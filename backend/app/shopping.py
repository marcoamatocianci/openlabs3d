"""Owner-scoped carts and structured checkout use the existing order engine."""
import json
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict,EmailStr
from sqlalchemy import select,delete
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from . import models,schemas
from .database import get_db
from .main import require,mutate,fail,get_listing
from .pricing import quote
from .accounts import Contact
router=APIRouter(prefix='/api')
class CartLine(schemas.QuoteInput):
    listing_id:int=Field(gt=0)
class CheckoutContact(Contact):
    email:EmailStr|None=None

class Checkout(BaseModel):
    model_config=ConfigDict(extra='forbid')
    idempotency_key:str=Field(min_length=16,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')
    contact:CheckoutContact
    address_id:int|None=None
    direct:CartLine|None=None

def buying(auth):
    if auth[0].role=='admin':fail(403,'Administrators use marketplace order management')

def cart_data(db,user_id):
    result=[]
    for row in db.scalars(select(models.CartItem).where(models.CartItem.user_id==user_id).order_by(models.CartItem.id)):
        p=db.get(models.Listing,row.listing_id)
        data={k:getattr(row,k) for k in ('id','listing_id','material','color','quantity')}
        data.update(title=p.title,available=p.status=='approved' and not p.removed)
        try:data.update(quote(p,row.material,row.color,row.quantity))
        except HTTPException as exc:
            data['available']=False
            data['unavailable_reason']=exc.detail
        result.append(data)
    return result
@router.get('/cart')
def cart(auth=Depends(require),db:Session=Depends(get_db)):
    buying(auth);return cart_data(db,auth[0].id)
@router.put('/cart')
def put_cart(body:CartLine,auth=Depends(mutate),db:Session=Depends(get_db)):
    buying(auth);p=get_listing(db,body.listing_id)
    if p.status!='approved':fail(409,'Product is unavailable')
    q=quote(p,body.material,body.color,body.quantity)
    stmt=insert(models.CartItem).values(user_id=auth[0].id,listing_id=p.id,material=q['material'],color=q['color'],quantity=q['quantity'])
    db.execute(stmt.on_conflict_do_update(index_elements=['user_id','listing_id','material','color'],set_={'quantity':body.quantity}));db.commit()
    return cart_data(db,auth[0].id)

@router.post('/cart')
def add_cart(body:CartLine,auth=Depends(mutate),db:Session=Depends(get_db)):
    buying(auth);p=get_listing(db,body.listing_id)
    if p.status!='approved':fail(409,'Product is unavailable')
    q=quote(p,body.material,body.color,body.quantity)
    stmt=insert(models.CartItem).values(user_id=auth[0].id,listing_id=p.id,material=q['material'],color=q['color'],quantity=q['quantity'])
    try:
        db.execute(stmt.on_conflict_do_update(index_elements=['user_id','listing_id','material','color'],set_={'quantity':models.CartItem.quantity+body.quantity}))
        row=db.scalar(select(models.CartItem).where(models.CartItem.user_id==auth[0].id,models.CartItem.listing_id==p.id,models.CartItem.material==q['material'],models.CartItem.color==q['color']))
        quote(p,row.material,row.color,row.quantity)
        db.commit()
    except IntegrityError:db.rollback();fail(422,'Maximum quantity exceeded')
    except HTTPException:db.rollback();raise
    return cart_data(db,auth[0].id)

@router.delete('/cart/{item_id}')
def delete_cart(item_id:int,auth=Depends(mutate),db:Session=Depends(get_db)):
    result=db.execute(delete(models.CartItem).where(models.CartItem.id==item_id,models.CartItem.user_id==auth[0].id))
    if not result.rowcount:fail(404,'Cart item not found')
    db.commit();return cart_data(db,auth[0].id)
@router.post('/checkout',status_code=201)
def checkout(body:Checkout,auth=Depends(mutate),db:Session=Depends(get_db)):
    buying(auth)
    if not auth[0].email_verified:fail(403,'Verify your email before ordering')
    from .operations import persist_order,order_data
    existing=db.scalar(select(models.Order).where(models.Order.buyer_id==auth[0].id,models.Order.idempotency_key==body.idempotency_key))
    if existing:return order_data(existing,db)
    contact=body.contact
    if any(not getattr(contact,k) for k in ('first_name','last_name','phone')):fail(422,'Your contact information is incomplete.')
    address=contact
    if body.address_id:
        address=db.get(models.UserAddress,body.address_id)
        if not address or address.user_id!=auth[0].id:fail(404,'Saved address not found')
    if any(not getattr(address,k) for k in ('country','city','street')):fail(422,'Complete the delivery address')
    lines=[body.direct] if body.direct else [CartLine(listing_id=r['listing_id'],material=r['material'],color=r['color'],quantity=r['quantity']) for r in cart_data(db,auth[0].id)]
    if not lines:fail(422,'Your basket is empty')
    validated=[]
    for line in lines:
        p=get_listing(db,line.listing_id)
        q=quote(p,line.material,line.color,line.quantity)
        validated.append(schemas.OrderLine(**line.model_dump(),expected_price_cents=q['unit_price_cents']))
    snapshot={key:getattr(address,key) for key in Contact.model_fields}
    order=schemas.OrderInput(idempotency_key=body.idempotency_key,contact=json.dumps({'first_name':contact.first_name,'last_name':contact.last_name,'phone':contact.phone,'email':auth[0].email},ensure_ascii=False),address=json.dumps(snapshot,ensure_ascii=False),items=validated)
    # The existing order engine revalidates availability and prices and snapshots lines.
    result=persist_order(order,auth,db,commit=False,contact_email=contact.email)
    if not body.direct:
        # Remove only the purchased configuration and quantity; leave concurrent edits intact.
        for line in lines:db.execute(delete(models.CartItem).where(models.CartItem.user_id==auth[0].id,models.CartItem.listing_id==line.listing_id,models.CartItem.material==line.material,models.CartItem.color==line.color,models.CartItem.quantity==line.quantity))
    db.commit()
    return result

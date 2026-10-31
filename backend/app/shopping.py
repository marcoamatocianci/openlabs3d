"""Owner-scoped carts and structured checkout use the existing order engine."""
import json
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict,EmailStr
from sqlalchemy import select,delete
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
PRICE=Field(ge=0,le=100_000_000)
class CartInput(CartLine):
    # The unit price the buyer was shown when adding. Never charged: it is only compared with the
    # authoritative quote, so a stale page leads to a price-change notice instead of a silent change.
    expected_unit_price_cents:int|None=Field(default=None,ge=0,le=100_000_000)
class PriceAcceptance(BaseModel):
    model_config=ConfigDict(extra='forbid')
    unit_price_cents:int=PRICE
class ConfirmedLine(CartLine):
    unit_price_cents:int=PRICE
class CheckoutContact(Contact):
    email:EmailStr|None=None

class Checkout(BaseModel):
    model_config=ConfigDict(extra='forbid')
    idempotency_key:str=Field(min_length=16,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')
    contact:CheckoutContact
    address_id:int|None=None
    direct:CartLine|None=None
    # Every line exactly as the checkout page showed it, with the unit price the buyer confirmed.
    confirmed:list[ConfirmedLine]=Field(min_length=1,max_length=30)

def buying(auth):
    if auth[0].role=='admin':fail(403,'Administrators use marketplace order management')

def euros(cents):return f'€{cents//100}.{cents%100:02d}'
def price_change(listing,line,previous,current):
    message=(f'The price of this product has changed from {euros(previous)} to {euros(current)}. Please review the updated price before continuing.' if previous is not None
             else f'Please review the current price of this product ({euros(current)}) before continuing.')
    return {'listing_id':listing.id,'title':listing.title,'material':line.material,'color':line.color,'quantity':line.quantity,'previous_unit_price_cents':previous,'current_unit_price_cents':current,'message':message}
def prices_changed(changes):
    first=changes[0]['message'] if len(changes)==1 else f'The prices of {len(changes)} products have changed. Please review the updated prices before continuing.'
    fail(409,{'code':'price_changed','message':first,'changes':changes})

def cart_data(db,user_id):
    result=[]
    for row in db.scalars(select(models.CartItem).where(models.CartItem.user_id==user_id).order_by(models.CartItem.id)):
        p=db.get(models.Listing,row.listing_id)
        data={k:getattr(row,k) for k in ('id','listing_id','material','color','quantity','confirmed_unit_price_cents')}
        data.update(title=p.title,available=p.status=='approved' and not p.removed,price_changed=False)
        try:
            data.update(quote(p,row.material,row.color,row.quantity))
            if row.confirmed_unit_price_cents!=data['unit_price_cents']:
                data.update(price_changed=True,price_change=price_change(p,row,row.confirmed_unit_price_cents,data['unit_price_cents']))
        except HTTPException as exc:
            data['available']=False
            data['unavailable_reason']=exc.detail
        result.append(data)
    return result
def pending_change(p,row):
    """Whether this line has a price change the buyer has not accepted yet."""
    try:return row.confirmed_unit_price_cents!=quote(p,row.material,row.color,row.quantity)['unit_price_cents']
    except HTTPException:return False
def save_line(db,user_id,p,body,quantity,shown):
    """Insert or update a basket line. A line whose price is already awaiting review keeps the
    price the buyer last accepted; otherwise the line takes the price shown to the buyer."""
    row=db.scalar(select(models.CartItem).where(models.CartItem.user_id==user_id,models.CartItem.listing_id==p.id,models.CartItem.material==body.material,models.CartItem.color==body.color))
    q=quote(p,body.material,body.color,quantity)
    keep=row is not None and pending_change(p,row)
    if row is None:
        row=models.CartItem(user_id=user_id,listing_id=p.id,material=q['material'],color=q['color'],quantity=quantity);db.add(row)
    row.quantity=quantity
    if not keep:row.confirmed_unit_price_cents=q['unit_price_cents'] if shown is None else shown
    return row
@router.get('/cart')
def cart(auth=Depends(require),db:Session=Depends(get_db)):
    buying(auth);return cart_data(db,auth[0].id)
@router.put('/cart')
def put_cart(body:CartInput,auth=Depends(mutate),db:Session=Depends(get_db)):
    buying(auth);p=get_listing(db,body.listing_id)
    if p.status!='approved':fail(409,'Product is unavailable')
    material=quote(p,body.material,body.color,body.quantity)['material']
    save_line(db,auth[0].id,p,body.model_copy(update={'material':material}),body.quantity,body.expected_unit_price_cents);db.commit()
    return cart_data(db,auth[0].id)

@router.post('/cart')
def add_cart(body:CartInput,auth=Depends(mutate),db:Session=Depends(get_db)):
    buying(auth);p=get_listing(db,body.listing_id)
    if p.status!='approved':fail(409,'Product is unavailable')
    q=quote(p,body.material,body.color,body.quantity);body=body.model_copy(update={'material':q['material']})
    existing=db.scalar(select(models.CartItem.quantity).where(models.CartItem.user_id==auth[0].id,models.CartItem.listing_id==p.id,models.CartItem.material==body.material,models.CartItem.color==body.color)) or 0
    shown=body.expected_unit_price_cents
    # The page quoted the added quantity; when that was accurate, the merged line's own quote is
    # what the buyer will see next, so it needs no review.
    if shown is not None and shown==q['unit_price_cents']:shown=None
    try:
        save_line(db,auth[0].id,p,body,existing+body.quantity,shown);db.commit()
    except HTTPException:db.rollback();raise
    except IntegrityError:db.rollback();fail(422,'Maximum quantity exceeded')
    return cart_data(db,auth[0].id)

@router.post('/cart/{item_id}/accept-price')
def accept_price(item_id:int,body:PriceAcceptance,auth=Depends(mutate),db:Session=Depends(get_db)):
    """The buyer explicitly accepts the price shown to them. If it changed again meanwhile, the
    newer price must be reviewed instead."""
    buying(auth)
    row=db.scalar(select(models.CartItem).where(models.CartItem.id==item_id,models.CartItem.user_id==auth[0].id))
    if not row:fail(404,'Cart item not found')
    p=get_listing(db,row.listing_id)
    current=quote(p,row.material,row.color,row.quantity)['unit_price_cents']
    if body.unit_price_cents!=current:prices_changed([price_change(p,row,body.unit_price_cents,current)])
    row.confirmed_unit_price_cents=current;db.commit()
    return cart_data(db,auth[0].id)

@router.delete('/cart/{item_id}')
def delete_cart(item_id:int,auth=Depends(mutate),db:Session=Depends(get_db)):
    result=db.execute(delete(models.CartItem).where(models.CartItem.id==item_id,models.CartItem.user_id==auth[0].id))
    if not result.rowcount:fail(404,'Cart item not found')
    db.commit();return cart_data(db,auth[0].id)
@router.post('/checkout',status_code=201)
def checkout(body:Checkout,auth=Depends(mutate),db:Session=Depends(get_db)):
    """Create the order only at the prices the buyer confirmed on the checkout page.

    The request runs in an IMMEDIATE transaction (database.get_db), so no price, rule or stock
    change can commit between these checks and the order insert."""
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
    rows=[] if body.direct else list(db.scalars(select(models.CartItem).where(models.CartItem.user_id==auth[0].id).order_by(models.CartItem.id)))
    lines=[body.direct] if body.direct else [CartLine(listing_id=r.listing_id,material=r.material,color=r.color,quantity=r.quantity) for r in rows]
    if not lines:fail(422,'Your basket is empty')
    shown={(c.listing_id,c.material,c.color,c.quantity):c.unit_price_cents for c in body.confirmed}
    if len(shown)!=len(body.confirmed) or set(shown)!={(l.listing_id,l.material,l.color,l.quantity) for l in lines}:
        fail(409,{'code':'cart_changed','message':'Your basket changed in another window. Review it before submitting your order.'})
    quoted,changes=[],[]
    for n,line in enumerate(lines):
        p=get_listing(db,line.listing_id)
        q=quote(p,line.material,line.color,line.quantity)   # 422 when no longer available
        price=q['unit_price_cents'];confirmed=shown[(line.listing_id,line.material,line.color,line.quantity)]
        # A basket line must also match the price its owner last accepted in the basket.
        accepted=rows[n].confirmed_unit_price_cents if rows else confirmed
        if confirmed!=price or accepted!=price:changes.append(price_change(p,line,accepted if accepted!=price else confirmed,price))
        quoted.append((line,q))
    if changes:prices_changed(changes)
    validated=[schemas.OrderLine(**line.model_dump(),expected_price_cents=q['unit_price_cents']) for line,q in quoted]
    snapshot={key:getattr(address,key) for key in Contact.model_fields}
    order=schemas.OrderInput(idempotency_key=body.idempotency_key,contact=json.dumps({'first_name':contact.first_name,'last_name':contact.last_name,'phone':contact.phone,'email':auth[0].email},ensure_ascii=False),address=json.dumps(snapshot,ensure_ascii=False),items=validated)
    # The existing order engine revalidates availability and prices and snapshots lines.
    result=persist_order(order,auth,db,commit=False,contact_email=contact.email)
    if sorted(i['price_cents'] for i in result['items'])!=sorted(shown.values()):
        db.rollback();fail(409,{'code':'price_changed','message':'Prices changed while your order was being placed. Please review them before continuing.'})
    if not body.direct:
        # Remove only the purchased configuration and quantity; leave concurrent edits intact.
        for line in lines:db.execute(delete(models.CartItem).where(models.CartItem.user_id==auth[0].id,models.CartItem.listing_id==line.listing_id,models.CartItem.material==line.material,models.CartItem.color==line.color,models.CartItem.quantity==line.quantity))
    db.commit()
    return result

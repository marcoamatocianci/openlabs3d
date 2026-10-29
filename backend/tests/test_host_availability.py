import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.database import Base
from app import models
from app.availability import combinations, supports
from app.pricing import quote

@pytest.fixture
def setup():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user=models.User(email='host@example.org',password_hash='x',display_name='Host',role='host')
        db.add(user);db.flush()
        host=models.HostApplication(user_id=user.id,status='approved')
        printer=models.HostPrinter(user_id=user.id,manufacturer='Custom',model='Printer',technology='FDM',x=200,y=200,z=200,quantity=1,materials='["PLA","PETG"]',material_colors='{"PLA":{"red":"#ff0000"},"PETG":{"blue":"#0000ff"}}')
        product=models.Listing(owner_id=user.id,title='Rack',status='approved',material='PLA',configuration='{"materials":{"PLA":10000,"PETG":12000}}',cad_dimensions='[100,100,100]',price_cents=1000)
        db.add_all([host,printer,product]);db.commit()
        yield db,user,host,printer,product

def test_exact_combinations_and_persistence(setup):
    db,user,host,printer,p=setup
    db.expire_all()
    assert combinations(p)=={'PLA':{'red':'#ff0000'},'PETG':{'blue':'#0000ff'}}
    assert quote(p,'PETG','blue',2)['total_cents']==2400
    with pytest.raises(HTTPException):quote(p,'PLA','blue',1)

@pytest.mark.parametrize('change', ['suspended','inactive','buyer','oversize','unknown-colors','unknown-size'])
def test_unavailable(setup,change):
    db,user,host,printer,p=setup
    if change=='suspended':host.status='suspended'
    if change=='inactive':user.active=False
    if change=='buyer':user.role='buyer'
    if change=='oversize':p.cad_dimensions='[500,100,100]'
    if change=='unknown-colors':printer.material_colors='{}'
    if change=='unknown-size':p.cad_dimensions='[]'
    db.flush()
    assert not supports(p,'PLA','red',user.id)
    with pytest.raises(HTTPException):quote(p,'PLA','red',1)

@pytest.mark.parametrize('dimensions',['{}','[true,100,100]','[0,100,100]','[100,100]','["100",100,100]','not-json'])
def test_invalid_dimensions_fail_closed(setup,dimensions):
    db,user,host,printer,p=setup
    p.cad_dimensions=dimensions;db.flush()
    assert combinations(p)=={}

def test_no_cross_printer_combination(setup):
    db,user,host,printer,p=setup
    printer.material_colors='{"PLA":{"red":"#ff0000"}}'
    small=models.HostPrinter(user_id=user.id,manufacturer='Custom',model='Small',technology='FDM',x=50,y=200,z=200,quantity=1,materials='["PETG"]',material_colors='{"PETG":{"blue":"#0000ff"}}')
    db.add(small);db.flush()
    assert not supports(p,'PETG','blue',user.id)
    small.x=200;db.flush()
    assert supports(p,'PETG','blue',user.id)
    assert not supports(p,'PLA','blue',user.id)

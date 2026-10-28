"""Integer minor-unit pricing; product rules live in SQLite."""
import json
from pydantic import BaseModel, ConfigDict, Field
from fastapi import HTTPException
COLORS={'aqua-blue':'#429fb7','signal-red':'#d9424d','cream':'#e7d9bc'}
class Rules(BaseModel):
    model_config=ConfigDict(extra='forbid')
    materials: dict[str,int] = Field(default_factory=dict)
    discounts: dict[int,int] = Field(default_factory=dict)
    max_quantity: int = Field(default=50,ge=1,le=50)

def options(p):
    rules=json.loads(p.configuration or '{}')
    return {'materials':rules.get('materials') or {p.material:10000},'discounts':rules.get('discounts',{}),'max_quantity':rules.get('max_quantity',50),'colors':COLORS if p.collection_key else {},'model_url':p.model_url}

def quote(p, material, color, quantity):
    o=options(p);material=material or p.material
    if material not in o['materials'] or (color not in o['colors'] if o['colors'] else bool(color)) or not 1<=quantity<=o['max_quantity']:
        raise HTTPException(422,'Choose available material, color and quantity')
    adjusted=(p.price_cents*o['materials'][material]+5000)//10000
    discount=max((int(v) for k,v in o['discounts'].items() if quantity>=int(k)),default=0)
    unit=(adjusted*(10000-discount)+5000)//10000
    return dict(material=material,color=color,quantity=quantity,base_price_cents=p.price_cents,material_adjustment_cents=adjusted-p.price_cents,discount_bps=discount,unit_price_cents=unit,total_cents=unit*quantity,currency=p.currency)

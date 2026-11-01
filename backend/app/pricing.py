"""Integer minor-unit pricing; product rules live in SQLite."""
import json
from pydantic import BaseModel, ConfigDict, Field
from fastapi import HTTPException
class Rules(BaseModel):
    model_config=ConfigDict(extra='forbid')
    materials: dict[str,int] = Field(default_factory=dict)
    discounts: dict[int,int] = Field(default_factory=dict)
    max_quantity: int = Field(default=50,ge=1,le=50)

UNAVAILABLE='This configuration is unavailable from eligible printing hosts. Refresh the product and choose another configuration.'
OWN_PRINTERS_ONLY='Only your own printers can make this configuration, and printing hosts cannot manufacture their own orders. Choose a material and colour another host offers.'

def options(p, buyer_id=None):
    """What can be bought. For a signed-in buyer, only what a host other than themselves can make."""
    from .visuals import visual_data
    visual=visual_data(p)
    rules=json.loads(p.configuration or '{}')
    from .availability import combinations
    available=combinations(p,exclude_host=buyer_id)
    materials={m:f for m,f in (rules.get('materials') or {p.material:10000}).items() if available.get(m)}
    # Nothing left for this buyer although others can order it: only their own printers make it.
    own_only=buyer_id is not None and not materials and bool(options(p)['materials'])
    return {'own_printers_only':own_only,'pricing_materials':rules.get('materials') or {p.material:10000},'materials':materials,'discounts':rules.get('discounts',{}),'max_quantity':rules.get('max_quantity',50),'colors':{c:h for m in materials for c,h in available[m].items()},'colors_by_material':{m:available[m] for m in materials},'visual':visual,'model_url':visual.get('model','' if p.cad_path else p.model_url)}

def offered(o, material, color, quantity):
    return material in o['materials'] and color in o['colors_by_material'].get(material,{}) and 1<=quantity<=o['max_quantity']

def quote(p, material, color, quantity, buyer_id=None):
    o=options(p,buyer_id);material=material or p.material
    if not offered(o,material,color,quantity):
        own=buyer_id is not None and offered(options(p),material,color,quantity)
        raise HTTPException(422,OWN_PRINTERS_ONLY if own else UNAVAILABLE)
    adjusted=(p.price_cents*o['materials'][material]+5000)//10000
    discount=max((int(v) for k,v in o['discounts'].items() if quantity>=int(k)),default=0)
    unit=(adjusted*(10000-discount)+5000)//10000
    return dict(material=material,color=color,color_hex=o['colors_by_material'][material][color],quantity=quantity,base_price_cents=p.price_cents,material_adjustment_cents=adjusted-p.price_cents,discount_bps=discount,unit_price_cents=unit,total_cents=unit*quantity,currency=p.currency)

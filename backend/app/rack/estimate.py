"""Material and price from geometry. Estimates only: real consumption depends on the slicer and the host's settings.

The rates are configuration, stored as the marketplace setting 'rack_pricing' and edited by administrators. Their default
values are PROTOTYPE values chosen to make the flow testable, not commercially validated prices, and the interface says so
until an administrator marks them validated. Every quote still flows through pricing.quote(): a rack is sold as a private
listing whose price_cents and material factors come from price_rules(), so the existing quote, price-change notice and
checkout rules apply unchanged. There is one price per rack and material, not per host: hosts have no price data today.
"""
import json, math
from pydantic import BaseModel, ConfigDict, Field

# Physical properties, typical values. Flexible and high-temperature filaments are left out: a rack needs a stiff, ordinary material.
DENSITY_G_CM3 = {'PLA': 1.24, 'PETG': 1.27, 'ABS': 1.04, 'ASA': 1.07}
MATERIALS = tuple(DENSITY_G_CM3)
SETTING_KEY = 'rack_pricing'
SHELL_FIT, INFILL_FIT, SOLID_SHARE = .742, .207, .98

class Rates(BaseModel):
    """What goes into a price. Each is one number an administrator can defend or change."""
    model_config = ConfigDict(extra='forbid')
    material_eur_per_kg: dict[str, float] = Field(default_factory=lambda: {'PLA': 25, 'PETG': 28, 'ABS': 30, 'ASA': 34})
    setup_eur: float = Field(default=4.5, ge=0, le=500)                # preparing a job: slicing, plate, removal, checks
    machine_eur_per_hour: float = Field(default=1.8, ge=0, le=500)     # printer time and the host's share of it
    deposition_mm3_s: float = Field(default=5.0, gt=0, le=100)         # for the time inside the price; never shown as a print time
    per_hole_eur: float = Field(default=.06, ge=0, le=50)              # inspection grows with the positions
    label_eur: float = Field(default=1.5, ge=0, le=100)
    premium_factor: float = Field(default=1.15, ge=1, le=5)
    marketplace_fee_pct: float = Field(default=12, ge=0, le=90)
    commercially_validated: bool = False                               # True removes the "prototype price" wording

DEFAULT_RATES = Rates()

def load_rates(db):
    """The configured rates, or the defaults when none were saved or what is saved no longer parses."""
    from ..models import MarketplaceSetting
    row = db.get(MarketplaceSetting, SETTING_KEY)
    if row is None: return DEFAULT_RATES
    try: return Rates.model_validate(json.loads(row.value))
    except ValueError: return DEFAULT_RATES

def printed_volume(volume_mm3, area_mm2):
    """Plastic actually laid down. Fitted to PrusaSlicer on the ten racks of scripts/rack_validation_prints.py (0.2 mm layers,
    3 perimeters, 15% gyroid infill): within about 15% of the slicer on each. Thin Lightweight walls print solid, so the
    solid volume caps it. A host's own slicer settings decide the real amount, so this stays an estimate."""
    return min(volume_mm3 * SOLID_SHARE, area_mm2 * SHELL_FIT + volume_mm3 * INFILL_FIT)

def grams(volume_mm3, area_mm2, material):
    return printed_volume(volume_mm3, area_mm2) / 1000 * DENSITY_G_CM3[material]

def unit_price_cents(volume_mm3, area_mm2, material, holes, labelled, style, rates=DEFAULT_RATES):
    per_kg = rates.material_eur_per_kg.get(material, max(rates.material_eur_per_kg.values(), default=30))
    euros = (rates.setup_eur + grams(volume_mm3, area_mm2, material) / 1000 * per_kg
             + printed_volume(volume_mm3, area_mm2) / rates.deposition_mm3_s / 3600 * rates.machine_eur_per_hour
             + holes * rates.per_hole_eur + (rates.label_eur if labelled else 0))
    euros *= rates.premium_factor if style == 'premium' else 1
    euros *= 1 + rates.marketplace_fee_pct / 100
    return int(math.ceil(euros * 10)) * 10      # up to the next 10 cents

def price_rules(volume_mm3, area_mm2, holes, labelled, style, rates=DEFAULT_RATES):
    """(base price in cents, {material: factor in basis points}): the private listing's pricing, cheapest material as base."""
    prices = {m: unit_price_cents(volume_mm3, area_mm2, m, holes, labelled, style, rates) for m in MATERIALS}
    base = min(prices.values())
    return base, {m: round(p * 10000 / base) for m, p in prices.items()}

def material_price(base, factor):
    """Exactly pricing.quote()'s material adjustment."""
    return (base * factor + 5000) // 10000

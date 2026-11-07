"""The tube profile library. Volume does not determine dimensions, so every profile records its own and where they
came from. Nothing here has been measured by OpenLabs3D: verification_status says what backs each profile.

  generic_unverified    a size chosen to accept common tubes of this type; dimensions partly assumed
  published_unmeasured  overall size from a manufacturer's or distributor's sheet; cone and tip are assumed
  measured              physically measured (no profile has reached this yet)

Add a container by adding a profile here. Purchased racks store the resolved dimensions they were made from, so
editing this library never changes an existing order.
"""
from dataclasses import asdict, dataclass

LIBRARY_VERSION = 1

@dataclass(frozen=True)
class TubeProfile:
    id: str
    label: str
    family: str                  # groups interchangeable choices in the interface
    manufacturer: str
    model: str
    nominal_capacity_ml: float
    body_diameter_mm: float      # largest body diameter that enters the rack
    cap_diameter_mm: float       # cap envelope, including the hinge tab of a snap cap
    overall_length_mm: float     # with the cap on
    support_region_diameter_mm: float
    cone_length_mm: float        # assumed in every profile: drawings could not be read
    tip_diameter_mm: float       # assumed in every profile
    bottom_geometry: str
    recommended_clearance_mm: float   # bore diameter minus body diameter
    minimum_separation_mm: float      # free gap between neighbouring caps, for fingers
    insertion_fraction: float    # share of the length held below the deck
    source_reference: str
    verification_status: str
    def public(self): return asdict(self)

_CORNING_15 = 'Corning spec sheet for Falcon 352096 (LSR00039, via pdf.dutscher.com/doc/352096/352096_FTen.pdf): 120.75 mm capped, 17.37 mm outside; the 22.48 mm cap reading is unconfirmed.'
_CORNING_50 = 'Corning drawing LSR00042 (tube length 114.55 mm) and distributor listings (Fisher, Avantor: 30 × 115 mm). Cap diameter is an estimate.'
_EPPENDORF_15 = 'Eppendorf Safe-Lock 1.5 mL sheet via pdf.dutscher.com (10.8 mm maximum outside, 38.9 mm): labels could not be mapped with certainty. Cap envelope is an estimate.'
_ASSUMED_05 = 'No manufacturer drawing could be read. Typical values, assumed; measure your tube before relying on the fit.'

PROFILES = {p.id: p for p in (
    TubeProfile('micro-0.5-generic', '0.5 mL microcentrifuge', 'micro-0.5', 'Generic', '0.5 mL snap-cap', .5, 8.0, 11.0, 30.5, 8.0, 17.0, 2.6, 'conical', .7, 3.0, .62, _ASSUMED_05, 'generic_unverified'),
    TubeProfile('micro-1.5-generic', '1.5 mL microcentrifuge', 'micro-1.5', 'Generic', '1.5 mL snap-cap', 1.5, 10.9, 14.0, 39.0, 10.9, 20.0, 3.4, 'conical', .8, 3.5, .62, _EPPENDORF_15, 'generic_unverified'),
    TubeProfile('conical-15-generic', '15 mL conical', 'conical-15', 'Generic', '15 mL screw-cap', 15, 17.4, 22.5, 120.8, 17.4, 22.0, 5.0, 'conical', .8, 3.5, .5, _CORNING_15, 'generic_unverified'),
    TubeProfile('conical-50-generic', '50 mL conical', 'conical-50', 'Generic', '50 mL screw-cap', 50, 30.0, 34.5, 115.0, 30.0, 17.0, 8.0, 'conical', .9, 3.5, .5, _CORNING_50, 'generic_unverified'),
    TubeProfile('falcon-352096', 'Falcon 15 mL (352096)', 'conical-15', 'Corning', 'Falcon 352096', 15, 17.37, 22.48, 120.75, 17.37, 22.0, 5.0, 'conical', .7, 3.5, .5, _CORNING_15, 'published_unmeasured'),
    TubeProfile('falcon-352070', 'Falcon 50 mL (352070)', 'conical-50', 'Corning', 'Falcon 352070', 50, 30.0, 34.5, 114.55, 30.0, 17.0, 8.0, 'conical', .8, 3.5, .5, _CORNING_50, 'published_unmeasured'),
)}
DEFAULT_PROFILE = {'conical-50': 'conical-50-generic', 'conical-15': 'conical-15-generic', 'micro-1.5': 'micro-1.5-generic', 'micro-0.5': 'micro-0.5-generic'}
FAMILIES = (('conical-50', '50 mL conical'), ('conical-15', '15 mL conical'), ('micro-1.5', '1.5 mL microcentrifuge'), ('micro-0.5', '0.5 mL microcentrifuge'))

# Adjustments a buyer may make, relative to the chosen profile. Outside these the tube is a different product.
OVERRIDE_LIMITS = {'body_diameter_mm': (.85, 1.15), 'cap_diameter_mm': (.8, 1.3), 'overall_length_mm': (.75, 1.25)}

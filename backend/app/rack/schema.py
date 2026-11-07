"""RackConfiguration: what a buyer asks for. Versioned and strict; unknown fields are refused and nothing in it is
ever executed. The planner turns it into a spec (hole positions, solids) which is what gets hashed and built."""
import hashlib, json, re, unicodedata
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1
Style = Literal['lightweight', 'premium']
Coordinate = Annotated[float, Field(ge=-1000, le=1000, allow_inf_nan=False)]
# Letters both font families draw, digits, and the punctuation a lab name needs. No control characters.
LABEL_TEXT = re.compile(r"^[A-Za-z0-9À-ÖØ-öø-ÿ .,:;'&()+/#\-]*$")

class TubeCount(BaseModel):
    model_config = ConfigDict(extra='forbid')
    profile_id: str = Field(max_length=40)
    quantity: int = Field(ge=0, le=1000, strict=True)

class TubePosition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    profile_id: str = Field(max_length=40)
    x: Coordinate
    y: Coordinate

class TubeOverride(BaseModel):
    model_config = ConfigDict(extra='forbid')
    body_diameter_mm: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    cap_diameter_mm: float | None = Field(default=None, gt=0, le=120, allow_inf_nan=False)
    overall_length_mm: float | None = Field(default=None, gt=0, le=300, allow_inf_nan=False)

class Envelope(BaseModel):
    """A printer's build volume the buyer chose to stay within, as offered by the availability data."""
    model_config = ConfigDict(extra='forbid')
    x: float = Field(gt=0, le=2000, allow_inf_nan=False)
    y: float = Field(gt=0, le=2000, allow_inf_nan=False)
    z: float = Field(gt=0, le=2000, allow_inf_nan=False)

class Layout(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['auto', 'manual'] = 'auto'
    spacing: Literal['compact', 'standard', 'roomy'] = 'standard'
    arrangement: Literal['auto', 'grid', 'staggered', 'grouped'] = 'auto'
    orientation: Literal['auto', 'landscape', 'portrait'] = 'auto'
    columns: int | None = Field(default=None, ge=1, le=60)
    outer_margin_mm: float = Field(default=0, ge=0, le=15, allow_inf_nan=False)
    positions: list[TubePosition] = Field(default_factory=list, max_length=1000)
    envelope: Envelope | None = None     # None: whatever fits the printers available for this material and colour
    preference: Literal['balanced', 'compact', 'wide'] = 'balanced'      # what the buyer wants the software to favour

class Label(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    text: str = Field(default='', max_length=120)
    font: Literal['sans', 'serif', 'mono'] = 'sans'
    size_mm: float | None = Field(default=None, gt=0, le=60, allow_inf_nan=False)    # None: as large as fits, up to the default
    position: Literal['front', 'back', 'left', 'right', 'top'] = 'front'
    style: Literal['engraved', 'embossed'] = 'engraved'
    @field_validator('text')
    @classmethod
    def printable(cls, value):
        value = unicodedata.normalize('NFC', value)
        if not LABEL_TEXT.fullmatch(value):
            raise ValueError('Labels may use letters, digits, spaces and . , : ; \' & ( ) + / # -')
        return value

class RackConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = SCHEMA_VERSION
    tubes: list[TubeCount] = Field(default_factory=list, max_length=20)
    layout: Layout = Field(default_factory=Layout)
    style: Style = 'lightweight'
    edge: Literal['sharp', 'soft', 'rounded'] = 'soft'
    corner_radius_mm: float | None = Field(default=None, ge=0, le=60, allow_inf_nan=False)   # advanced; limited by the geometry
    height_mm: float | None = Field(default=None, gt=0, le=400, allow_inf_nan=False)          # None: recommended for these tubes
    clearance_adjust_mm: float = Field(default=0, ge=-.3, le=.8, allow_inf_nan=False)
    overrides: dict[str, TubeOverride] = Field(default_factory=dict, max_length=20)
    label: Label | None = None
    # The finish decides which printers count, not the geometry, so these two never reach the spec or its hash.
    material: str = Field(default='', max_length=60)
    color: str = Field(default='', max_length=48)

def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)

def spec_hash(spec):
    """The identity of a rack: the same geometry input always gives the same hash, and so the same build."""
    return hashlib.sha256(canonical_json(spec).encode()).hexdigest()

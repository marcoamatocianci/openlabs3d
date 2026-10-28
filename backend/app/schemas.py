from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)
class Login(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
class ListingInput(BaseModel):
    featured: bool = False
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(default='', max_length=160)
    description: str = Field(default='', max_length=10000)
    category: str = Field(default='', max_length=100)
    price_cents: int = Field(default=0, ge=0, le=100000000)
    material: str = Field(default='', max_length=200)
    dimensions: str = Field(default='', max_length=200)
    compatibility: str = Field(default='', max_length=300)
    listing_type: Literal['official','community'] = 'community'
class ListingPatch(BaseModel):
    featured: bool | None = None
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=10000)
    category: str | None = Field(default=None, max_length=100)
    price_cents: int | None = Field(default=None, ge=0, le=100000000)
    material: str | None = Field(default=None, max_length=200)
    dimensions: str | None = Field(default=None, max_length=200)
    compatibility: str | None = Field(default=None, max_length=300)
    listing_type: Literal['official','community'] | None = None
class Reorder(BaseModel):
    image_ids: list[int] = Field(max_length=5)
class Reject(BaseModel):
    reason: str = Field(default='', max_length=1000)

class HostApplicationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(max_length=150)
    contact: str = Field(max_length=200)
    country: str = Field(max_length=100)
    region: str = Field(max_length=150)
    printers: str = Field(max_length=1000)
    technologies: str = Field(max_length=500)
    materials: str = Field(max_length=500)
    dimensions: str = Field(max_length=200)
    capabilities: str = Field(max_length=3000)
    additional: str = Field(default='', max_length=3000)
    submit: bool = False

class ProfileInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)

class AccountDeletion(BaseModel):
    password: str = Field(min_length=1, max_length=128)

class QuoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material: str = Field(default="", max_length=200)
    color: str = Field(default="", max_length=40)
    quantity: int = Field(ge=1, le=50, strict=True)

class OrderLine(QuoteInput):
    color: str = Field(default="", max_length=40)
    listing_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=50)
    expected_price_cents: int = Field(ge=0, le=100000000)

class OrderInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    contact: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=1000)
    items: list[OrderLine] = Field(min_length=1, max_length=30)

class JobTransition(BaseModel):
    status: Literal['printing', 'ready', 'completed']

class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0, le=10000)
    active: bool = True

class SettingsInput(BaseModel):
    marketplace_name: str = Field(min_length=1, max_length=100)
    contact: str = Field(default='', max_length=200)
    host_applications_open: bool = True

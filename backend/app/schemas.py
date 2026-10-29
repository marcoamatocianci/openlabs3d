from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    @field_validator("password")
    @classmethod
    def password_policy(cls, value):
        if not any(c.isupper() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Password requires an uppercase letter and a number")
        return value
    display_name: str = Field(default="", max_length=100)
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

def validate_delivery_snapshot(value, contact_only=False):
    import json
    from .accounts import Contact
    try:
        data=json.loads(value)
        if not isinstance(data,dict):raise ValueError('Expected structured contact information')
        email=data.pop('email',None)
        validated=Contact.model_validate(data)
        required=('first_name','last_name','phone') if contact_only else ('country','city','street')
        if any(not getattr(validated,k) for k in required):raise ValueError('Complete contact and delivery information')
        result=validated.model_dump()
        if email is not None:result['email']=str(__import__("pydantic").TypeAdapter(EmailStr).validate_python(email))
        return json.dumps(result,ensure_ascii=False)
    except (ValueError,TypeError):raise ValueError('Provide valid structured contact and delivery information') from None

class OrderInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    contact: str = Field(min_length=1, max_length=1000)
    address: str = Field(min_length=1, max_length=3000)
    items: list[OrderLine] = Field(min_length=1, max_length=30)
    @field_validator('contact')
    @classmethod
    def validate_contact(cls,value):return validate_delivery_snapshot(value,True)
    @field_validator('address')
    @classmethod
    def validate_address(cls,value):return validate_delivery_snapshot(value)


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

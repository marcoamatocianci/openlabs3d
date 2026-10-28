from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, CheckConstraint, Text, Index, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def now(): return datetime.now(timezone.utc)
class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default='buyer')
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='1', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (CheckConstraint("role IN ('buyer','host','admin')"),)
class LoginSession(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
class Listing(Base):
    __tablename__ = 'listings'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), index=True)
    title: Mapped[str] = mapped_column(String(160), default='')
    description: Mapped[str] = mapped_column(Text, default='')
    category: Mapped[str] = mapped_column(String(100), default='')
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default='EUR')
    material: Mapped[str] = mapped_column(String(200), default='')
    dimensions: Mapped[str] = mapped_column(String(200), default='')
    compatibility: Mapped[str] = mapped_column(String(300), default='')
    listing_type: Mapped[str] = mapped_column(String(20), default='community')
    status: Mapped[str] = mapped_column(String(20), default='draft')
    configuration: Mapped[str] = mapped_column(Text, default='{}', server_default='{}')
    model_url: Mapped[str] = mapped_column(String(300), default='', server_default='')
    featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')
    collection_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejection_reason: Mapped[str] = mapped_column(String(1000), default='')
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner: Mapped[User] = relationship()
    images: Mapped[list['ProductImage']] = relationship(order_by='ProductImage.sort_order', cascade='all, delete-orphan')
    __table_args__ = (CheckConstraint('price_cents >= 0'), CheckConstraint("listing_type IN ('official','community')"), CheckConstraint("status IN ('draft','pending','approved','rejected','archived')"), Index('ix_listings_public', 'status', 'published_at'))
class ProductImage(Base):
    __tablename__ = 'product_images'
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey('listings.id', ondelete='CASCADE'), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(80), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class HostApplication(Base):
    __tablename__ = 'host_applications'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), unique=True)
    name: Mapped[str] = mapped_column(String(150), default='')
    contact: Mapped[str] = mapped_column(String(200), default='')
    country: Mapped[str] = mapped_column(String(100), default='')
    region: Mapped[str] = mapped_column(String(150), default='')
    printers: Mapped[str] = mapped_column(String(1000), default='')
    technologies: Mapped[str] = mapped_column(String(500), default='')
    materials: Mapped[str] = mapped_column(String(500), default='')
    dimensions: Mapped[str] = mapped_column(String(200), default='')
    capabilities: Mapped[str] = mapped_column(Text, default='')
    additional: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(20), default='draft', index=True)
    rejection_reason: Mapped[str] = mapped_column(String(1000), default='')
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    __table_args__ = (CheckConstraint("status IN ('draft','pending','approved','rejected','suspended')"),)

class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    contact: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    total_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default='EUR')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    items: Mapped[list['OrderItem']] = relationship(cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('buyer_id', 'idempotency_key'), CheckConstraint("status IN ('pending','accepted','printing','ready','completed','cancelled')"), CheckConstraint('total_cents >= 0'))

class OrderItem(Base):
    color: Mapped[str] = mapped_column(String(40), default='', server_default='')
    __tablename__ = 'order_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='RESTRICT'), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey('listings.id', ondelete='RESTRICT'))
    title: Mapped[str] = mapped_column(String(160))
    material: Mapped[str] = mapped_column(String(200))
    dimensions: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer)
    price_cents: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint('quantity > 0'), CheckConstraint('price_cents >= 0'))

class PrintingJob(Base):
    __tablename__ = 'printing_jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='RESTRICT'), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('order_items.id', ondelete='RESTRICT'), unique=True)
    host_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default='available', index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    item: Mapped[OrderItem] = relationship()
    __table_args__ = (CheckConstraint("status IN ('available','accepted','printing','ready','completed','cancelled')"),)

class Activity(Base):
    __tablename__ = 'activity_log'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(150))
    detail: Mapped[str] = mapped_column(String(1000), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class Category(Base):
    __tablename__ = 'categories'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class MarketplaceSetting(Base):
    __tablename__ = 'marketplace_settings'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))

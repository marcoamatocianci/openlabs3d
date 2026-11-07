from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, CheckConstraint, Text, Float, Index, Boolean, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import CITEXT
from .database import Base

def now(): return datetime.now(timezone.utc)
# Usernames keep the case they were typed in but are unique and matched case-insensitively:
# SQLite's NOCASE collation, PostgreSQL's citext (length is enforced by the request schemas).
USERNAME = String(32, collation='NOCASE').with_variant(CITEXT(), 'postgresql')
class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    username: Mapped[str] = mapped_column(USERNAME, unique=True, default=lambda: 'user_' + __import__('uuid').uuid4().hex[:20])
    theme: Mapped[str] = mapped_column(String(10), default='system', server_default='system')
    # The sole active selection: initials, an uploaded file, or an SVG design.
    profile_picture: Mapped[str] = mapped_column(Text, default='{"kind":"initials"}', server_default='{"kind":"initials"}')
    # Retained only as migration archives, never read as active pictures.
    avatar: Mapped[str] = mapped_column(String(80), default='', server_default='')
    avatar_mode: Mapped[str] = mapped_column(String(10), default='photo', server_default='photo')
    avatar_style: Mapped[str] = mapped_column(Text, default='', server_default='')
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')
    # When a link confirmed the address. NULL for accounts confirmed before this was recorded: the date is not known.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Existed unverified before verification became mandatory: may still sign in, and is still not verified.
    legacy_email_access: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0', nullable=False)
    # An address awaiting confirmation. The sign-in address changes only once it is confirmed.
    pending_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), default='', server_default='')
    last_name: Mapped[str] = mapped_column(String(100), default='', server_default='')
    phone: Mapped[str] = mapped_column(String(40), default='', server_default='')
    country: Mapped[str] = mapped_column(String(2), default='', server_default='')
    city: Mapped[str] = mapped_column(String(150), default='', server_default='')
    region: Mapped[str] = mapped_column(String(150), default='', server_default='')
    postal_code: Mapped[str] = mapped_column(String(30), default='', server_default='')
    street: Mapped[str] = mapped_column(String(200), default='', server_default='')
    additional: Mapped[str] = mapped_column(String(200), default='', server_default='')
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
    cad_path: Mapped[str] = mapped_column(String(80),default='',server_default='')
    cad_dimensions: Mapped[str] = mapped_column(Text,default='[]',server_default='[]')
    removed: Mapped[bool] = mapped_column(Boolean,default=False,server_default='0')
    collection_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejection_reason: Mapped[str] = mapped_column(String(1000), default='')
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}
    # A custom rack sold to one buyer (see app/racks.py): the hash of its geometry. Such a listing is private to its
    # owner and never edited. NULL for every catalogue product.
    rack_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rack_snapshot: Mapped[str] = mapped_column(Text, default='', server_default='')
    # Which saved design it came from, for "ordered versions". Cleared when that design is deleted; never needed to make it.
    rack_design_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner: Mapped[User] = relationship()
    images: Mapped[list['ProductImage']] = relationship(order_by='ProductImage.sort_order', cascade='all, delete-orphan')
    # The stored file behind cad_path, and through it the content's analysis and previews. Read-only: CAD
    # processing never writes listings, so it never moves their version.
    cad_file: Mapped['CadFile | None'] = relationship(primaryjoin='foreign(Listing.cad_path) == CadFile.name', viewonly=True, lazy='selectin')
    __table_args__ = (CheckConstraint('price_cents >= 0'), CheckConstraint("listing_type IN ('official','community')"), CheckConstraint("status IN ('draft','pending','approved','rejected','archived')"), Index('ix_listings_public', 'status', 'published_at'),
        Index('uq_listing_rack', 'owner_id', 'rack_hash', unique=True, sqlite_where=text('rack_hash IS NOT NULL'), postgresql_where=text('rack_hash IS NOT NULL')))
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
    # JSON snapshots validated by schemas.OrderInput (up to 1000 and 3000 characters).
    contact: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    total_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default='EUR')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    items: Mapped[list['OrderItem']] = relationship(cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('buyer_id', 'idempotency_key'), CheckConstraint("status IN ('pending','accepted','printing','ready','shipped','completed','cancelled')"), CheckConstraint('total_cents >= 0'))

class OrderItem(Base):
    manufacturing_dimensions: Mapped[str] = mapped_column(Text, default='[]', server_default='[]')
    # Colour key as purchased: a name, or name~rrggbb when hosts stock that name in several shades.
    color: Mapped[str] = mapped_column(String(48), default='', server_default='')
    # Display colour offered when the order was placed; '' for lines ordered before it was recorded.
    color_hex: Mapped[str] = mapped_column(String(7), default='', server_default='')
    # Manufacturing snapshot (see app/manufacturing.py): the listing revision and the exact,
    # immutable CAD file sold. cad_status: pinned | unverified (order predates versioning) | none | missing.
    listing_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cad_path: Mapped[str] = mapped_column(String(80), default='', server_default='')
    cad_sha256: Mapped[str] = mapped_column(String(64), default='', server_default='')
    cad_status: Mapped[str] = mapped_column(String(12), default='', server_default='')
    # A custom rack's full configuration, geometry, file references and report as sold. Never changed afterwards.
    rack_snapshot: Mapped[str] = mapped_column(Text, default='', server_default='')
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
    # Shipment entered by the host when marking the job shipped; the buyer then confirms receipt (completed).
    carrier: Mapped[str] = mapped_column(String(80), default='', server_default='')
    tracking_number: Mapped[str] = mapped_column(String(80), default='', server_default='')
    tracking_url: Mapped[str] = mapped_column(String(500), default='', server_default='')
    shipping_note: Mapped[str] = mapped_column(String(500), default='', server_default='')
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    item: Mapped[OrderItem] = relationship()
    __table_args__ = (CheckConstraint("status IN ('available','accepted','printing','ready','shipped','completed','cancelled')"),)

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

class AccountToken(Base):
    __tablename__ = 'account_tokens'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # The address an email_change token confirms.
    new_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    # Kept after use, so a reused link can be told from an unknown one.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class UserIdentity(Base):
    """An external sign-in linked to one internal account. subject is the provider's stable id, not an address."""
    __tablename__ = 'user_identities'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    provider: Mapped[str] = mapped_column(String(30))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(254), default='', server_default='')    # shown to the user only
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint('provider', 'subject', name='uq_identity_subject'), UniqueConstraint('user_id', 'provider', name='uq_identity_user_provider'))

class OAuthFlow(Base):
    """One sign-in attempt in progress: state (hashed), nonce and PKCE verifier stay on the server."""
    __tablename__ = 'oauth_flows'
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))
    nonce: Mapped[str] = mapped_column(String(100))
    code_verifier: Mapped[str] = mapped_column(String(128))
    browser_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=True)    # set when linking
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class EmailJob(Base):
    """One message to send (email_service). Holds no link and no body: those are made when it is sent."""
    __tablename__ = 'email_jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    recipient: Mapped[str] = mapped_column(String(254))
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    context: Mapped[str] = mapped_column(Text, default='{}', server_default='{}')
    status: Mapped[str] = mapped_column(String(12), default='pending', server_default='pending')  # pending sending sent failed cancelled
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(200), default='', server_default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index('ix_email_jobs_due', 'status', 'next_attempt_at'), Index('ix_email_jobs_recipient', 'recipient', 'kind', 'created_at'))

class UserAddress(Base):
    __tablename__ = 'user_addresses'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    label: Mapped[str] = mapped_column(String(40))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(40))
    country: Mapped[str] = mapped_column(String(2))
    city: Mapped[str] = mapped_column(String(150))
    region: Mapped[str] = mapped_column(String(150), default='')
    postal_code: Mapped[str] = mapped_column(String(30), default='')
    street: Mapped[str] = mapped_column(String(200))
    additional: Mapped[str] = mapped_column(String(200), default='')
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (Index('uq_default_address', 'user_id', unique=True, sqlite_where=text('is_default = 1'), postgresql_where=text('is_default')),)

class CartItem(Base):
    __tablename__='cart_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey('listings.id',ondelete='CASCADE'))
    material: Mapped[str] = mapped_column(String(200))
    color: Mapped[str] = mapped_column(String(48),default='')
    quantity: Mapped[int] = mapped_column(Integer)
    # Unit price the buyer last saw and accepted for this line; NULL for lines saved before prices
    # were recorded. Checkout refuses lines whose current price differs until the buyer accepts it.
    confirmed_unit_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__=(UniqueConstraint('user_id','listing_id','material','color'),CheckConstraint('quantity BETWEEN 1 AND 50'))

class Material(Base):
    __tablename__='materials'
    name: Mapped[str] = mapped_column(String(60),primary_key=True)
    technology: Mapped[str] = mapped_column(String(10))
class PrinterModel(Base):
    __tablename__='printer_models'
    id: Mapped[int] = mapped_column(primary_key=True)
    manufacturer: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    technology: Mapped[str] = mapped_column(String(10))
    x: Mapped[float|None] = mapped_column(Float,nullable=True)
    y: Mapped[float|None] = mapped_column(Float,nullable=True)
    z: Mapped[float|None] = mapped_column(Float,nullable=True)
    source: Mapped[str] = mapped_column(String(1000),default='')
    verified: Mapped[bool] = mapped_column(Boolean,default=False)
    materials: Mapped[str] = mapped_column(Text,default='[]')
    limitations: Mapped[str] = mapped_column(Text,default='')
    __table_args__=(UniqueConstraint('manufacturer','model'),CheckConstraint("technology IN ('FDM','RESIN')"))
class HostPrinter(Base):
    __tablename__='host_printers'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    model_id: Mapped[int|None] = mapped_column(ForeignKey('printer_models.id'),nullable=True)
    manufacturer: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    technology: Mapped[str] = mapped_column(String(10))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    z: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    # Legacy per-printer stock, kept only for downgrades; stock now lives in HostMaterial (migration 74a).
    materials: Mapped[str] = mapped_column(Text, default='[]')
    material_colors: Mapped[str] = mapped_column(Text, default='{}', server_default='{}')
    # Administrator-approved material capabilities of this printer.
    capabilities: Mapped[str] = mapped_column(Text, default='[]', server_default='[]')
    __table_args__=(CheckConstraint("technology IN ('FDM','RESIN')"),CheckConstraint('quantity BETWEEN 1 AND 100'),CheckConstraint('x>0 AND y>0 AND z>0'))

class HostMaterial(Base):
    """A material a host owns and its colours ({name: hex}), chosen once for all printers.
    A printer offers it when the material is also among that printer's approved capabilities."""
    __tablename__='host_materials'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    material: Mapped[str] = mapped_column(String(40))
    colors: Mapped[str] = mapped_column(Text, default='{}', server_default='{}')
    __table_args__=(UniqueConstraint('user_id','material'),)


class EquipmentRevision(Base):
    __tablename__ = 'equipment_revisions'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(20), default='draft', index=True)
    proposal: Mapped[str] = mapped_column(Text)
    before: Mapped[str] = mapped_column(Text)
    rejection_reason: Mapped[str] = mapped_column(String(1000), default='')
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (CheckConstraint("status IN ('draft','pending','approved','rejected')"),
        Index('uq_equipment_open_revision', 'user_id', unique=True, sqlite_where=text("status IN ('draft','pending')"), postgresql_where=text("status IN ('draft','pending')")))


class CustomRequest(Base):
    """A buyer's description of a tool to design or manufacture. Reviewed and quoted by administrators;
    never an order: no listing, price, host assignment or payment is created from it."""
    __tablename__ = 'custom_requests'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(120))
    application: Mapped[str] = mapped_column(Text)
    dimensions: Mapped[str] = mapped_column(Text)
    compatibility: Mapped[str] = mapped_column(Text, default='')
    quantity: Mapped[int] = mapped_column(Integer)
    material: Mapped[str] = mapped_column(String(60), default='')
    conditions: Mapped[str] = mapped_column(Text, default='[]')
    requirements: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(20), default='submitted', index=True)
    admin_notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    user: Mapped[User] = relationship()
    files: Mapped[list['CustomRequestFile']] = relationship(order_by='CustomRequestFile.id', cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('user_id', 'idempotency_key'), CheckConstraint('quantity BETWEEN 1 AND 10000'),
        CheckConstraint("status IN ('submitted','under_review','quoted','closed')"))

class CustomRequestFile(Base):
    __tablename__ = 'custom_request_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey('custom_requests.id', ondelete='CASCADE'), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(10))
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (CheckConstraint("kind IN ('model','image','document')"),)


class CadAsset(Base):
    """One unique CAD content (SHA-256 of the file bytes), however many files, listings or orders use it.
    Geometry analysis is stored here once; previews are cad_jobs results."""
    __tablename__ = 'cad_assets'
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    format: Mapped[str] = mapped_column(String(4))
    size_bytes: Mapped[int] = mapped_column(Integer)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)            # JSON from mesh.analyze
    analysis_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    jobs: Mapped[list['CadJob']] = relationship(order_by='CadJob.id', viewonly=True, lazy='joined')
    __table_args__ = (CheckConstraint("format IN ('stl','3mf')"), CheckConstraint('size_bytes >= 0'))

class CadFile(Base):
    """A file under uploads/cad. Names are immutable; older uploads have random names, so several files can
    hold the same content."""
    __tablename__ = 'cad_files'
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    sha256: Mapped[str] = mapped_column(ForeignKey('cad_assets.sha256', ondelete='RESTRICT'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    asset: Mapped[CadAsset] = relationship(lazy='joined', innerjoin=True)

class CadJob(Base):
    """A processing stage for one content and one stage version (cache_key): the durable work queue and the
    cache index at once. A ready row is reused by every file, listing and page with that content."""
    __tablename__ = 'cad_jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(ForeignKey('cad_assets.sha256', ondelete='RESTRICT'))
    kind: Mapped[str] = mapped_column(String(12))
    cache_key: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(12), default='queued', server_default='queued')
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    output_dir: Mapped[str] = mapped_column(String(64), default='', server_default='')   # under uploads/renders
    result: Mapped[str] = mapped_column(Text, default='{}', server_default='{}')
    last_error: Mapped[str] = mapped_column(String(500), default='', server_default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint('sha256', 'kind', 'cache_key', name='uq_cad_job_stage'),
        CheckConstraint("kind IN ('analyze','render')"), CheckConstraint("status IN ('queued','processing','ready','failed')"),
        Index('ix_cad_jobs_due', 'status', 'next_attempt_at'))


class RackDesign(Base):
    """A buyer's saved rack, a draft that can always be edited. What was sold is a separate immutable record: the
    private listing and the order line's snapshot, which later edits here never reach."""
    __tablename__ = 'rack_designs'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(80))
    config: Mapped[str] = mapped_column(Text)
    config_hash: Mapped[str] = mapped_column(String(64), default='', server_default='')     # '' while it has problems
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class RackBuild(Base):
    """The queue and cache of CAD builds, one row per distinct geometry (see app/rack/queue.py)."""
    __tablename__ = 'rack_builds'
    config_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    spec: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default='queued', server_default='queued')
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    result: Mapped[str] = mapped_column(Text, default='{}', server_default='{}')
    last_error: Mapped[str] = mapped_column(String(500), default='', server_default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("status IN ('queued','processing','ready','failed','abandoned')"), Index('ix_rack_builds_due', 'status', 'next_attempt_at'))

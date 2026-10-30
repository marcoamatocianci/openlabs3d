from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.database import Base
from app.main import app  # Initialize shared routes before importing equipment.
from app.equipment import CATALOGUE, seed_equipment
from app.models import PrinterModel


def test_catalogue_is_idempotent_and_refreshes_verified_models():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_equipment(db)
        printers = db.scalars(select(PrinterModel)).all()
        assert len(printers) == len(CATALOGUE)
        assert len({(p.manufacturer, p.model) for p in printers}) == len(printers)
        p = db.scalar(select(PrinterModel).where(PrinterModel.manufacturer == 'Bambu Lab', PrinterModel.model == 'A1'))
        original_id = p.id
        p.x = 1
        db.commit()
        seed_equipment(db)
        db.refresh(p)
        assert (p.id, p.x, p.y, p.z) == (original_id, 256, 256, 256)
        assert db.scalar(select(PrinterModel).where(PrinterModel.manufacturer == 'Elegoo', PrinterModel.model == 'Neptune 4 Plus')).z == 385
        assert len(db.scalars(select(PrinterModel)).all()) == len(CATALOGUE)


def test_catalogue_does_not_overwrite_unverified_host_suggestions():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        p = PrinterModel(manufacturer='Bambu Lab', model='A1', technology='FDM', x=123, y=123, z=123, verified=False, materials='[]', source='Host suggestion')
        db.add(p)
        db.commit()
        seed_equipment(db)
        db.refresh(p)
        assert p.x == 123 and not p.verified and p.source == 'Host suggestion'

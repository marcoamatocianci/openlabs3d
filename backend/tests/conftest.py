"""Shared fixtures.

OPENLABS3D_TEST_POSTGRES_URL=postgresql+psycopg://... runs the in-process suite against PostgreSQL instead of
SQLite. Test modules point DATABASE_URL at their own SQLite file when imported; in PostgreSQL mode those
assignments are redirected to the given database, which is emptied first. Subprocess tests that pass an
explicit SQLite URL in their own environment (the Alembic chain, seeding scripts) keep using SQLite.
"""
import os
import pytest

POSTGRES_URL = os.environ.get('OPENLABS3D_TEST_POSTGRES_URL')
if POSTGRES_URL:
    from sqlalchemy import create_engine, text
    with create_engine(POSTGRES_URL).begin() as connection:
        connection.execute(text('DROP SCHEMA public CASCADE; CREATE SCHEMA public; CREATE EXTENSION IF NOT EXISTS citext'))

    class _Environ(type(os.environ)):
        def __setitem__(self, key, value):
            super().__setitem__(key, POSTGRES_URL if key == 'DATABASE_URL' and str(value).startswith('sqlite') else value)
        def setdefault(self, key, value=None):
            if key not in self: self[key] = value
            return self[key]
    os.environ.__class__ = _Environ
    os.environ['DATABASE_URL'] = POSTGRES_URL

@pytest.fixture(autouse=True)
def reset_rate_limit_between_tests():
    from app.main import rate
    rate.clear()
    yield
    rate.clear()

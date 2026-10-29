import getpass
from pydantic import ValidationError
from sqlalchemy import select
from .database import SessionLocal
from .models import User
from .main import hasher
from .schemas import Register

def check_utf8(*values):
    try:
        for value in values:
            value.encode('utf-8')
    except UnicodeEncodeError:
        raise SystemExit('Input contains invalid text encoding. Use a UTF-8 terminal and retype the values; no account was changed.') from None

def main():
    email = input('Administrator email: ').strip().lower()
    name = input('Display name: ').strip()
    username = input('Username (3–32 letters, numbers, underscores): ').strip()
    password = getpass.getpass('Password (8+ characters, uppercase and number): ')
    check_utf8(email, name, username, password)
    try:
        validated = Register(email=email, username=username, display_name=name, password=password)
    except ValidationError:
        raise SystemExit('Invalid name, email, or password length.')
    confirmation = getpass.getpass('Confirm password: ')
    check_utf8(confirmation)
    if password != confirmation: raise SystemExit('Passwords do not match.')
    with SessionLocal() as db:
        email = str(validated.email).lower()
        if db.scalar(select(User).where(User.email == email)): raise SystemExit('This email is already registered. No account was changed.')
        db.add(User(email=email, username=username, display_name=name, password_hash=hasher.hash(password), role='admin')); db.commit()
    print('Administrator created.')
if __name__ == '__main__': main()

import os
from pathlib import Path

APP_ENV = os.getenv('APP_ENV', 'development')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:////app/data/openlabs3d.db')
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', '/app/data/uploads')) / 'products'
MAX_UPLOAD = max(1, min(5, int(os.getenv('MAX_UPLOAD_SIZE_MB', '5')))) * 1024 * 1024
MAX_IMAGES = max(1, min(5, int(os.getenv('MAX_IMAGES_PER_LISTING', '5'))))
SECURE_COOKIE = APP_ENV == 'production'

# Links in email always use this address, never a request header. PUBLIC_BASE_URL is the older name for it.
APP_PUBLIC_URL = (os.getenv('APP_PUBLIC_URL') or os.getenv('PUBLIC_BASE_URL') or 'http://localhost:8080').rstrip('/')
EMAIL_VERIFICATION_EXPIRY_HOURS = max(1, int(os.getenv('EMAIL_VERIFICATION_EXPIRY_HOURS', '24')))
PASSWORD_RESET_EXPIRY_MINUTES = max(5, int(os.getenv('PASSWORD_RESET_EXPIRY_MINUTES', '60')))
EMAIL_RESEND_COOLDOWN_SECONDS = max(1, int(os.getenv('EMAIL_RESEND_COOLDOWN_SECONDS', '60')))
EMAIL_RESEND_HOURLY_LIMIT = max(1, int(os.getenv('EMAIL_RESEND_HOURLY_LIMIT', '5')))
# A sign-up never confirmed gives up its username and address after this long.
UNVERIFIED_ACCOUNT_RETENTION_DAYS = max(1, int(os.getenv('UNVERIFIED_ACCOUNT_RETENTION_DAYS', '7')))

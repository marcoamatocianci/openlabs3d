import os
from pathlib import Path

APP_ENV = os.getenv('APP_ENV', 'development')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:////app/data/openlabs3d.db')
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', '/app/data/uploads')) / 'products'
MAX_UPLOAD = max(1, min(5, int(os.getenv('MAX_UPLOAD_SIZE_MB', '5')))) * 1024 * 1024
MAX_IMAGES = max(1, min(5, int(os.getenv('MAX_IMAGES_PER_LISTING', '5'))))
SECURE_COOKIE = APP_ENV == 'production'

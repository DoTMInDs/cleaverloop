from .base import *

DEBUG = True
ALLOWED_HOSTS = ['*']

# Database
# Parses DATABASE_URL or defaults to SQLite with WAL mode
DATABASES = {
    'default': env.db_url('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}

# If SQLite is used, ensure WAL mode is activated on connections
if DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
    DATABASES['default']['OPTIONS'] = {
        'timeout': 30,  # 30-second busy timeout
    }

# CORS settings for local testing
CORS_ALLOW_ALL_ORIGINS = True

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# For local development with WhiteNoise, don't manifest hash static files to avoid missing file errors
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Execute Celery tasks synchronously in local development if worker is not started
CELERY_TASK_ALWAYS_EAGER = env.bool('CELERY_TASK_ALWAYS_EAGER', default=True)
CELERY_TASK_EAGER_PROPAGATES = True

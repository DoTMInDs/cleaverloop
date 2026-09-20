from .base import *

DEBUG = False

# Database
DATABASES = {
    'default': env.db_url('DATABASE_URL')
}

# PostgreSQL connection health and pooling
DATABASES['default']['CONN_MAX_AGE'] = 600
DATABASES['default']['CONN_HEALTH_CHECKS'] = True

# Security Settings
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# WhiteNoise production storage
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STORAGES['staticfiles'] = {
    'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
}

# Runtime security validations
import sys
if any(cmd in sys.argv for cmd in ('runserver', 'gunicorn', 'uvicorn', 'daphne')):
    from django.core.exceptions import ImproperlyConfigured
    if not SECRET_KEY or SECRET_KEY.startswith('django-insecure-'):
        raise ImproperlyConfigured("Insecure default SECRET_KEY detected. Set a dedicated random SECRET_KEY in your environment.")
    if '*' in ALLOWED_HOSTS:
        raise ImproperlyConfigured("ALLOWED_HOSTS cannot contain wildcard '*' in production.")

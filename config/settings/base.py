import os
from pathlib import Path
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Initialize environ
env = environ.Env(
    DEBUG=(bool, False),
    MOCK_PROVIDERS_ENABLED=(bool, True),
    STORAGE_BACKEND=(str, 'local'),
    DEFAULT_STARTER_CREDITS=(int, 500),
    CREDIT_COST_IMAGE_STANDARD=(int, 50),
    CREDIT_COST_VIDEO_PER_SEC=(int, 50),
    MAX_AGENT_CREDITS_PER_REQUEST=(int, 2500),
    MAX_SCENES_PER_REQUEST=(int, 6),
)

# Read .env file if it exists
env_file = BASE_DIR / '.env'
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env('SECRET_KEY', default='django-insecure-cleverloop-fallback-secret-key-12345')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*'])

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'corsheaders',
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.credits',
    'apps.billing',
    'apps.media',
    'apps.characters',
    'apps.projects',
    'apps.providers',
    'apps.generations',
    'apps.studio',
    'apps.editor',
    'apps.ai',
    'apps.adminpanel',
    'apps.analytics',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.analytics.middleware.CorrelationIDMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.credits.context_processors.credit_wallet',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework Settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# Celery Broker & Settings
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default='redis://127.0.0.1:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 mins hard limit

# Force Redis protocol 2 (RESP2) for universal compatibility with all Redis versions
CELERY_BROKER_TRANSPORT_OPTIONS = {'protocol': 2}
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {'protocol': 2}

# Object Storage Backend Settings
STORAGE_BACKEND = env('STORAGE_BACKEND', default='local')
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='auto')
AWS_S3_ENDPOINT_URL = env('AWS_S3_ENDPOINT_URL', default='')

# AI Provider API Keys
MOCK_PROVIDERS_ENABLED = env.bool('MOCK_PROVIDERS_ENABLED', default=True)
ALLOW_MOCK_FALLBACK = env.bool('ALLOW_MOCK_FALLBACK', default=True)

# Google AI Studio - Generative Media (Veo 3.1 & Imagen 3)
GOOGLE_AI_API_KEY = env('GOOGLE_AI_API_KEY', default='')

# Google AI Studio - Reasoning LLM (Super Agent Storyboard Planner)
GEMINI_API_KEY = env('GEMINI_API_KEY', default='')
AGENT_LLM_PROVIDER = env('AGENT_LLM_PROVIDER', default='gemini')

# Video & Image Commercial Providers
KLING_API_KEY = env('KLING_API_KEY', default='')
SEEDANCE_API_KEY = env('SEEDANCE_API_KEY', default='')
ALIBABA_API_KEY = env('ALIBABA_API_KEY', default='')
OPENAI_API_KEY = env('OPENAI_API_KEY', default='')
FLUX_API_KEY = env('FLUX_API_KEY', default='')
MINIMAX_API_KEY = env('MINIMAX_API_KEY', default='')
FAL_KEY = env('FAL_KEY', default='')

# Platform Economics Configuration
DEFAULT_STARTER_CREDITS = env('DEFAULT_STARTER_CREDITS', default=500)
CREDIT_COST_IMAGE_STANDARD = env('CREDIT_COST_IMAGE_STANDARD', default=50)
CREDIT_COST_VIDEO_PER_SEC = env('CREDIT_COST_VIDEO_PER_SEC', default=50)
MAX_AGENT_CREDITS_PER_REQUEST = env('MAX_AGENT_CREDITS_PER_REQUEST', default=2500)
MAX_SCENES_PER_REQUEST = env('MAX_SCENES_PER_REQUEST', default=6)

# Login / Logout Redirects
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'studio:dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

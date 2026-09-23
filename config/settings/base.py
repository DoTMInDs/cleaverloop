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
    MAX_AGENT_CREDITS_PER_REQUEST=(int, 500000),
    MAX_SCENES_PER_REQUEST=(int, 6),
    PAYMENT_PROVIDER=(str, 'mock'),
    PAYSTACK_PUBLIC_KEY=(str, ''),
    PAYSTACK_SECRET_KEY=(str, ''),
    PAYSTACK_CURRENCY=(str, 'USD'),
)

# Read .env file if it exists
env_file = BASE_DIR / '.env'
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env('SECRET_KEY', default='django-insecure-cleaverloop-fallback-secret-key-12345')
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
    'django.contrib.humanize',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'corsheaders',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.apple',
    "tailwind",
    "theme",
    'storages',
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
    'apps.voices',
    'apps.adminpanel',
    'apps.analytics',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS
TAILWIND_APP_NAME = "theme"
NPM_BIN_PATH = "npm.cmd"

if DEBUG:
    # Add django_browser_reload only in DEBUG mode
    INSTALLED_APPS += ["django_browser_reload"]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.analytics.middleware.CorrelationIDMiddleware',
]

if DEBUG:
    # Add django_browser_reload middleware only in DEBUG mode
    MIDDLEWARE += [
        "django_browser_reload.middleware.BrowserReloadMiddleware",
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

# Caches configuration (Distributed Redis with test isolation)
import sys
REDIS_CACHE_URL = env('REDIS_CACHE_URL', default=env('REDIS_URL', default='redis://127.0.0.1:6379/1'))

if 'test' in sys.argv or env.bool('USE_LOCMEM_CACHE', default=False):
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'test-cleaverloop-cache',
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_CACHE_URL,
            'OPTIONS': {
                'protocol': 2,  # Force RESP2 for universal Redis compatibility (including Windows & older Redis instances)
            },
            'TIMEOUT': 300,
            'KEY_PREFIX': 'cleaverloop',
        }
    }

# Cached database sessions (Sub-millisecond Redis session reads with reliable DB write-through)
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'


# Object Storage Backend Settings
STORAGE_BACKEND = env('STORAGE_BACKEND', default='local')
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='us-east-1')
AWS_S3_ENDPOINT_URL = env('AWS_S3_ENDPOINT_URL', default='')
AWS_QUERYSTRING_AUTH = env.bool('AWS_QUERYSTRING_AUTH', default=False)

if STORAGE_BACKEND == 's3' and AWS_STORAGE_BUCKET_NAME:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {
                "access_key": AWS_ACCESS_KEY_ID,
                "secret_key": AWS_SECRET_ACCESS_KEY,
                "bucket_name": AWS_STORAGE_BUCKET_NAME,
                "region_name": AWS_S3_REGION_NAME if AWS_S3_REGION_NAME != 'auto' else None,
                "endpoint_url": AWS_S3_ENDPOINT_URL if AWS_S3_ENDPOINT_URL else None,
                "default_acl": None,
                "querystring_auth": AWS_QUERYSTRING_AUTH,
                "file_overwrite": False,
            },
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    if not AWS_QUERYSTRING_AUTH:
        region_segment = f".{AWS_S3_REGION_NAME}" if AWS_S3_REGION_NAME and AWS_S3_REGION_NAME != 'auto' else ""
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3{region_segment}.amazonaws.com/"
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

# AI Provider API Keys (Unified Single Google AI / Gemini Key)
MOCK_PROVIDERS_ENABLED = env.bool('MOCK_PROVIDERS_ENABLED', default=True)
ALLOW_MOCK_FALLBACK = env.bool('ALLOW_MOCK_FALLBACK', default=True)

# Single Unified Google Gemini Key for all Multimodal, Video (Veo), Image (Nano Banana), and Reasoning
GEMINI_API_KEY = env('GEMINI_API_KEY', default='') or env('GOOGLE_AI_API_KEY', default='') or env('GOOGLE_API_KEY', default='')
GOOGLE_AI_API_KEY = GEMINI_API_KEY
AGENT_LLM_PROVIDER = env('AGENT_LLM_PROVIDER', default='gemini')

# Video & Image Commercial Providers (Optional Third-Party Fallbacks)
KLING_API_KEY = env('KLING_API_KEY', default='')
SEEDANCE_API_KEY = env('SEEDANCE_API_KEY', default='')
ALIBABA_API_KEY = env('ALIBABA_API_KEY', default='')
OPENAI_API_KEY = env('OPENAI_API_KEY', default='')
FLUX_API_KEY = env('FLUX_API_KEY', default='')
MINIMAX_API_KEY = env('MINIMAX_API_KEY', default='')
FAL_KEY = env('FAL_KEY', default='')
ELEVENLABS_API_KEY = env('ELEVENLABS_API_KEY', default='') or env('ELEVEN_API_KEY', default='')

# Payment & Billing Configuration (Paystack)
PAYMENT_PROVIDER = env('PAYMENT_PROVIDER', default='mock')
PAYSTACK_PUBLIC_KEY = env('PAYSTACK_PUBLIC_KEY', default='')
PAYSTACK_SECRET_KEY = env('PAYSTACK_SECRET_KEY', default='')
PAYSTACK_CURRENCY = env('PAYSTACK_CURRENCY', default='GHS')
USD_TO_GHS_RATE = env('USD_TO_GHS_RATE', default='auto')

# Platform Economics Configuration (Flashloop Benchmark)
DEFAULT_STARTER_CREDITS = env.int('DEFAULT_STARTER_CREDITS', default=500)
CREDIT_COST_VOICE_CLONE = env.int('CREDIT_COST_VOICE_CLONE', default=50)
SUBSCRIPTION_PLANS = {
    'free': {
        'name': 'Free Trial',
        'price_monthly': 0,
        'credits': 500,
        'has_unlimited': False,
        'max_concurrency': 1,
    },
    'starter': {
        'name': 'Starter',
        'price_monthly': 19,
        'price_annual_monthly_equiv': 15,
        'credits': 90000,
        'has_unlimited': False,
        'max_concurrency': 1,
    },
    'creator': {
        'name': 'Creator',
        'price_monthly': 59,
        'price_annual_monthly_equiv': 49,
        'credits': 400000,
        'has_unlimited': True,
        'max_concurrency': 2,
    },
    'ultra': {
        'name': 'Ultra / Pro',
        'price_monthly': 129,
        'price_annual_monthly_equiv': 99,
        'credits': 1000000,
        'has_unlimited': True,
        'max_concurrency': 4,
    },
}
CREDIT_COST_IMAGE_STANDARD = env.int('CREDIT_COST_IMAGE_STANDARD', default=50)
CREDIT_COST_VIDEO_PER_SEC = env.int('CREDIT_COST_VIDEO_PER_SEC', default=50)
MAX_AGENT_CREDITS_PER_REQUEST = env.int('MAX_AGENT_CREDITS_PER_REQUEST', default=500000)
MAX_SCENES_PER_REQUEST = env.int('MAX_SCENES_PER_REQUEST', default=6)

# Login / Logout Redirects
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'studio:dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

# Authentication Backends (Django default + allauth)
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# django-allauth Configuration
ACCOUNT_USER_MODEL_USERNAME_FIELD = 'username'
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_DEFAULT_HTTP_PROTOCOL = env('ACCOUNT_DEFAULT_HTTP_PROTOCOL', default='http')
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_ADAPTER = 'apps.accounts.adapters.CustomSocialAccountAdapter'


# Google and Apple Social Account Provider Configuration
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': env('GOOGLE_OAUTH_CLIENT_ID', default=''),
            'secret': env('GOOGLE_OAUTH_CLIENT_SECRET', default=''),
            'key': '',
        },
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
    },
    'apple': {
        'APP': {
            'client_id': env('APPLE_OAUTH_CLIENT_ID', default=''),
            'secret': env('APPLE_OAUTH_TEAM_ID', default=env('APPLE_OAUTH_SECRET_KEY', default='')),
            'key': env('APPLE_OAUTH_KEY_ID', default=''),
            'settings': {
                'certificate_key': env('APPLE_OAUTH_CERTIFICATE_KEY', default=env('APPLE_OAUTH_SECRET_KEY', default='')),
            },
        },
        'SCOPE': ['email', 'name'],
    },

}


import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# -----------------------------------------------------------------------------
# Base settings (shared by local.py and production.py)
# -----------------------------------------------------------------------------

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'dev-only-insecure-key-do-not-use-in-production'
)

DEBUG = False

# -----------------------------------------------------------------------------
# Custom user model
# -----------------------------------------------------------------------------

AUTH_USER_MODEL = 'account.MyUser'

# -----------------------------------------------------------------------------
# Installed apps
# -----------------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',


    'account',
    'django_recaptcha',

    "imagekit",

    "home.apps.HomeConfig",

]

# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',


]



ROOT_URLCONF = 'garagelions.urls'

# -----------------------------------------------------------------------------
# Templates
# -----------------------------------------------------------------------------

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'home.context_processors.footer_video_reviews',
            ],
        },
    },
]

WSGI_APPLICATION = 'garagelions.wsgi.application'

# -----------------------------------------------------------------------------
# Password validation
# -----------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# -----------------------------------------------------------------------------
# Internationalization
# -----------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# -----------------------------------------------------------------------------
# Static & Media settings (overridden in production)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Static & Media settings (shared)
# -----------------------------------------------------------------------------

STATIC_URL = '/static/'

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# -----------------------------------------------------------------------------
# Upload limits / safety
# - Big files will stream to disk once they exceed FILE_UPLOAD_MAX_MEMORY_SIZE.
# - Nginx must ALSO allow the max upload size (client_max_body_size).
# -----------------------------------------------------------------------------

# Keep memory usage reasonable while still allowing large videos
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024      # 25MB (POST data)
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024      # 25MB (file buffering)




# -----------------------------------------------------------------------------
# Email (overridden in production)
# -----------------------------------------------------------------------------

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_USE_TLS = True
EMAIL_PORT = 587
EMAIL_HOST_USER = ''  # override in production.py or local.py
EMAIL_HOST_PASSWORD = ''  # override in production.py or local.py
DEFAULT_FROM_EMAIL = "PC New Lead <info@garagelions.com>"
# -----------------------------------------------------------------------------
# Default primary key
# -----------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


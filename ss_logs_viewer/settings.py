import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-9=&xp_9x+mjc56-1-s%frs9g(9x_^#2pamuc79z@othdsz_@=g')

DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
CSRF_TRUSTED_ORIGINS = [
    h if h.startswith('http') else f'https://{h}'
    for h in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if h
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'logs',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'ss_logs_viewer.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ss_logs_viewer.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    },
    'wms': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'wms_postgres',
        'USER': 'wms_postgres_user',
        'PASSWORD': os.environ.get('WMS_DB_PASSWORD', ''),
        'HOST': os.environ.get('WMS_DB_HOST', 'dpg-d44bkkbe5dus73b02p5g-a.frankfurt-postgres.render.com'),
        'PORT': '5432',
        'OPTIONS': {
            'sslmode': 'require',
        },
    },
}

DATABASE_ROUTERS = ['logs.db_router.WmsRouter']

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# SoStocked API credentials (env vars for production, fallback to files for local dev)
SS_LOGS_DIR = os.environ.get('SS_LOGS_DIR', '/home/nikilko-user/ss-logs')
SS_CLIENT_ID = os.environ.get('SS_CLIENT_ID', '')
SS_CLIENT_SECRET = os.environ.get('SS_CLIENT_SECRET', '')
SS_ACCOUNT_ID = os.environ.get('SS_ACCOUNT_ID', '')
SS_BEARER_TOKEN = os.environ.get('SS_BEARER_TOKEN', '')

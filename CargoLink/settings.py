import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Charge les variables .env à la racine (ou à côté de settings.py),
# sans écraser les variables déjà définies dans l'environnement.
for _env_file in (BASE_DIR / '.env', BASE_DIR / 'CargoLink' / '.env'):
    if _env_file.exists():
        for _line in _env_file.read_text(encoding='utf-8').splitlines():
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _key, _value = _line.split('=', 1)
                os.environ.setdefault(_key.strip(), _value.strip().strip('"\''))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "localhost,127.0.0.1",
    ).split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "",
    ).split(",")
    if origin.strip()
]

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'authentification.apps.AuthentificationConfig',
    'vehicules',
    'demandes.apps.DemandesConfig',
    'gestion_trajets_offres.apps.GestionTrajetsOffresConfig',
    'suivi_transport.apps.SuiviTransportConfig',
    'avis_reclamations.apps.AvisReclamationsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'CargoLink.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'CargoLink.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["PGDATABASE"],
        "USER": os.environ["PGUSER"],
        "PASSWORD": os.environ["PGPASSWORD"],
        "HOST": os.environ["PGHOST"],
        "PORT": os.getenv("PGPORT", "5432"),
        "OPTIONS": {
            "sslmode": "require",
            "channel_binding": "require",
        },
    }
}


# Password validation
AUTH_USER_MODEL = 'authentification.User'

# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [BASE_DIR / "static"]

# Gemini is called only from the server; never expose this key in browser code.
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', '').strip() or 'gemini-2.5-flash'

# Celery & Broker configuration (facultatif : le projet démarre sans ces packages)
# Installer : uv add celery redis
# Lancer (Windows) : uv run celery -A CargoLink worker -P solo -l info
# Beat : uv run celery -A CargoLink beat -l info
# Redis (WSL / Docker) : docker run -p 6379:6379 redis:alpine
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://127.0.0.1:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
# Fuseau Tunisie cohérent avec TIME_ZONE (UTC) + USE_TZ=True :
# Celery convertit les heures en UTC en interne ; le beat_schedule est exprimé en Africa/Tunis.
CELERY_TIMEZONE = 'Africa/Tunis'
CELERY_TASK_TRACK_STARTED = True

# Pause entre requêtes IA pour respecter le quota gratuit Gemini (secondes)
IA_RISQUE_PAUSE_SECONDS = float(os.environ.get('IA_RISQUE_PAUSE_SECONDS', '6'))


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

_mail_user = os.environ.get('EMAIL_HOST_USER', '').strip()
# Google affiche le mot de passe d'application par groupes de 4 : on retire les espaces.
_mail_password = ''.join(os.environ.get('EMAIL_HOST_PASSWORD', '').split())
DEFAULT_FROM_EMAIL = f'CargoLink <{_mail_user}>' if _mail_user else 'CargoLink <no-reply@cargolink.local>'

if _mail_user and _mail_password:
    # Gmail SMTP (mot de passe d'application défini dans .env)
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'OPTIONS': {
                'host': 'smtp.gmail.com',
                'port': 587,
                'use_tls': True,
                'username': _mail_user,
                'password': _mail_password,
                'timeout': 15,
            },
        },
    }
else:
    # Sans identifiants, les e-mails s'affichent dans la console.
    if _mail_password and not _mail_user:
        print("ATTENTION : EMAIL_HOST_USER est vide dans .env, aucun e-mail ne sera envoyé (affichage console).")
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.console.EmailBackend',
        },
    }

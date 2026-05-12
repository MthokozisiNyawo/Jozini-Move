import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Basic Flask Config
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY and os.environ.get('FLASK_ENV') != 'production':
        SECRET_KEY = 'dev-secret-key-for-development-only-do-not-use-in-production'
        print("WARNING: Using default SECRET_KEY for development. DO NOT use in production!")
    elif not SECRET_KEY:
        raise ValueError("SECRET_KEY must be set in environment variables for production")
    
    # Database - Handle SQLite specially
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        database_url = 'sqlite:///jozini_move.db'
    
    # SQLite doesn't support connection pooling options
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Only add engine options for non-SQLite databases
    if not database_url.startswith('sqlite'):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': 10,
            'pool_recycle': 3600,
            'pool_pre_ping': True,
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {}
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = os.environ.get('REMEMBER_COOKIE_SECURE', 'False').lower() == 'true'
    REMEMBER_COOKIE_HTTPONLY = True
    
    # Upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    UPLOAD_FOLDER = 'app/static/uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    
    # App settings
    APP_NAME = "Jozini Move"
    APP_VERSION = "1.0.0"
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')
    
    # Delivery settings
    DELIVERY_FEE = 20.00
    SERVICE_FEE = 5.00
    DRIVER_PERCENTAGE = 0.7
    
    # SMS (Africa's Talking)
    SMS_ENABLED = os.environ.get('SMS_ENABLED', 'False').lower() == 'true'
    AFRICAS_TALKING_USERNAME = os.environ.get('AFRICAS_TALKING_USERNAME')
    AFRICAS_TALKING_API_KEY = os.environ.get('AFRICAS_TALKING_API_KEY')
    
    # Email (SendGrid)
    EMAIL_ENABLED = os.environ.get('EMAIL_ENABLED', 'False').lower() == 'true'
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
    DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@jozinimove.co.za')
    
    # Payment (PayFast for South Africa)
    PAYMENT_ENABLED = os.environ.get('PAYMENT_ENABLED', 'False').lower() == 'true'
    PAYFAST_MERCHANT_ID = os.environ.get('PAYFAST_MERCHANT_ID')
    PAYFAST_MERCHANT_KEY = os.environ.get('PAYFAST_MERCHANT_KEY')
    PAYFAST_PASSPHRASE = os.environ.get('PAYFAST_PASSPHRASE')
    PAYFAST_TEST_MODE = os.environ.get('PAYFAST_TEST_MODE', 'True').lower() == 'true'
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'logs/app.log')
    
    # Admin
    admin_emails = os.environ.get('ADMIN_EMAILS', '')
    ADMIN_EMAILS = [email.strip() for email in admin_emails.split(',') if email.strip()]
    
    # Rate Limiting - Disable for development
    RATELIMIT_ENABLED = os.environ.get('RATELIMIT_ENABLED', 'False').lower() == 'true'
    RATELIMIT_DEFAULT = "100/hour"
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')
    
    # Cache - Use simple cache for development
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'SimpleCache')
    CACHE_DEFAULT_TIMEOUT = 300
    # Disable Redis for development
    if CACHE_TYPE == 'RedisCache' and not os.environ.get('REDIS_URL'):
        CACHE_TYPE = 'SimpleCache'
        print("Redis not configured, using SimpleCache instead")

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    PAYFAST_TEST_MODE = True
    RATELIMIT_ENABLED = False
    # Use simple cache in development
    CACHE_TYPE = 'SimpleCache'

class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL', 'sqlite:///:memory:')
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    CACHE_TYPE = 'SimpleCache'

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    RATELIMIT_ENABLED = True
    # Use Redis in production if available
    if os.environ.get('REDIS_URL'):
        CACHE_TYPE = 'RedisCache'
        CACHE_REDIS_URL = os.environ.get('REDIS_URL')

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
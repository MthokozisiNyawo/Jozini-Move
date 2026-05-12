# IMPORTANT: Monkey patch must be FIRST before any flask_login imports
import sys
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

# Add parent directory to path to import config
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Monkey patch werkzeug.urls to add missing functions for Flask-Login compatibility
import werkzeug.urls
from urllib.parse import parse_qs, unquote_plus, urlencode as _urlencode

# Add url_decode function (missing in newer Werkzeug versions)
def _url_decode(s, charset='utf-8', decode_keys=False, include_empty=True, 
                errors='replace', separator='&', cls=None):
    """Compatibility wrapper for url_decode"""
    if isinstance(s, bytes):
        s = s.decode(charset)
    result = {}
    if not s:
        return result
    pairs = s.split(separator)
    for pair in pairs:
        if not pair and not include_empty:
            continue
        if '=' in pair:
            key, value = pair.split('=', 1)
        else:
            key, value = pair, ''
        key = unquote_plus(key).encode('latin1').decode(charset, errors)
        if decode_keys:
            key = key.encode('latin1').decode(charset, errors)
        value = unquote_plus(value).encode('latin1').decode(charset, errors) if value else ''
        if key in result:
            result[key].append(value)
        else:
            result[key] = [value]
    return result

# Add url_encode function (missing in newer Werkzeug versions)
def _url_encode(query, charset='utf-8', sort=False, key=None, separator='&', cls=None):
    """Compatibility wrapper for url_encode"""
    if isinstance(query, dict):
        query = list(query.items())
    elif hasattr(query, 'items'):
        query = list(query.items())
    
    if sort:
        query = sorted(query, key=key)
    
    return _urlencode(query, doseq=True)

# Add the functions to werkzeug.urls if they don't exist
if not hasattr(werkzeug.urls, 'url_decode'):
    werkzeug.urls.url_decode = _url_decode
if not hasattr(werkzeug.urls, 'url_encode'):
    werkzeug.urls.url_encode = _url_encode

# Also patch the module directly for any direct imports
sys.modules['werkzeug.urls'].url_decode = _url_decode
sys.modules['werkzeug.urls'].url_encode = _url_encode

# Now safe to import Flask extensions
from flask import Flask, render_template, request, flash, url_for, redirect, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_talisman import Talisman
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Import config - now with proper path
from config import config

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
cache = Cache()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

def create_app(config_name=None):
    """Application factory pattern"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Configure session security
    app.config.update(
        SESSION_COOKIE_SECURE=app.config.get('SESSION_COOKIE_SECURE', False),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        REMEMBER_COOKIE_SECURE=app.config.get('REMEMBER_COOKIE_SECURE', False),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_DURATION=app.config.get('PERMANENT_SESSION_LIFETIME')
    )
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    # Initialize cache with error handling (disable Redis if not available)
    try:
        cache.init_app(app)
    except Exception as e:
        print(f"Warning: Cache initialization failed: {e}. Using dummy cache.")
        app.config['CACHE_TYPE'] = 'SimpleCache'
        cache.init_app(app)
    
    # Initialize limiter with error handling
    try:
        limiter.init_app(app)
    except Exception as e:
        print(f"Warning: Rate limiter initialization failed: {e}. Limiter disabled.")
        app.config['RATELIMIT_ENABLED'] = False
    
    # Security middleware for production only
    if config_name == 'production':
        Talisman(app, 
                content_security_policy={
                    'default-src': "'self'",
                    'script-src': ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", "https://code.jquery.com"],
                    'style-src': ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", "https://fonts.googleapis.com"],
                    'font-src': ["'self'", "https://cdn.jsdelivr.net", "https://fonts.gstatic.com"],
                    'img-src': ["'self'", "data:", "https:"],
                    'connect-src': ["'self'"],
                    'frame-src': ["'none'"],
                    'object-src': ["'none'"],
                },
                force_https=True,
                strict_transport_security=True,
                strict_transport_security_max_age=31536000,
                frame_options='DENY')
        
        CORS(app, resources={r"/api/*": {"origins": app.config['APP_URL']}})
    
    # Login manager configuration
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'
    login_manager.refresh_view = 'auth.login'
    login_manager.needs_refresh_message = 'Please log in again to confirm your identity.'
    login_manager.needs_refresh_message_category = 'info'
    
    # Register blueprints
    try:
        from app.routes import main_bp, auth_bp, shop_bp, order_bp, driver_bp, admin_bp, api_bp
        
        app.register_blueprint(main_bp)
        app.register_blueprint(auth_bp, url_prefix='/auth')
        app.register_blueprint(shop_bp, url_prefix='/shop')
        app.register_blueprint(order_bp, url_prefix='/orders')
        app.register_blueprint(driver_bp, url_prefix='/driver')
        app.register_blueprint(admin_bp, url_prefix='/admin')
        app.register_blueprint(api_bp, url_prefix='/api/v1')
    except ImportError as e:
        print(f"Warning: Could not import all blueprints: {e}")
        # Fallback to basic blueprints
        from app.routes import main_bp, auth_bp, shop_bp, order_bp, driver_bp
        app.register_blueprint(main_bp)
        app.register_blueprint(auth_bp, url_prefix='/auth')
        app.register_blueprint(shop_bp, url_prefix='/shop')
        app.register_blueprint(order_bp, url_prefix='/orders')
        app.register_blueprint(driver_bp, url_prefix='/driver')
    
    # Template context processors
    @app.context_processor
    def utility_processor():
        def format_currency(amount):
            if amount is None:
                amount = 0
            return f"R {amount:,.2f}"
        
        def get_order_status_color(status):
            colors = {
                'pending': 'warning',
                'confirmed': 'info',
                'preparing': 'info',
                'ready': 'primary',
                'picked_up': 'info',
                'in_transit': 'info',
                'delivered': 'success',
                'cancelled': 'danger'
            }
            return colors.get(status, 'secondary')
        
        return dict(
            format_currency=format_currency,
            get_order_status_color=get_order_status_color,
            app_name=app.config.get('APP_NAME', 'Jozini Move'),
            app_version=app.config.get('APP_VERSION', '1.0.0')
        )
    
    # Request handlers
    @app.before_request
    def before_request():
        g.user = current_user if current_user.is_authenticated else None
        g.request_start_time = datetime.utcnow()
    
    @app.after_request
    def after_request(response):
        if hasattr(g, 'request_start_time'):
            elapsed = (datetime.utcnow() - g.request_start_time).total_seconds()
            if elapsed > 1.0:  # Log slow requests
                app.logger.warning(f'Slow request: {request.path} took {elapsed:.2f}s')
        return response
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        if request.is_json:
            return {'error': 'Resource not found'}, 404
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(403)
    def forbidden_error(error):
        if request.is_json:
            return {'error': 'Access forbidden'}, 403
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.error(f'Server Error: {error}')
        if request.is_json:
            return {'error': 'Internal server error'}, 500
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(429)
    def ratelimit_error(error):
        if request.is_json:
            return {'error': 'Rate limit exceeded. Please try again later.'}, 429
        flash('Too many requests. Please slow down.', 'danger')
        return redirect(url_for('main.index'))
    
    # Create database tables and initialize default data
    with app.app_context():
        try:
            db.create_all()
            print("✓ Database tables created/verified successfully!")
            
            # Initialize default data
            init_default_data(app)
            
        except Exception as e:
            print(f"Warning: Could not create database tables: {e}")
            print("You may need to run: flask db upgrade")
    
    # Setup logging
    if not app.debug and not app.testing:
        # File logging
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        file_handler = RotatingFileHandler('logs/jozini_move.log', maxBytes=10485760, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        app.logger.setLevel(logging.INFO)
        app.logger.info('Jozini Move application startup')
    
    return app

def init_default_data(app):
    """Initialize default data for the application"""
    from app.models import User, Shop, Item, DeliveryZone, Settings, Notification
    
    print("\n" + "=" * 50)
    print("Initializing Default Data")
    print("=" * 50)
    
    # 1. Create Admin User
    print("\n1. Creating admin user...")
    admin = User.query.filter_by(email='admin@jozinimove.co.za').first()
    if not admin:
        admin = User(
            name='System Administrator',
            phone='0712345678',
            email='admin@jozinimove.co.za',
            address='Jozini Town Centre, Jozini, South Africa',
            user_type='admin',
            is_active=True,
            is_verified=True,
            rating=5.0,
            created_at=datetime.utcnow()
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("   ✓ Admin user created!")
        print("      Email: admin@jozinimove.co.za")
        print("      Password: admin123")
    else:
        print("   ✓ Admin user already exists")
    
    # 2. Create Demo Customer
    print("\n2. Creating demo customer...")
    customer = User.query.filter_by(email='customer@jozinimove.co.za').first()
    if not customer:
        customer = User(
            name='Thandi Customer',
            phone='0721234567',
            email='customer@jozinimove.co.za',
            address='123 Main Street, Jozini Town',
            user_type='customer',
            is_active=True,
            is_verified=True,
            rating=5.0,
            created_at=datetime.utcnow()
        )
        customer.set_password('customer123')
        db.session.add(customer)
        db.session.commit()
        print("   ✓ Demo customer created!")
        print("      Email: customer@jozinimove.co.za")
        print("      Password: customer123")
    else:
        print("   ✓ Demo customer already exists")
    
    # 3. Create Demo Driver
    print("\n3. Creating demo driver...")
    driver = User.query.filter_by(email='driver@jozinimove.co.za').first()
    if not driver:
        driver = User(
            name='Sipho Driver',
            phone='0839876543',
            email='driver@jozinimove.co.za',
            address='15 Taxi Rank, Jozini',
            user_type='driver',
            is_active=True,
            is_verified=True,
            vehicle='Toyota Hilux - White',
            rating=5.0,
            created_at=datetime.utcnow()
        )
        driver.set_password('driver123')
        db.session.add(driver)
        db.session.commit()
        print("   ✓ Demo driver created!")
        print("      Email: driver@jozinimove.co.za")
        print("      Password: driver123")
    else:
        print("   ✓ Demo driver already exists")
    
    # 4. Create Demo Shop Owner
    print("\n4. Creating demo shop owner...")
    shop_owner = User.query.filter_by(email='shopowner@jozinimove.co.za').first()
    if not shop_owner:
        shop_owner = User(
            name='Mama Dlamini',
            phone='0711111111',
            email='shopowner@jozinimove.co.za',
            address='Jozini Market, Shop 5',
            user_type='shop_owner',
            is_active=True,
            is_verified=True,
            shop_category='Restaurant',
            rating=5.0,
            created_at=datetime.utcnow()
        )
        shop_owner.set_password('shop123')
        db.session.add(shop_owner)
        db.session.commit()
        print("   ✓ Demo shop owner created!")
        print("      Email: shopowner@jozinimove.co.za")
        print("      Password: shop123")
    else:
        print("   ✓ Demo shop owner already exists")
    
    # 5. Create Delivery Zones
    print("\n5. Creating delivery zones...")
    zones = [
        {'name': 'Jozini Town Centre', 'description': 'Central Jozini area including CBD', 'delivery_fee': 15.00, 'estimated_time': 30, 'min_order': 0, 'is_active': True},
        {'name': 'Jozini Market', 'description': 'Jozini Market area and taxi rank', 'delivery_fee': 15.00, 'estimated_time': 25, 'min_order': 0, 'is_active': True},
        {'name': 'Lake Jozini', 'description': 'Lake Jozini resort area', 'delivery_fee': 25.00, 'estimated_time': 40, 'min_order': 50, 'is_active': True},
        {'name': 'eMpangeni', 'description': 'eMpangeni village', 'delivery_fee': 30.00, 'estimated_time': 35, 'min_order': 50, 'is_active': True},
        {'name': 'Pongola', 'description': 'Pongola town', 'delivery_fee': 35.00, 'estimated_time': 45, 'min_order': 100, 'is_active': True},
        {'name': 'Ngotshane', 'description': 'Ngotshane village', 'delivery_fee': 25.00, 'estimated_time': 35, 'min_order': 50, 'is_active': True},
        {'name': 'Makhoseni', 'description': 'Makhoseni rural area', 'delivery_fee': 30.00, 'estimated_time': 40, 'min_order': 50, 'is_active': True},
        {'name': 'Mseleni', 'description': 'Mseleni area', 'delivery_fee': 40.00, 'estimated_time': 50, 'min_order': 100, 'is_active': True},
    ]
    
    zones_created = 0
    for zone_data in zones:
        zone = DeliveryZone.query.filter_by(name=zone_data['name']).first()
        if not zone:
            zone = DeliveryZone(**zone_data)
            db.session.add(zone)
            zones_created += 1
    db.session.commit()
    print(f"   ✓ {zones_created} delivery zones created successfully!")
    
    # 6. Create Demo Shop
    print("\n6. Creating demo shop...")
    shop_owner_obj = User.query.filter_by(email='shopowner@jozinimove.co.za').first()
    shop = Shop.query.filter_by(shop_name="Mama's Kitchen").first()
    
    if not shop and shop_owner_obj:
        shop = Shop(
            owner_id=shop_owner_obj.id,
            shop_name="Mama's Kitchen",
            category='restaurant',
            address='Jozini Market, Shop 5, Jozini',
            phone='0711111111',
            email='shopowner@jozinimove.co.za',
            description='Traditional home-cooked meals and fast food. Serving the Jozini community with love!',
            opening_hours='7:00 AM',
            closing_hours='9:00 PM',
            rating=4.8,
            rating_count=125,
            is_open=True,
            status='active',
            min_order=30.00,
            delivery_fee=20.00,
            preparation_time=30,
            created_at=datetime.utcnow()
        )
        db.session.add(shop)
        db.session.commit()
        print("   ✓ Demo shop 'Mama's Kitchen' created!")
    else:
        print("   ✓ Demo shop already exists")
        shop = Shop.query.filter_by(shop_name="Mama's Kitchen").first()
    
    # 7. Create Menu Items
    if shop:
        print("\n7. Creating menu items...")
        items = [
            {'name': 'Chicken Burger', 'description': 'Grilled chicken breast with lettuce, tomato, and mayo', 'price': 65.00, 'category': 'Burgers', 'available': True, 'is_featured': True, 'preparation_time': 15, 'stock_quantity': -1},
            {'name': 'Beef Burger', 'description': 'Juicy beef patty with cheese and special sauce', 'price': 75.00, 'category': 'Burgers', 'available': True, 'is_featured': True, 'preparation_time': 15, 'stock_quantity': -1},
            {'name': 'Veggie Burger', 'description': 'Plant-based patty with fresh vegetables', 'price': 65.00, 'category': 'Burgers', 'available': True, 'is_featured': False, 'preparation_time': 15, 'stock_quantity': -1},
            {'name': 'Fried Chicken (3 pieces)', 'description': 'Crispy fried chicken with chips and gravy', 'price': 85.00, 'category': 'Chicken', 'available': True, 'is_featured': True, 'preparation_time': 20, 'stock_quantity': -1},
            {'name': 'Chicken Wings (6 pieces)', 'description': 'Spicy or BBQ chicken wings', 'price': 55.00, 'category': 'Chicken', 'available': True, 'is_featured': False, 'preparation_time': 15, 'stock_quantity': -1},
            {'name': 'Chips (Large)', 'description': 'Large portion of crispy golden fries', 'price': 25.00, 'category': 'Sides', 'available': True, 'is_featured': False, 'preparation_time': 10, 'stock_quantity': -1},
            {'name': 'Onion Rings', 'description': 'Crispy battered onion rings', 'price': 30.00, 'category': 'Sides', 'available': True, 'is_featured': False, 'preparation_time': 10, 'stock_quantity': -1},
            {'name': 'Coca-Cola 500ml', 'description': 'Ice-cold Coca-Cola', 'price': 15.00, 'category': 'Beverages', 'available': True, 'is_featured': False, 'preparation_time': 2, 'stock_quantity': 100},
            {'name': 'Fanta Orange 500ml', 'description': 'Ice-cold Fanta Orange', 'price': 15.00, 'category': 'Beverages', 'available': True, 'is_featured': False, 'preparation_time': 2, 'stock_quantity': 100},
            {'name': 'Water 500ml', 'description': 'Still spring water', 'price': 10.00, 'category': 'Beverages', 'available': True, 'is_featured': False, 'preparation_time': 1, 'stock_quantity': 200},
            {'name': 'Chicken Salad', 'description': 'Fresh mixed greens with grilled chicken', 'price': 70.00, 'category': 'Salads', 'available': True, 'is_featured': False, 'preparation_time': 12, 'stock_quantity': -1},
            {'name': 'Ice Cream Sundae', 'description': 'Vanilla ice cream with chocolate sauce', 'price': 35.00, 'category': 'Desserts', 'available': True, 'is_featured': False, 'preparation_time': 5, 'stock_quantity': 50},
        ]
        
        items_created = 0
        for item_data in items:
            existing_item = Item.query.filter_by(shop_id=shop.id, name=item_data['name']).first()
            if not existing_item:
                item = Item(shop_id=shop.id, **item_data)
                db.session.add(item)
                items_created += 1
        db.session.commit()
        print(f"   ✓ {items_created} menu items created!")
    
    # 8. Create System Settings
    print("\n8. Creating system settings...")
    settings_list = [
        {'key': 'app_name', 'value': 'Jozini Move', 'description': 'Application name'},
        {'key': 'app_version', 'value': '1.0.0', 'description': 'Application version'},
        {'key': 'app_description', 'value': 'Fast & reliable local delivery service', 'description': 'App description'},
        {'key': 'contact_email', 'value': 'info@jozinimove.co.za', 'description': 'Contact email'},
        {'key': 'contact_phone', 'value': '+27 71 234 5678', 'description': 'Contact phone'},
        {'key': 'delivery_fee', 'value': '20.00', 'description': 'Default delivery fee'},
        {'key': 'service_fee', 'value': '5.00', 'description': 'Service fee'},
        {'key': 'driver_percentage', 'value': '70', 'description': 'Driver commission'},
        {'key': 'free_delivery_min', 'value': '200', 'description': 'Free delivery minimum'},
        {'key': 'platform_commission', 'value': '10', 'description': 'Platform commission'},
        {'key': 'sms_enabled', 'value': 'false', 'description': 'SMS notifications'},
        {'key': 'email_enabled', 'value': 'false', 'description': 'Email notifications'},
    ]
    
    settings_created = 0
    for setting_data in settings_list:
        setting = Settings.query.filter_by(key=setting_data['key']).first()
        if not setting:
            setting = Settings(**setting_data)
            db.session.add(setting)
            settings_created += 1
    db.session.commit()
    print(f"   ✓ {settings_created} system settings created!")
    
    # 9. Create Welcome Notifications
    print("\n9. Creating welcome notifications...")
    users = User.query.all()
    notifications_created = 0
    for user in users:
        existing = Notification.query.filter_by(user_id=user.id, title='Welcome to Jozini Move!').first()
        if not existing:
            notification = Notification(
                user_id=user.id,
                title='Welcome to Jozini Move!',
                message=f'Welcome {user.name}! Start exploring local shops today!',
                type='success',
                created_at=datetime.utcnow()
            )
            db.session.add(notification)
            notifications_created += 1
    db.session.commit()
    print(f"   ✓ {notifications_created} welcome notifications created!")
    
    print("\n" + "=" * 50)
    print("✅ DEFAULT DATA INITIALIZATION COMPLETE!")
    print("=" * 50)
    print("\n📋 Login Credentials:")
    print("-" * 30)
    print("🔹 ADMIN: admin@jozinimove.co.za / admin123")
    print("🔹 CUSTOMER: customer@jozinimove.co.za / customer123")
    print("🔹 DRIVER: driver@jozinimove.co.za / driver123")
    print("🔹 SHOP OWNER: shopowner@jozinimove.co.za / shop123")
    print("-" * 30)
    print("\n🚀 Application ready! Visit: http://localhost:5000")
    print("=" * 50)

# Import models for SQLAlchemy
from app import models
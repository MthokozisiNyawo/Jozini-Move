from app.routes.main import main_bp
from app.routes.auth import auth_bp
from app.routes.shop import shop_bp
from app.routes.order import order_bp
from app.routes.driver import driver_bp
from app.routes.admin import admin_bp
from app.routes.api import api_bp

__all__ = [
    'main_bp', 
    'auth_bp', 
    'shop_bp', 
    'order_bp', 
    'driver_bp', 
    'admin_bp',
    'api_bp'
]
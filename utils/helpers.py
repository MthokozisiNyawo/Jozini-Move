import os
import random
import string
import secrets
from app.models import Notification, db
from datetime import datetime, timedelta
from flask import current_app, url_for, json
from PIL import Image
import re

def generate_order_number():
    """Generate unique order number: JM-YYYYMMDD-XXXX"""
    date_str = datetime.now().strftime('%Y%m%d')
    random_str = ''.join(random.choices(string.digits, k=4))
    return f"JM-{date_str}-{random_str}"

def generate_delivery_pin():
    """Generate 4-digit delivery PIN"""
    return ''.join(random.choices(string.digits, k=4))

def get_delivery_zones():
    """Get delivery zones for Jozini area"""
    return [
        ('jozini_town', 'Jozini Town Centre - R15', 15.00, 30),
        ('jozini_market', 'Jozini Market - R15', 15.00, 25),
        ('lake_jozini', 'Lake Jozini Area - R25', 25.00, 40),
        ('empangeni', 'eMpangeni Village - R30', 30.00, 35),
        ('pongola', 'Pongola Town - R35', 35.00, 45),
        ('ngotshane', 'Ngotshane - R25', 25.00, 35),
        ('makhoseni', 'Makhoseni - R30', 30.00, 40),
        ('mseleni', 'Mseleni - R40', 40.00, 50)
    ]

def calculate_delivery_fee(zone):
    """Calculate delivery fee based on zone"""
    zones = {
        'jozini_town': 15.00,
        'jozini_market': 15.00,
        'lake_jozini': 25.00,
        'empangeni': 30.00,
        'pongola': 35.00,
        'ngotshane': 25.00,
        'makhoseni': 30.00,
        'mseleni': 40.00
    }
    return zones.get(zone, 20.00)

def format_currency(amount):
    """Format amount as South African Rand"""
    if amount is None:
        amount = 0
    return f"R {amount:,.2f}"

def get_order_status_color(status):
    """Return Bootstrap color class for order status"""
    colors = {
        'pending': 'warning',
        'confirmed': 'info',
        'preparing': 'info',
        'ready': 'primary',
        'accepted': 'primary',
        'picked_up': 'info',
        'in_transit': 'info',
        'delivered': 'success',
        'cancelled': 'danger'
    }
    return colors.get(status, 'secondary')

def get_order_status_text(status):
    """Return human-readable status text"""
    texts = {
        'pending': 'Order Placed',
        'confirmed': 'Order Confirmed',
        'preparing': 'Being Prepared',
        'ready': 'Ready for Pickup',
        'accepted': 'Accepted by Driver',
        'picked_up': 'Picked Up',
        'in_transit': 'On the Way',
        'delivered': 'Delivered',
        'cancelled': 'Cancelled'
    }
    return texts.get(status, status.title())

def validate_south_african_phone(phone):
    """Validate South African phone number"""
    pattern = r'^(0[6-8][0-9]{8})$'
    return re.match(pattern, phone) is not None

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def save_uploaded_file(file, folder, filename=None):
    """Save uploaded file and return filename"""
    if not file:
        return None
    
    # Create folder if not exists
    upload_path = os.path.join(current_app.root_path, 'static', folder)
    os.makedirs(upload_path, exist_ok=True)
    
    # Generate filename if not provided
    if not filename:
        ext = file.filename.rsplit('.', 1)[1].lower() if file.filename else 'jpg'
        filename = f"{secrets.token_hex(16)}.{ext}"
    
    # Save file
    filepath = os.path.join(upload_path, filename)
    file.save(filepath)
    
    # Optimize image
    if folder in ['uploads', 'profile', 'items', 'logos']:
        optimize_image(filepath)
    
    return filename

def optimize_image(filepath, max_size=(800, 800), quality=85):
    """Optimize image size and quality"""
    try:
        with Image.open(filepath) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Resize if too large
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save with optimization
            img.save(filepath, optimize=True, quality=quality)
    except Exception as e:
        current_app.logger.error(f"Image optimization failed: {e}")

def save_profile_image(file, user_id):
    """Save profile image and return filename"""
    if not file or not file.filename:
        return None
    
    upload_path = os.path.join(current_app.root_path, 'static/uploads/profile')
    os.makedirs(upload_path, exist_ok=True)
    
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"user_{user_id}_{secrets.token_hex(8)}.{ext}"
    filepath = os.path.join(upload_path, filename)
    
    file.save(filepath)
    optimize_image(filepath, max_size=(500, 500), quality=85)
    
    return filename

def save_shop_logo(file, shop_id):
    """Save shop logo and return filename"""
    if not file or not file.filename:
        return None
    
    upload_path = os.path.join(current_app.root_path, 'static/uploads/logos')
    os.makedirs(upload_path, exist_ok=True)
    
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"shop_{shop_id}_{secrets.token_hex(8)}.{ext}"
    filepath = os.path.join(upload_path, filename)
    
    file.save(filepath)
    optimize_image(filepath, max_size=(500, 500), quality=85)
    
    return filename

def save_item_image(file, item_id):
    """Save item image and return filename"""
    if not file or not file.filename:
        return None
    
    upload_path = os.path.join(current_app.root_path, 'static/uploads/items')
    os.makedirs(upload_path, exist_ok=True)
    
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"item_{item_id}_{secrets.token_hex(8)}.{ext}"
    filepath = os.path.join(upload_path, filename)
    
    file.save(filepath)
    optimize_image(filepath, max_size=(800, 800), quality=85)
    
    return filename

def delete_image(filepath):
    """Delete an image file"""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            return True
    except Exception as e:
        current_app.logger.error(f"Failed to delete image: {e}")
    return False

def send_verification_sms(phone, token):
    """Send verification SMS using Africa's Talking"""
    if not current_app.config.get('SMS_ENABLED', False):
        return
    
    try:
        from africastalking import initialize, SMS
        
        initialize(
            username=current_app.config.get('AFRICAS_TALKING_USERNAME'),
            api_key=current_app.config.get('AFRICAS_TALKING_API_KEY')
        )
        
        sms = SMS()
        verification_url = f"{current_app.config['APP_URL']}/auth/verify/{token}"
        message = f"Welcome to Jozini Move! Verify your account: {verification_url}"
        
        sms.send(message, [phone])
    except Exception as e:
        current_app.logger.error(f"SMS sending failed: {e}")

def send_verification_email(email, token):
    """Send verification email using SendGrid"""
    if not current_app.config.get('EMAIL_ENABLED', False):
        return
    
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        
        verification_url = f"{current_app.config['APP_URL']}/auth/verify/{token}"
        
        message = Mail(
            from_email=current_app.config.get('DEFAULT_FROM_EMAIL', 'noreply@jozinimove.co.za'),
            to_emails=email,
            subject='Verify Your Jozini Move Account',
            html_content=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Verify Your Account</title>
            </head>
            <body style="font-family: Arial, sans-serif;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #0d6efd;">Welcome to Jozini Move!</h1>
                    <p>Please click the button below to verify your account:</p>
                    <a href="{verification_url}" style="display: inline-block; padding: 10px 20px; background-color: #0d6efd; color: white; text-decoration: none; border-radius: 5px;">Verify Account</a>
                    <p>Or copy this link: <a href="{verification_url}">{verification_url}</a></p>
                    <p>This link will expire in 24 hours.</p>
                    <hr>
                    <p style="color: #666; font-size: 12px;">Jozini Move - Fast & Reliable Local Delivery</p>
                </div>
            </body>
            </html>
            """
        )
        
        sg = SendGridAPIClient(current_app.config.get('SENDGRID_API_KEY'))
        sg.send(message)
    except Exception as e:
        current_app.logger.error(f"Email sending failed: {e}")

def send_password_reset_email(email, token):
    """Send password reset email"""
    if not current_app.config.get('EMAIL_ENABLED', False):
        return
    
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        
        reset_url = f"{current_app.config['APP_URL']}/auth/reset-password/{token}"
        
        message = Mail(
            from_email=current_app.config.get('DEFAULT_FROM_EMAIL', 'noreply@jozinimove.co.za'),
            to_emails=email,
            subject='Reset Your Jozini Move Password',
            html_content=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Reset Your Password</title>
            </head>
            <body style="font-family: Arial, sans-serif;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #0d6efd;">Password Reset Request</h1>
                    <p>Click the button below to reset your password:</p>
                    <a href="{reset_url}" style="display: inline-block; padding: 10px 20px; background-color: #0d6efd; color: white; text-decoration: none; border-radius: 5px;">Reset Password</a>
                    <p>Or copy this link: <a href="{reset_url}">{reset_url}</a></p>
                    <p>This link will expire in 1 hour.</p>
                    <p>If you didn't request this, please ignore this email.</p>
                    <hr>
                    <p style="color: #666; font-size: 12px;">Jozini Move - Fast & Reliable Local Delivery</p>
                </div>
            </body>
            </html>
            """
        )
        
        sg = SendGridAPIClient(current_app.config.get('SENDGRID_API_KEY'))
        sg.send(message)
    except Exception as e:
        current_app.logger.error(f"Email sending failed: {e}")

def send_order_notification(order, event):
    """Send order notification to relevant parties"""
    try:
        # Customer notification
        customer_notification = Notification(
            user_id=order.customer_id,
            title=f"Order {event.replace('_', ' ').title()}",
            message=f"Your order #{order.order_number} has been {event.replace('_', ' ')}.",
            type='info',
            link=url_for('order.order_detail', order_number=order.order_number)
        )
        db.session.add(customer_notification)
        
        # Shop owner notification
        if order.shop and order.shop.owner_id:
            shop_notification = Notification(
                user_id=order.shop.owner_id,
                title=f"Order {event.replace('_', ' ').title()}",
                message=f"Order #{order.order_number} has been {event.replace('_', ' ')}.",
                type='info',
                link=url_for('order.order_detail', order_number=order.order_number)
            )
            db.session.add(shop_notification)
        
        # Driver notification (if assigned)
        if order.driver_id:
            driver_notification = Notification(
                user_id=order.driver_id,
                title=f"Order {event.replace('_', ' ').title()}",
                message=f"Order #{order.order_number} has been {event.replace('_', ' ')}.",
                type='info',
                link=url_for('driver.order_details', order_number=order.order_number)
            )
            db.session.add(driver_notification)
        
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Notification failed: {e}")
        db.session.rollback()

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates in km"""
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371  # Earth's radius in km
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c

def estimate_delivery_time(distance_km):
    """Estimate delivery time based on distance"""
    # Average speed 30 km/h in urban areas
    travel_time = (distance_km / 30) * 60
    # Add 15 minutes for pickup and dropoff
    return int(travel_time + 15)

def parse_items_json(items_json):
    """Safely parse items JSON string"""
    if not items_json:
        return []
    try:
        return json.loads(items_json)
    except (json.JSONDecodeError, TypeError):
        return []

def get_category_icon(category):
    """Get Font Awesome icon for shop category"""
    icons = {
        'restaurant': 'utensils',
        'butchery': 'drumstick-bite',
        'grocery': 'shopping-basket',
        'pharmacy': 'capsules',
        'hardware': 'tools',
        'clothing': 'tshirt',
        'electronics': 'mobile-alt',
        'other': 'store'
    }
    return icons.get(category.lower() if category else 'other', 'store')
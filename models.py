from datetime import datetime, timedelta
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
import json
import secrets
import qrcode
from io import BytesIO
import base64

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    address = db.Column(db.Text)
    user_type = db.Column(db.String(20), default='customer', index=True)
    rating = db.Column(db.Float, default=5.0)
    total_ratings = db.Column(db.Integer, default=0)
    vehicle = db.Column(db.String(50))
    shop_category = db.Column(db.String(50))
    profile_image = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100))
    reset_password_token = db.Column(db.String(100))
    reset_password_expires = db.Column(db.DateTime)
    last_login = db.Column(db.DateTime)
    last_ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    shops = db.relationship('Shop', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    customer_orders = db.relationship('Order', backref='customer', 
                                     foreign_keys='Order.customer_id', lazy='dynamic')
    driver_orders = db.relationship('Order', backref='driver', 
                                   foreign_keys='Order.driver_id', lazy='dynamic')
    cart_items = db.relationship('Cart', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password, method='scrypt')
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def get_unread_notifications_count(self):
        """Get count of unread notifications"""
        return Notification.query.filter_by(user_id=self.id, is_read=False).count()
    
    def generate_verification_token(self):
        """Generate email/phone verification token"""
        self.verification_token = secrets.token_urlsafe(32)
        db.session.commit()
        return self.verification_token
    
    def generate_reset_token(self):
        """Generate password reset token"""
        self.reset_password_token = secrets.token_urlsafe(32)
        self.reset_password_expires = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()
        return self.reset_password_token
    
    def update_rating(self, new_rating):
        """Update user rating"""
        total = (self.rating * self.total_ratings) + new_rating
        self.total_ratings += 1
        self.rating = total / self.total_ratings
        db.session.commit()
    
    def is_customer(self):
        return self.user_type == 'customer'
    
    def is_driver(self):
        return self.user_type == 'driver'
    
    def is_shop_owner(self):
        return self.user_type == 'shop_owner'
    
    def is_admin(self):
        return self.user_type == 'admin'
    
    def to_dict(self, include_sensitive=False):
        """Convert user to dictionary"""
        data = {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'user_type': self.user_type,
            'rating': self.rating,
            'profile_image': self.profile_image,
            'is_verified': self.is_verified,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_sensitive:
            data['address'] = self.address
            data['vehicle'] = self.vehicle
            data['shop_category'] = self.shop_category
        return data
    
    def __repr__(self):
        return f'<User {self.name} ({self.user_type})>'

class Shop(db.Model):
    __tablename__ = 'shops'
    
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    shop_name = db.Column(db.String(100), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False, index=True)
    address = db.Column(db.Text, nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120))
    description = db.Column(db.Text)
    opening_hours = db.Column(db.String(100))
    closing_hours = db.Column(db.String(100))
    rating = db.Column(db.Float, default=5.0)
    rating_count = db.Column(db.Integer, default=0)
    logo = db.Column(db.String(200))
    cover_image = db.Column(db.String(200))
    is_open = db.Column(db.Boolean, default=True, index=True)
    status = db.Column(db.String(20), default='pending', index=True)  # pending, active, suspended
    min_order = db.Column(db.Float, default=0)
    delivery_fee = db.Column(db.Float, default=20.00)
    preparation_time = db.Column(db.Integer, default=30)  # minutes
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items = db.relationship('Item', backref='shop', lazy='dynamic', cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='shop', lazy='dynamic')
    cart_items = db.relationship('Cart', backref='shop', lazy='dynamic')
    
    def update_rating(self):
        """Update shop rating based on completed orders"""
        from app.models import Order
        completed_orders = Order.query.filter_by(shop_id=self.id, order_status='delivered').all()
        if completed_orders:
            total_rating = sum(order.shop_rating or 0 for order in completed_orders if order.shop_rating)
            count = sum(1 for order in completed_orders if order.shop_rating)
            if count > 0:
                self.rating = total_rating / count
                self.rating_count = count
                db.session.commit()
    
    def get_qr_code(self):
        qr_data = f"{current_app.config['APP_URL']}/shop/{self.id}"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    def __repr__(self):
        return f'<Shop {self.shop_name}>'

class Item(db.Model):
    __tablename__ = 'items'
    
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), index=True)
    image = db.Column(db.String(200))
    available = db.Column(db.Boolean, default=True, index=True)
    is_featured = db.Column(db.Boolean, default=False)
    preparation_time = db.Column(db.Integer, default=15)  # minutes
    stock_quantity = db.Column(db.Integer, default=-1)  # -1 means unlimited
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    cart_items = db.relationship('Cart', backref='item', lazy='dynamic')
    
    def is_in_stock(self, quantity=1):
        """Check if item is in stock"""
        if self.stock_quantity == -1:
            return True
        return self.stock_quantity >= quantity
    
    def reduce_stock(self, quantity):
        """Reduce stock quantity"""
        if self.stock_quantity != -1:
            self.stock_quantity -= quantity
            db.session.commit()
    
    def to_dict(self):
        """Convert item to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'price': self.price,
            'category': self.category,
            'image': self.image,
            'available': self.available,
            'is_featured': self.is_featured,
            'preparation_time': self.preparation_time
        }
    
    def __repr__(self):
        return f'<Item {self.name}>'

class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    
    items_json = db.Column(db.Text, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    delivery_fee = db.Column(db.Float, default=20.00)
    service_fee = db.Column(db.Float, default=5.00)
    discount = db.Column(db.Float, default=0)
    grand_total = db.Column(db.Float, nullable=False)
    
    delivery_address = db.Column(db.Text, nullable=False)
    delivery_zone = db.Column(db.String(50))
    delivery_latitude = db.Column(db.Float)
    delivery_longitude = db.Column(db.Float)
    order_notes = db.Column(db.Text)
    
    order_status = db.Column(db.String(20), default='pending', index=True)
    payment_method = db.Column(db.String(20), default='cash')
    payment_status = db.Column(db.String(20), default='pending', index=True)
    payment_transaction_id = db.Column(db.String(100))
    
    delivery_pin = db.Column(db.String(10))
    estimated_delivery = db.Column(db.DateTime)
    actual_delivery = db.Column(db.DateTime)
    
    customer_rating = db.Column(db.Integer)
    customer_review = db.Column(db.Text)
    shop_rating = db.Column(db.Integer)
    driver_rating = db.Column(db.Integer)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    status_history = db.relationship('OrderStatus', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    
    def add_status_update(self, status, notes=None, user_id=None):
        """Add status update to order"""
        status_update = OrderStatus(
            order_id=self.id,
            status=status,
            notes=notes,
            user_id=user_id
        )
        db.session.add(status_update)
        self.order_status = status
        db.session.commit()
        return status_update
    
    def get_items(self):
        """Get order items as list"""
        return json.loads(self.items_json) if self.items_json else []
    
    def get_driver_earnings(self):
        """Calculate driver earnings for delivered order"""
        if self.order_status == 'delivered':
            return (self.delivery_fee * 0.7) + self.service_fee
        return 0
    
    def get_shop_earnings(self):
        """Calculate shop earnings"""
        return self.total_amount + (self.delivery_fee * 0.3)  # Shop gets 30% of delivery fee
    
    def generate_delivery_qr(self):
        """Generate QR code for delivery confirmation"""
        qr_data = f"{current_app.config['APP_URL']}/delivery/confirm/{self.order_number}/{self.delivery_pin}"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    
    def to_dict(self):
        """Convert order to dictionary"""
        return {
            'order_number': self.order_number,
            'status': self.order_status,
            'total_amount': self.total_amount,
            'delivery_fee': self.delivery_fee,
            'service_fee': self.service_fee,
            'grand_total': self.grand_total,
            'payment_method': self.payment_method,
            'payment_status': self.payment_status,
            'estimated_delivery': self.estimated_delivery.isoformat() if self.estimated_delivery else None,
            'created_at': self.created_at.isoformat(),
            'items': self.get_items()
        }
    
    def __repr__(self):
        return f'<Order {self.order_number}>'

class OrderStatus(db.Model):
    __tablename__ = 'order_statuses'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, index=True)
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user = db.relationship('User', foreign_keys=[user_id])
    
    def __repr__(self):
        return f'<OrderStatus {self.status} for Order {self.order_id}>'

class Cart(db.Model):
    __tablename__ = 'cart'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    special_instructions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'shop_id', 'item_id', name='unique_cart_item'),
    )
    
    def get_subtotal(self):
        """Calculate item subtotal"""
        return self.item.price * self.quantity
    
    def to_dict(self):
        """Convert cart item to dictionary"""
        return {
            'id': self.id,
            'item_id': self.item_id,
            'name': self.item.name,
            'price': self.item.price,
            'quantity': self.quantity,
            'subtotal': self.get_subtotal(),
            'special_instructions': self.special_instructions
        }
    
    def __repr__(self):
        return f'<Cart Item {self.item_id} x {self.quantity}>'

class DeliveryZone(db.Model):
    __tablename__ = 'delivery_zones'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text)
    delivery_fee = db.Column(db.Float, default=20.00)
    estimated_time = db.Column(db.Integer, default=30)  # minutes
    min_order = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<DeliveryZone {self.name}>'

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')  # info, success, warning, danger
    is_read = db.Column(db.Boolean, default=False, index=True)
    link = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        db.session.commit()
    
    def to_dict(self):
        """Convert notification to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'type': self.type,
            'is_read': self.is_read,
            'link': self.link,
            'created_at': self.created_at.isoformat()
        }
    
    def __repr__(self):
        return f'<Notification {self.title}>'

class Settings(db.Model):
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @classmethod
    def get(cls, key, default=None):
        """Get setting value by key"""
        setting = cls.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @classmethod
    def set(cls, key, value, description=None):
        """Set setting value"""
        setting = cls.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = cls(key=key, value=value, description=description)
            db.session.add(setting)
        db.session.commit()
        return setting
    
    @classmethod
    def get_float(cls, key, default=0.0):
        """Get setting as float"""
        value = cls.get(key)
        if value:
            try:
                return float(value)
            except ValueError:
                return default
        return default
    
    @classmethod
    def get_int(cls, key, default=0):
        """Get setting as integer"""
        value = cls.get(key)
        if value:
            try:
                return int(value)
            except ValueError:
                return default
        return default
    
    @classmethod
    def get_bool(cls, key, default=False):
        """Get setting as boolean"""
        value = cls.get(key)
        if value is not None:
            return value.lower() in ('true', '1', 'yes', 'on')
        return default
    
    def __repr__(self):
        return f'<Setting {self.key}={self.value}>'

class PaymentTransaction(db.Model):
    __tablename__ = 'payment_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    transaction_id = db.Column(db.String(100), unique=True, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    response_data = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    order = db.relationship('Order', backref=db.backref('payment_transactions', lazy='dynamic'))
    
    def __repr__(self):
        return f'<PaymentTransaction {self.transaction_id}>'

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50))
    resource_id = db.Column(db.Integer)
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user = db.relationship('User', foreign_keys=[user_id])
    
    def __repr__(self):
        return f'<AuditLog {self.action} by User {self.user_id}>'
    
class RefundRequest(db.Model):
    __tablename__ = 'refund_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    refund_method = db.Column(db.String(50), default='original')
    evidence = db.Column(db.Text)  # Comma-separated image paths
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, completed
    admin_notes = db.Column(db.Text)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    order = db.relationship('Order', backref=db.backref('refund_requests', lazy='dynamic'))
    user = db.relationship('User', foreign_keys=[user_id])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])
    
    def __repr__(self):
        return f'<RefundRequest {self.id} for Order {self.order_id}>'
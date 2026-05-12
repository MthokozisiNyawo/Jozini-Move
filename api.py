from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db, limiter
from app.models import User, Shop, Item, Order, Cart, DeliveryZone, OrderStatus
from app.utils.helpers import generate_order_number, generate_delivery_pin, format_currency
from datetime import datetime, timedelta
import json

api_bp = Blueprint('api', __name__)

@api_bp.route('/auth/login', methods=['POST'])
@limiter.limit("10 per minute")
def api_login():
    """API login endpoint"""
    data = request.get_json()
    phone = data.get('phone')
    password = data.get('password')
    
    user = User.query.filter_by(phone=phone).first()
    if user and user.check_password(password):
        # Generate API token (implement JWT for production)
        return jsonify({
            'success': True,
            'user': user.to_dict(),
            'token': 'temp_token'  # Replace with JWT
        })
    
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@api_bp.route('/shops', methods=['GET'])
def get_shops():
    """Get all shops"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    category = request.args.get('category')
    search = request.args.get('search')
    
    query = Shop.query.filter_by(status='active')
    
    if category:
        query = query.filter_by(category=category)
    if search:
        query = query.filter(Shop.shop_name.ilike(f'%{search}%'))
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'shops': [shop.to_dict() for shop in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    })

@api_bp.route('/shops/<int:shop_id>/menu', methods=['GET'])
def get_shop_menu(shop_id):
    """Get shop menu"""
    shop = Shop.query.get_or_404(shop_id)
    items = Item.query.filter_by(shop_id=shop_id, available=True).all()
    
    # Group by category
    categories = {}
    for item in items:
        cat = item.category or 'Other'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item.to_dict())
    
    return jsonify({
        'shop': shop.to_dict(),
        'menu': categories
    })

@api_bp.route('/cart', methods=['GET'])
@login_required
def get_cart():
    """Get user's cart"""
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    
    # Group by shop
    shops = {}
    for item in cart_items:
        if item.shop_id not in shops:
            shops[item.shop_id] = {
                'shop': item.shop.to_dict(),
                'items': []
            }
        shops[item.shop_id]['items'].append(item.to_dict())
    
    return jsonify({'cart': list(shops.values())})

@api_bp.route('/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    """Add item to cart"""
    data = request.get_json()
    item_id = data.get('item_id')
    quantity = data.get('quantity', 1)
    
    item = Item.query.get_or_404(item_id)
    
    cart_item = Cart.query.filter_by(
        user_id=current_user.id,
        shop_id=item.shop_id,
        item_id=item_id
    ).first()
    
    if cart_item:
        cart_item.quantity += quantity
    else:
        cart_item = Cart(
            user_id=current_user.id,
            shop_id=item.shop_id,
            item_id=item_id,
            quantity=quantity
        )
        db.session.add(cart_item)
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Item added to cart'})

@api_bp.route('/cart/update/<int:cart_id>', methods=['PUT'])
@login_required
def update_cart_item(cart_id):
    """Update cart item quantity"""
    data = request.get_json()
    quantity = data.get('quantity')
    
    cart_item = Cart.query.get_or_404(cart_id)
    
    if cart_item.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    if quantity <= 0:
        db.session.delete(cart_item)
    else:
        cart_item.quantity = quantity
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Cart updated'})

@api_bp.route('/cart/remove/<int:cart_id>', methods=['DELETE'])
@login_required
def remove_from_cart(cart_id):
    """Remove item from cart"""
    cart_item = Cart.query.get_or_404(cart_id)
    
    if cart_item.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    db.session.delete(cart_item)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Item removed from cart'})

@api_bp.route('/orders', methods=['POST'])
@login_required
def create_order():
    """Create new order"""
    data = request.get_json()
    shop_id = data.get('shop_id')
    
    # Get cart items
    cart_items = Cart.query.filter_by(
        user_id=current_user.id,
        shop_id=shop_id
    ).all()
    
    if not cart_items:
        return jsonify({'success': False, 'message': 'Cart is empty'}), 400
    
    # Calculate totals
    subtotal = sum(item.item.price * item.quantity for item in cart_items)
    delivery_fee = 20.00
    service_fee = 5.00
    grand_total = subtotal + delivery_fee + service_fee
    
    # Create items list
    items_list = [{
        'name': cart_item.item.name,
        'price': cart_item.item.price,
        'quantity': cart_item.quantity,
        'total': cart_item.item.price * cart_item.quantity
    } for cart_item in cart_items]
    
    # Create order
    order = Order(
        order_number=generate_order_number(),
        customer_id=current_user.id,
        shop_id=shop_id,
        items_json=json.dumps(items_list),
        total_amount=subtotal,
        delivery_fee=delivery_fee,
        service_fee=service_fee,
        grand_total=grand_total,
        delivery_address=data.get('delivery_address'),
        delivery_zone=data.get('delivery_zone'),
        order_notes=data.get('order_notes'),
        payment_method=data.get('payment_method', 'cash'),
        delivery_pin=generate_delivery_pin(),
        estimated_delivery=datetime.utcnow() + timedelta(minutes=45)
    )
    
    db.session.add(order)
    db.session.flush()
    
    # Add status update
    order.add_status_update('pending', 'Order placed successfully')
    
    # Clear cart
    Cart.query.filter_by(user_id=current_user.id, shop_id=shop_id).delete()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'order': order.to_dict(),
        'message': f'Order {order.order_number} created successfully'
    })

@api_bp.route('/orders/<order_number>', methods=['GET'])
@login_required
def get_order(order_number):
    """Get order details"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    
    # Check permission
    if not (order.customer_id == current_user.id or 
            order.driver_id == current_user.id or
            order.shop.owner_id == current_user.id or
            current_user.is_admin()):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    return jsonify(order.to_dict())

@api_bp.route('/orders/<order_number>/status', methods=['PUT'])
@login_required
def update_order_status(order_number):
    """Update order status"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    data = request.get_json()
    status = data.get('status')
    notes = data.get('notes')
    
    # Check permission
    if order.shop.owner_id == current_user.id:
        # Shop owner can update: preparing, ready, cancelled
        allowed = ['preparing', 'ready', 'cancelled']
    elif order.driver_id == current_user.id:
        # Driver can update: picked_up, in_transit, delivered
        allowed = ['picked_up', 'in_transit', 'delivered']
    elif current_user.is_admin():
        allowed = ['pending', 'preparing', 'ready', 'picked_up', 'in_transit', 'delivered', 'cancelled']
    else:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    if status not in allowed:
        return jsonify({'success': False, 'message': 'Invalid status update'}), 400
    
    # For delivery, verify PIN
    if status == 'delivered':
        pin = data.get('delivery_pin')
        if not pin or pin != order.delivery_pin:
            return jsonify({'success': False, 'message': 'Invalid delivery PIN'}), 400
        order.actual_delivery = datetime.utcnow()
    
    order.add_status_update(status, notes, current_user.id)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Order status updated to {status}'})

@api_bp.route('/delivery-zones', methods=['GET'])
def get_delivery_zones():
    """Get delivery zones"""
    zones = DeliveryZone.query.filter_by(is_active=True).all()
    return jsonify([{
        'id': z.id,
        'name': z.name,
        'delivery_fee': z.delivery_fee,
        'estimated_time': z.estimated_time,
        'min_order': z.min_order
    } for z in zones])

@api_bp.route('/track/<order_number>', methods=['GET'])
def track_order(order_number):
    """Track order (public)"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    
    return jsonify({
        'order_number': order.order_number,
        'status': order.order_status,
        'estimated_delivery': order.estimated_delivery.isoformat() if order.estimated_delivery else None,
        'status_history': [{
            'status': s.status,
            'notes': s.notes,
            'time': s.created_at.isoformat()
        } for s in order.status_history.order_by(OrderStatus.created_at.asc()).all()]
    })

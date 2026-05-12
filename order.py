from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Order, OrderStatus, Shop, Cart, Notification, User, Item
from app.forms import CheckoutForm, ReviewForm
from app.utils.helpers import format_currency, get_order_status_color, parse_items_json
from datetime import datetime, timedelta
import json
import random
import string

order_bp = Blueprint('order', __name__)

def generate_order_number():
    """Generate unique order number: JM-YYYYMMDD-XXXX"""
    date_str = datetime.now().strftime('%Y%m%d')
    random_str = ''.join(random.choices(string.digits, k=4))
    return f"JM-{date_str}-{random_str}"

def generate_delivery_pin():
    """Generate 4-digit delivery PIN"""
    return ''.join(random.choices(string.digits, k=4))

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

def get_delivery_zones():
    """Get delivery zones for Jozini area"""
    return [
        ('jozini_town', 'Jozini Town Centre', 15.00),
        ('jozini_market', 'Jozini Market', 15.00),
        ('lake_jozini', 'Lake Jozini Area', 25.00),
        ('empangeni', 'eMpangeni Village', 30.00),
        ('pongola', 'Pongola Town', 35.00),
        ('ngotshane', 'Ngotshane', 25.00),
        ('makhoseni', 'Makhoseni', 30.00),
        ('mseleni', 'Mseleni', 40.00)
    ]

@order_bp.route('/checkout/<int:shop_id>', methods=['GET', 'POST'])
@login_required
def checkout(shop_id):
    """Checkout page"""
    if not current_user.is_customer():
        flash('Only customers can checkout', 'danger')
        return redirect(url_for('main.index'))
    
    # Check if user is trying to order from their own shop
    if current_user.is_shop_owner():
        user_shops = [shop.id for shop in current_user.shops.all()]
        if shop_id in user_shops:
            flash('You cannot place an order from your own shop. Please order from other shops.', 'danger')
            return redirect(url_for('shop.shop_detail', shop_id=shop_id))
    
    shop = Shop.query.get_or_404(shop_id)
    cart_items = Cart.query.filter_by(
        user_id=current_user.id,
        shop_id=shop_id
    ).all()
    
    if not cart_items:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('shop.shop_detail', shop_id=shop_id))
    
    # Check if shop is open
    if not shop.is_open:
        flash('This shop is currently closed', 'warning')
        return redirect(url_for('shop.shop_detail', shop_id=shop_id))
    
    # Calculate subtotal
    subtotal = sum(item.item.price * item.quantity for item in cart_items)
    
    # Check minimum order
    if subtotal < shop.min_order:
        flash(f'Minimum order amount for this shop is {format_currency(shop.min_order)}', 'warning')
        return redirect(url_for('shop.view_cart', shop_id=shop_id))
    
    # Initialize form
    form = CheckoutForm()
    
    # Set delivery zone choices
    zones = get_delivery_zones()
    form.delivery_zone.choices = [(z[0], f"{z[1]} - {format_currency(z[2])}") for z in zones]
    
    if form.validate_on_submit():
        try:
            # Get selected zone details
            selected_zone = next((z for z in zones if z[0] == form.delivery_zone.data), None)
            delivery_fee = selected_zone[2] if selected_zone else 20.00
            
            service_fee = 5.00
            grand_total = subtotal + delivery_fee + service_fee
            
            # Create items list
            items_list = []
            for cart_item in cart_items:
                items_list.append({
                    'id': cart_item.item.id,
                    'name': cart_item.item.name,
                    'price': float(cart_item.item.price),
                    'quantity': cart_item.quantity,
                    'total': float(cart_item.item.price * cart_item.quantity)
                })
                
                # Reduce stock
                cart_item.item.reduce_stock(cart_item.quantity)
            
            # Generate order number and PIN
            order_number = generate_order_number()
            delivery_pin = generate_delivery_pin()
            
            # Create order
            order = Order(
                order_number=order_number,
                customer_id=current_user.id,
                shop_id=shop_id,
                items_json=json.dumps(items_list),
                total_amount=subtotal,
                delivery_fee=delivery_fee,
                service_fee=service_fee,
                grand_total=grand_total,
                delivery_address=form.delivery_address.data,
                delivery_zone=form.delivery_zone.data,
                order_notes=form.order_notes.data,
                payment_method=form.payment_method.data,
                delivery_pin=delivery_pin,
                estimated_delivery=datetime.utcnow() + timedelta(minutes=shop.preparation_time + 30)
            )
            
            db.session.add(order)
            db.session.flush()
            
            # Add status update
            order.add_status_update('pending', 'Order placed successfully', current_user.id)
            
            # Clear cart
            Cart.query.filter_by(user_id=current_user.id, shop_id=shop_id).delete()
            
            # Create notifications
            # Customer notification
            customer_notification = Notification(
                user_id=current_user.id,
                title='Order Placed',
                message=f'Your order #{order_number} has been placed successfully. Total: {format_currency(grand_total)}',
                type='success',
                link=url_for('order.order_detail', order_number=order_number)
            )
            db.session.add(customer_notification)
            
            # Shop owner notification
            shop_notification = Notification(
                user_id=shop.owner_id,
                title='New Order Received',
                message=f'New order #{order_number} received for {shop.shop_name}. Total: {format_currency(grand_total)}',
                type='info',
                link=url_for('order.order_detail', order_number=order_number)
            )
            db.session.add(shop_notification)
            
            db.session.commit()
            
            flash(f'Order placed successfully! Your order number is {order_number}', 'success')
            return redirect(url_for('order.order_detail', order_number=order_number))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to place order: {str(e)}', 'danger')
    
    # Pre-fill delivery address
    if current_user.address:
        form.delivery_address.data = current_user.address
    
    return render_template('orders/checkout.html',
                         form=form,
                         shop=shop,
                         cart_items=cart_items,
                         subtotal=subtotal,
                         format_currency=format_currency)

@order_bp.route('/my-orders')
@login_required
def my_orders():
    """View user's orders based on user type"""
    from datetime import datetime
    
    if current_user.is_customer():
        orders = Order.query.filter_by(customer_id=current_user.id)\
                           .order_by(Order.created_at.desc())\
                           .all()
    elif current_user.is_shop_owner():
        # Get shop IDs owned by user
        shop_ids = [shop.id for shop in current_user.shops.all()]
        orders = Order.query.filter(Order.shop_id.in_(shop_ids))\
                           .order_by(Order.created_at.desc())\
                           .all()
    elif current_user.is_driver():
        orders = Order.query.filter_by(driver_id=current_user.id)\
                           .order_by(Order.created_at.desc())\
                           .all()
    else:
        orders = []
    
    # Parse items JSON for each order
    for order in orders:
        order.parsed_items = parse_items_json(order.items_json)
    
    now = datetime.utcnow()
    
    return render_template('orders/my_orders.html', 
                         orders=orders,
                         now=now,
                         get_order_status_color=get_order_status_color,
                         format_currency=format_currency)

@order_bp.route('/<order_number>')
@login_required
def order_detail(order_number):
    """Order details page"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    
    # Check permissions
    has_permission = (
        current_user.id == order.customer_id or
        current_user.id == order.driver_id or
        (order.shop and current_user.id == order.shop.owner_id) or
        current_user.is_admin()
    )
    
    if not has_permission:
        flash('You do not have permission to view this order', 'danger')
        return redirect(url_for('order.my_orders'))
    
    # Parse items
    items = parse_items_json(order.items_json)
    
    # Get status history
    status_history = OrderStatus.query.filter_by(order_id=order.id)\
                                     .order_by(OrderStatus.created_at.asc())\
                                     .all()
    
    # Get shop
    shop = Shop.query.get(order.shop_id)
    
    now = datetime.utcnow()
    
    return render_template('orders/order_detail.html',
                         order=order,
                         items=items,
                         status_history=status_history,
                         shop=shop,
                         now=now,
                         format_currency=format_currency)

@order_bp.route('/<order_number>/track')
def track_order(order_number):
    """Public order tracking page"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    
    items = parse_items_json(order.items_json)
    status_history = OrderStatus.query.filter_by(order_id=order.id)\
                                     .order_by(OrderStatus.created_at.asc())\
                                     .all()
    
    return render_template('orders/track.html', 
                         order=order, 
                         items=items,
                         status_history=status_history,
                         format_currency=format_currency)

@order_bp.route('/<order_number>/cancel', methods=['POST'])
@login_required
def cancel_order(order_number):
    """Cancel an order"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    
    # Only customer can cancel pending orders
    if current_user.id != order.customer_id:
        flash('You cannot cancel this order', 'danger')
        return redirect(url_for('order.order_detail', order_number=order_number))
    
    if order.order_status not in ['pending', 'confirmed']:
        flash('This order cannot be cancelled at this stage', 'warning')
        return redirect(url_for('order.order_detail', order_number=order_number))
    
    try:
        order.add_status_update('cancelled', 'Order cancelled by customer', current_user.id)
        
        # Restore stock
        items = parse_items_json(order.items_json)
        for item_data in items:
            item = Item.query.filter_by(shop_id=order.shop_id, name=item_data['name']).first()
            if item and item.stock_quantity != -1:
                item.stock_quantity += item_data['quantity']
        
        db.session.commit()
        flash('Order has been cancelled', 'success')
        return jsonify({'success': True, 'message': 'Order cancelled successfully'})
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to cancel order: {str(e)}', 'danger')
        return jsonify({'success': False, 'message': str(e)})

@order_bp.route('/<order_number>/review', methods=['GET', 'POST'])
@login_required
def review_order(order_number):
    """Review an order"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    
    if current_user.id != order.customer_id:
        flash('You cannot review this order', 'danger')
        return redirect(url_for('order.order_detail', order_number=order_number))
    
    if order.order_status != 'delivered':
        flash('You can only review delivered orders', 'warning')
        return redirect(url_for('order.order_detail', order_number=order_number))
    
    if order.customer_rating:
        flash('You have already reviewed this order', 'info')
        return redirect(url_for('order.order_detail', order_number=order_number))
    
    form = ReviewForm()
    
    if form.validate_on_submit():
        try:
            order.customer_rating = form.rating.data
            order.customer_review = form.review.data
            db.session.commit()
            
            # Update shop rating
            if order.shop:
                order.shop.update_rating()
            
            # Update driver rating if driver assigned
            if order.driver_id:
                driver = User.query.get(order.driver_id)
                if driver:
                    driver.update_rating(form.rating.data)
            
            flash('Thank you for your review!', 'success')
            return redirect(url_for('order.order_detail', order_number=order_number))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error submitting review: {str(e)}', 'danger')
    
    return render_template('orders/review.html', form=form, order=order, format_currency=format_currency)
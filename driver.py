from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Order, OrderStatus, Notification, Shop, User
from app.utils.helpers import format_currency
from app.utils.decorators import driver_required
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_, extract, text
import json
import random
import string

driver_bp = Blueprint('driver', __name__)

def generate_delivery_pin():
    """Generate a random 4-digit delivery PIN"""
    return ''.join(random.choices(string.digits, k=4))

@driver_bp.route('/dashboard')
@login_required
@driver_required
def dashboard():
    """Driver dashboard - display all orders from database"""
    try:
        # Get filter parameters
        status_filter = request.args.get('status', 'all')
        sort_by = request.args.get('sort', 'newest')
        
        # Base query - get ALL orders
        query = Order.query
        
        # Apply status filter
        if status_filter != 'all':
            query = query.filter(Order.order_status == status_filter)
        
        # Apply sorting
        if sort_by == 'newest':
            query = query.order_by(Order.created_at.desc())
        elif sort_by == 'oldest':
            query = query.order_by(Order.created_at.asc())
        elif sort_by == 'highest_fee':
            query = query.order_by(Order.delivery_fee.desc())
        elif sort_by == 'lowest_fee':
            query = query.order_by(Order.delivery_fee.asc())
        
        # Get all orders
        all_orders = query.all()
        
        # IMPORTANT: Available orders = ANY order with NO driver assigned (regardless of status)
        available_orders = [o for o in all_orders if o.driver_id is None]
        
        # My active orders = orders assigned to this driver that are NOT delivered or cancelled
        my_active_orders = [o for o in all_orders if o.driver_id == current_user.id and o.order_status not in ['delivered', 'cancelled']]
        
        # Completed orders = delivered orders by this driver
        completed_orders = [o for o in all_orders if o.order_status == 'delivered' and o.driver_id == current_user.id]
        
        # Get unique statuses for filter
        statuses = db.session.query(Order.order_status).distinct().all()
        statuses = [s[0] for s in statuses if s[0]]
        
        # Calculate driver statistics
        today = datetime.utcnow().date()
        
        # Today's deliveries for this driver
        today_deliveries = Order.query.filter(
            Order.driver_id == current_user.id,
            Order.order_status == 'delivered',
            func.date(Order.updated_at) == today
        ).count()
        
        # Today's earnings
        today_earnings = db.session.query(func.sum(Order.delivery_fee)).filter(
            Order.driver_id == current_user.id,
            Order.order_status == 'delivered',
            func.date(Order.updated_at) == today
        ).scalar() or 0
        today_earnings = (today_earnings * 0.7) + (today_deliveries * 5)
        
        # Total earnings for this driver
        total_earnings = db.session.query(func.sum(Order.delivery_fee)).filter(
            Order.driver_id == current_user.id,
            Order.order_status == 'delivered'
        ).scalar() or 0
        completed_count = Order.query.filter_by(
            driver_id=current_user.id, 
            order_status='delivered'
        ).count()
        total_earnings = (total_earnings * 0.7) + (completed_count * 5)
        
        # Total deliveries for this driver
        total_deliveries = Order.query.filter_by(
            driver_id=current_user.id,
            order_status='delivered'
        ).count()
        
        # Driver rating
        avg_rating = current_user.rating if current_user.total_ratings > 0 else 5.0
        
        # Get current time for new badge
        now = datetime.utcnow()
        
        return render_template('driver/dashboard.html',
                             all_orders=all_orders,
                             available_orders=available_orders,
                             my_active_orders=my_active_orders,
                             completed_orders=completed_orders,
                             today_deliveries=today_deliveries,
                             today_earnings=float(today_earnings),
                             total_earnings=float(total_earnings),
                             total_deliveries=total_deliveries,
                             avg_rating=avg_rating,
                             statuses=statuses,
                             status_filter=status_filter,
                             sort_by=sort_by,
                             now=now,
                             format_currency=format_currency)
    
    except Exception as e:
        current_app.logger.error(f"Driver dashboard error: {str(e)}")
        flash('Error loading dashboard. Please try again.', 'danger')
        return redirect(url_for('main.index'))

@driver_bp.route('/accept-order/<order_number>', methods=['POST'])
@login_required
@driver_required
def accept_order(order_number):
    """Driver accepts an available order"""
    try:
        order = Order.query.filter_by(order_number=order_number).first_or_404()
        
        # Check if order already has a driver assigned
        if order.driver_id is not None:
            flash('This order has already been accepted by another driver.', 'danger')
            return redirect(url_for('driver.dashboard'))
        
        # Assign driver to order
        order.driver_id = current_user.id
        order.order_status = 'accepted'
        order.updated_at = datetime.utcnow()
        
        # Add status update
        status_update = OrderStatus(
            order_id=order.id,
            status='accepted',
            notes=f'Driver {current_user.name} has accepted the order.',
            user_id=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(status_update)
        
        # Notify customer
        customer_notification = Notification(
            user_id=order.customer_id,
            title='Order Accepted!',
            message=f'Your order #{order_number} has been accepted by driver {current_user.name}. They will pick it up soon.',
            type='success',
            link=url_for('order.order_detail', order_number=order_number),
            created_at=datetime.utcnow()
        )
        db.session.add(customer_notification)
        
        # Notify shop owner
        shop_notification = Notification(
            user_id=order.shop.owner_id,
            title='Order Accepted by Driver',
            message=f'Order #{order_number} has been accepted by driver {current_user.name}.',
            type='info',
            link=url_for('order.order_detail', order_number=order_number),
            created_at=datetime.utcnow()
        )
        db.session.add(shop_notification)
        
        db.session.commit()
        
        flash(f'Order {order_number} accepted successfully! Please go to the shop to pick up the order.', 'success')
        return redirect(url_for('driver.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('driver.dashboard'))

@driver_bp.route('/pickup-order/<order_number>', methods=['POST'])
@login_required
@driver_required
def pickup_order(order_number):
    """Driver picks up the order from the shop"""
    try:
        order = Order.query.filter_by(order_number=order_number).first_or_404()
        
        if order.driver_id != current_user.id:
            flash('You are not assigned to this order.', 'danger')
            return redirect(url_for('driver.dashboard'))
        
        if order.order_status != 'accepted':
            flash('Order must be accepted before pickup.', 'danger')
            return redirect(url_for('driver.dashboard'))
        
        order.order_status = 'picked_up'
        order.updated_at = datetime.utcnow()
        
        status_update = OrderStatus(
            order_id=order.id,
            status='picked_up',
            notes=f'Driver {current_user.name} has picked up the order from the shop.',
            user_id=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(status_update)
        
        customer_notification = Notification(
            user_id=order.customer_id,
            title='Order Picked Up!',
            message=f'Your order #{order_number} has been picked up by the driver. Delivery in progress!',
            type='success',
            link=url_for('order.order_detail', order_number=order_number),
            created_at=datetime.utcnow()
        )
        db.session.add(customer_notification)
        
        db.session.commit()
        
        flash(f'Order {order_number} picked up successfully! Please deliver to the customer.', 'success')
        return redirect(url_for('driver.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('driver.dashboard'))

@driver_bp.route('/start-delivery/<order_number>', methods=['POST'])
@login_required
@driver_required
def start_delivery(order_number):
    """Driver starts delivery - generates PIN and notifies customer"""
    try:
        order = Order.query.filter_by(order_number=order_number).first_or_404()
        
        if order.driver_id != current_user.id:
            flash('You are not assigned to this order.', 'danger')
            return redirect(url_for('driver.dashboard'))
        
        if order.order_status != 'picked_up':
            flash('Order must be picked up first.', 'danger')
            return redirect(url_for('driver.dashboard'))
        
        # Generate delivery PIN
        delivery_pin = generate_delivery_pin()
        
        # Update order status and set PIN
        order.order_status = 'in_transit'
        order.delivery_pin = delivery_pin
        order.estimated_delivery = datetime.utcnow() + timedelta(minutes=30)
        order.updated_at = datetime.utcnow()
        
        status_update = OrderStatus(
            order_id=order.id,
            status='in_transit',
            notes=f'Driver {current_user.name} is en route to delivery location. ETA: 30 minutes.',
            user_id=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(status_update)
        
        # Send PIN to customer via notification
        customer_notification = Notification(
            user_id=order.customer_id,
            title='Delivery PIN - Order Out for Delivery!',
            message=f'Your order #{order_number} is out for delivery! Your delivery PIN is: {delivery_pin}\n\nPlease share this PIN with the driver when they arrive to confirm delivery.',
            type='info',
            link=url_for('order.order_detail', order_number=order_number),
            created_at=datetime.utcnow()
        )
        db.session.add(customer_notification)
        
        db.session.commit()
        
        flash(f'Delivery started for {order_number}! PIN {delivery_pin} sent to customer. ETA: 30 minutes.', 'success')
        return redirect(url_for('driver.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('driver.dashboard'))

@driver_bp.route('/complete-delivery/<order_number>', methods=['POST'])
@login_required
@driver_required
def complete_delivery(order_number):
    """Driver completes delivery with PIN verification"""
    try:
        order = Order.query.filter_by(order_number=order_number).first_or_404()
        
        if order.driver_id != current_user.id:
            flash('You are not assigned to this order.', 'danger')
            return redirect(url_for('driver.dashboard'))
        
        if order.order_status != 'in_transit':
            flash('Order must be in transit first.', 'danger')
            return redirect(url_for('driver.dashboard'))
        
        delivery_pin = request.form.get('delivery_pin', '').strip()
        
        # Verify delivery PIN
        if not delivery_pin or delivery_pin != order.delivery_pin:
            flash(f'Invalid delivery PIN. Please check with the customer.', 'danger')
            return redirect(url_for('driver.dashboard'))
        
        order.order_status = 'delivered'
        order.actual_delivery = datetime.utcnow()
        order.updated_at = datetime.utcnow()
        
        driver_earnings = (order.delivery_fee * 0.7) + 5.00
        
        status_update = OrderStatus(
            order_id=order.id,
            status='delivered',
            notes=f'Order delivered successfully by {current_user.name}. Customer PIN verified.',
            user_id=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(status_update)
        
        customer_notification = Notification(
            user_id=order.customer_id,
            title='Order Delivered!',
            message=f'Your order #{order_number} has been delivered. Thank you for using Jozini Move!',
            type='success',
            link=url_for('order.review_order', order_number=order_number),
            created_at=datetime.utcnow()
        )
        db.session.add(customer_notification)
        
        shop_notification = Notification(
            user_id=order.shop.owner_id,
            title='Order Completed',
            message=f'Order #{order_number} has been delivered successfully.',
            type='success',
            link=url_for('order.order_detail', order_number=order_number),
            created_at=datetime.utcnow()
        )
        db.session.add(shop_notification)
        
        db.session.commit()
        
        flash(f'Order delivered successfully! You earned {format_currency(driver_earnings)}.', 'success')
        return redirect(url_for('driver.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('driver.dashboard'))

@driver_bp.route('/order-details/<order_number>')
@login_required
@driver_required
def order_details(order_number):
    """View order details for driver"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    
    items = json.loads(order.items_json) if order.items_json else []
    status_history = OrderStatus.query.filter_by(order_id=order.id)\
                                     .order_by(OrderStatus.created_at.asc())\
                                     .all()
    shop = Shop.query.get(order.shop_id)
    
    driver_earnings = None
    if order.order_status == 'delivered':
        driver_earnings = (order.delivery_fee * 0.7) + 5.00
    
    return render_template('driver/order_details.html',
                         order=order,
                         items=items,
                         status_history=status_history,
                         shop=shop,
                         driver_earnings=driver_earnings,
                         format_currency=format_currency)

@driver_bp.route('/earnings')
@login_required
@driver_required
def earnings():
    """Driver earnings report"""
    from sqlalchemy import extract, func
    from datetime import datetime, timedelta
    
    # Get filter parameters
    period = request.args.get('period', 'monthly')
    year = request.args.get('year', type=int, default=datetime.utcnow().year)
    month = request.args.get('month', type=int, default=datetime.utcnow().month)
    
    # Base query for delivered orders
    base_query = Order.query.filter(
        Order.driver_id == current_user.id,
        Order.order_status == 'delivered'
    )
    
    # Total earnings (all time)
    total_deliveries = base_query.count()
    total_fees = base_query.with_entities(func.sum(Order.delivery_fee)).scalar() or 0
    total_earnings = (total_fees * 0.7) + (total_deliveries * 5)
    
    # Earnings by month (last 12 months)
    monthly_earnings = db.session.query(
        extract('year', Order.updated_at).label('year'),
        extract('month', Order.updated_at).label('month'),
        func.count(Order.id).label('deliveries'),
        func.sum(Order.delivery_fee).label('total_fees')
    ).filter(
        Order.driver_id == current_user.id,
        Order.order_status == 'delivered'
    ).group_by('year', 'month')\
     .order_by(extract('year', Order.updated_at).desc(), extract('month', Order.updated_at).desc()).all()
    
    monthly_data = []
    for item in monthly_earnings:
        if item.year and item.month:
            earnings = (item.total_fees or 0) * 0.7 + (item.deliveries * 5)
            month_name = datetime(int(item.year), int(item.month), 1).strftime('%B %Y')
            monthly_data.append({
                'year': int(item.year),
                'month': int(item.month),
                'month_name': month_name,
                'deliveries': item.deliveries,
                'total_fees': float(item.total_fees or 0),
                'earnings': float(earnings)
            })
    
    # Weekly earnings (last 7 days)
    weekly_earnings = []
    today = datetime.utcnow().date()
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        day_orders = Order.query.filter(
            Order.driver_id == current_user.id,
            Order.order_status == 'delivered',
            func.date(Order.updated_at) == date
        ).all()
        
        day_deliveries = len(day_orders)
        day_fees = sum(o.delivery_fee for o in day_orders)
        day_earnings = (day_fees * 0.7) + (day_deliveries * 5)
        
        weekly_earnings.append({
            'date': date.strftime('%a'),
            'full_date': date.strftime('%Y-%m-%d'),
            'deliveries': day_deliveries,
            'earnings': float(day_earnings)
        })
    
    # Get selected month data
    selected_month_data = None
    for data in monthly_data:
        if data['year'] == year and data['month'] == month:
            selected_month_data = data
            break
    
    # Get daily breakdown for selected month
    daily_breakdown = []
    if selected_month_data:
        # Get first and last day of selected month
        first_day = datetime(year, month, 1).date()
        if month == 12:
            last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
        
        daily_orders = Order.query.filter(
            Order.driver_id == current_user.id,
            Order.order_status == 'delivered',
            func.date(Order.updated_at) >= first_day,
            func.date(Order.updated_at) <= last_day
        ).order_by(Order.updated_at.desc()).all()
        
        for order in daily_orders:
            daily_breakdown.append({
                'order_number': order.order_number,
                'date': order.updated_at.strftime('%Y-%m-%d'),
                'delivery_fee': order.delivery_fee,
                'earnings': (order.delivery_fee * 0.7) + 5
            })
    
    # Chart data for last 6 months
    chart_months = []
    chart_earnings = []
    chart_deliveries = []
    
    for i in range(5, -1, -1):
        # Calculate date for i months ago
        current_date = datetime.utcnow().date()
        target_month = current_date.replace(day=1) - timedelta(days=30 * i)
        target_year = target_month.year
        target_month_num = target_month.month
        
        found = False
        for data in monthly_data:
            if data['year'] == target_year and data['month'] == target_month_num:
                chart_months.append(data['month_name'][:3])
                chart_earnings.append(data['earnings'])
                chart_deliveries.append(data['deliveries'])
                found = True
                break
        
        if not found:
            chart_months.append(target_month.strftime('%b'))
            chart_earnings.append(0)
            chart_deliveries.append(0)
    
    return render_template('driver/earnings.html',
                         total_deliveries=total_deliveries,
                         total_earnings=float(total_earnings),
                         monthly_data=monthly_data,
                         weekly_earnings=weekly_earnings,
                         daily_breakdown=daily_breakdown,
                         selected_month_data=selected_month_data,
                         chart_months=chart_months,
                         chart_earnings=chart_earnings,
                         chart_deliveries=chart_deliveries,
                         current_year=year,
                         current_month=month,
                         format_currency=format_currency)

@driver_bp.route('/api/available-count')
@login_required
@driver_required
def available_count():
    """API endpoint to get count of available orders"""
    count = Order.query.filter(
        Order.order_status == 'ready',
        Order.driver_id.is_(None)
    ).count()
    return jsonify({'count': count})
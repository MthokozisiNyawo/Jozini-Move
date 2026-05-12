from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db, cache
from app.models import User, Shop, Item, Order, OrderStatus, Notification, DeliveryZone, Settings, AuditLog
from app.forms import DeliveryZoneForm
from app.utils.helpers import format_currency
from app.utils.decorators import admin_required
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_
import json

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard with analytics"""
    # Get date range for filtering
    days = request.args.get('days', 30, type=int)
    start_date = datetime.utcnow().date() - timedelta(days=days)
    
    # Basic statistics
    total_users = User.query.count()
    total_shops = Shop.query.count()
    total_orders = Order.query.count()
    total_drivers = User.query.filter_by(user_type='driver').count()
    
    # Revenue statistics
    total_revenue = db.session.query(func.sum(Order.grand_total)).filter(
        Order.order_status == 'delivered'
    ).scalar() or 0
    
    today_revenue = db.session.query(func.sum(Order.grand_total)).filter(
        Order.order_status == 'delivered',
        func.date(Order.updated_at) == datetime.utcnow().date()
    ).scalar() or 0
    
    pending_revenue = db.session.query(func.sum(Order.grand_total)).filter(
        Order.payment_status == 'pending',
        Order.order_status != 'cancelled'
    ).scalar() or 0
    
    # Platform fee revenue (30% of delivery fees)
    platform_revenue = db.session.query(func.sum(Order.delivery_fee)).filter(
        Order.order_status == 'delivered'
    ).scalar() or 0
    platform_revenue = platform_revenue * 0.3
    
    # Order statistics
    today_orders = Order.query.filter(
        func.date(Order.created_at) == datetime.utcnow().date()
    ).count()
    
    pending_orders = Order.query.filter_by(order_status='pending').count()
    processing_orders = Order.query.filter(
        Order.order_status.in_(['confirmed', 'preparing', 'ready'])
    ).count()
    in_transit_orders = Order.query.filter_by(order_status='in_transit').count()
    completed_orders = Order.query.filter_by(order_status='delivered').count()
    cancelled_orders = Order.query.filter_by(order_status='cancelled').count()
    
    # Recent activities
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    recent_shops = Shop.query.order_by(Shop.created_at.desc()).limit(10).all()
    
    # Chart data - Daily orders for last 7 days
    daily_stats = []
    for i in range(7):
        date = datetime.utcnow().date() - timedelta(days=i)
        orders_count = Order.query.filter(func.date(Order.created_at) == date).count()
        revenue = db.session.query(func.sum(Order.grand_total)).filter(
            func.date(Order.created_at) == date,
            Order.order_status == 'delivered'
        ).scalar() or 0
        daily_stats.append({
            'date': date.strftime('%a'),
            'orders': orders_count,
            'revenue': float(revenue)
        })
    daily_stats.reverse()
    
    # Monthly stats for chart
    monthly_stats = []
    for i in range(6):
        month_start = datetime.utcnow().replace(day=1) - timedelta(days=30*i)
        month_end = (month_start + timedelta(days=32)).replace(day=1)
        orders_count = Order.query.filter(
            Order.created_at >= month_start,
            Order.created_at < month_end
        ).count()
        revenue = db.session.query(func.sum(Order.grand_total)).filter(
            Order.created_at >= month_start,
            Order.created_at < month_end,
            Order.order_status == 'delivered'
        ).scalar() or 0
        monthly_stats.append({
            'month': month_start.strftime('%B'),
            'orders': orders_count,
            'revenue': float(revenue)
        })
    monthly_stats.reverse()
    
    # User growth
    user_growth = []
    for i in range(7):
        date = datetime.utcnow().date() - timedelta(days=i)
        new_users = User.query.filter(func.date(User.created_at) == date).count()
        user_growth.append({
            'date': date.strftime('%a'),
            'users': new_users
        })
    user_growth.reverse()
    
    # Top performing shops
    top_shops = db.session.query(
        Shop.id,
        Shop.shop_name,
        Shop.logo,
        func.count(Order.id).label('total_orders'),
        func.sum(Order.grand_total).label('total_revenue')
    ).join(Order, Order.shop_id == Shop.id)\
     .filter(Order.order_status == 'delivered')\
     .group_by(Shop.id)\
     .order_by(func.sum(Order.grand_total).desc())\
     .limit(10).all()
    
    # Top drivers
    top_drivers = db.session.query(
        User.id,
        User.name,
        User.phone,
        func.count(Order.id).label('total_deliveries'),
        func.sum(Order.delivery_fee).label('total_earnings')
    ).join(Order, Order.driver_id == User.id)\
     .filter(Order.order_status == 'delivered')\
     .group_by(User.id)\
     .order_by(func.count(Order.id).desc())\
     .limit(10).all()
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_shops=total_shops,
                         total_orders=total_orders,
                         total_drivers=total_drivers,
                         total_revenue=total_revenue,
                         today_revenue=today_revenue,
                         pending_revenue=pending_revenue,
                         platform_revenue=platform_revenue,
                         today_orders=today_orders,
                         pending_orders=pending_orders,
                         processing_orders=processing_orders,
                         in_transit_orders=in_transit_orders,
                         completed_orders=completed_orders,
                         cancelled_orders=cancelled_orders,
                         recent_orders=recent_orders,
                         recent_users=recent_users,
                         recent_shops=recent_shops,
                         daily_stats=daily_stats,
                         monthly_stats=monthly_stats,
                         user_growth=user_growth,
                         top_shops=top_shops,
                         top_drivers=top_drivers,
                         days=days,
                         format_currency=format_currency)

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """Manage users"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    user_type = request.args.get('type', '')
    status = request.args.get('status', '')
    
    query = User.query
    
    if search:
        query = query.filter(
            or_(
                User.name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.phone.ilike(f'%{search}%')
            )
        )
    
    if user_type:
        query = query.filter_by(user_type=user_type)
    
    if status:
        is_active = status == 'active'
        query = query.filter_by(is_active=is_active)
    
    users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20)
    
    # Statistics
    total_customers = User.query.filter_by(user_type='customer').count()
    total_drivers = User.query.filter_by(user_type='driver').count()
    total_shop_owners = User.query.filter_by(user_type='shop_owner').count()
    active_users = User.query.filter_by(is_active=True).count()
    
    return render_template('admin/users.html',
                         users=users,
                         search=search,
                         user_type=user_type,
                         status=status,
                         total_customers=total_customers,
                         total_drivers=total_drivers,
                         total_shop_owners=total_shop_owners,
                         active_users=active_users)

@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    """View user details"""
    user = User.query.get_or_404(user_id)
    
    # Get user statistics
    total_orders = Order.query.filter_by(customer_id=user_id).count()
    total_spent = db.session.query(func.sum(Order.grand_total)).filter(
        Order.customer_id == user_id,
        Order.order_status == 'delivered'
    ).scalar() or 0
    
    if user.is_driver():
        deliveries = Order.query.filter_by(driver_id=user_id, order_status='delivered').count()
        earnings = db.session.query(func.sum(Order.delivery_fee)).filter(
            Order.driver_id == user_id,
            Order.order_status == 'delivered'
        ).scalar() or 0
        earnings = earnings * 0.7 + (deliveries * 5)
    else:
        deliveries = 0
        earnings = 0
    
    if user.is_shop_owner():
        shops = Shop.query.filter_by(owner_id=user_id).all()
        shop_orders = Order.query.filter(Order.shop_id.in_([s.id for s in shops])).count()
        shop_revenue = db.session.query(func.sum(Order.grand_total)).filter(
            Order.shop_id.in_([s.id for s in shops]),
            Order.order_status == 'delivered'
        ).scalar() or 0
    else:
        shops = []
        shop_orders = 0
        shop_revenue = 0
    
    # Recent orders
    recent_orders = Order.query.filter_by(customer_id=user_id)\
                               .order_by(Order.created_at.desc())\
                               .limit(20).all()
    
    return render_template('admin/user_detail.html',
                         user=user,
                         total_orders=total_orders,
                         total_spent=total_spent,
                         deliveries=deliveries,
                         earnings=earnings,
                         shops=shops,
                         shop_orders=shop_orders,
                         shop_revenue=shop_revenue,
                         recent_orders=recent_orders,
                         format_currency=format_currency)

@admin_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    """Activate/deactivate user"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': 'Cannot deactivate yourself'})
    
    user.is_active = not user.is_active
    
    # Create notification for user
    notification = Notification(
        user_id=user.id,
        title='Account Status Updated',
        message=f'Your account has been {"activated" if user.is_active else "deactivated"} by admin.',
        type='warning' if not user.is_active else 'success'
    )
    db.session.add(notification)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'is_active': user.is_active,
        'message': f'User {user.name} has been {"activated" if user.is_active else "deactivated"}'
    })

@admin_bp.route('/users/<int:user_id>/make-admin', methods=['POST'])
@login_required
@admin_required
def make_admin(user_id):
    """Make user an admin"""
    user = User.query.get_or_404(user_id)
    user.user_type = 'admin'
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'{user.name} is now an admin'})

@admin_bp.route('/shops')
@login_required
@admin_required
def shops():
    """Manage shops"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    category = request.args.get('category', '')
    
    query = Shop.query
    
    if search:
        query = query.filter(
            or_(
                Shop.shop_name.ilike(f'%{search}%'),
                Shop.address.ilike(f'%{search}%')
            )
        )
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    if category:
        query = query.filter_by(category=category)
    
    shops = query.order_by(Shop.created_at.desc()).paginate(page=page, per_page=20)
    
    # Statistics
    pending_shops = Shop.query.filter_by(status='pending').count()
    active_shops = Shop.query.filter_by(status='active').count()
    suspended_shops = Shop.query.filter_by(status='suspended').count()
    total_shops = Shop.query.count()
    
    # Categories
    categories = db.session.query(Shop.category, func.count(Shop.id))\
                          .group_by(Shop.category).all()
    
    return render_template('admin/shops.html',
                         shops=shops,
                         search=search,
                         status_filter=status_filter,
                         category=category,
                         pending_shops=pending_shops,
                         active_shops=active_shops,
                         suspended_shops=suspended_shops,
                         total_shops=total_shops,
                         categories=categories)

@admin_bp.route('/shops/<int:shop_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_shop(shop_id):
    """Approve a pending shop"""
    shop = Shop.query.get_or_404(shop_id)
    shop.status = 'active'
    db.session.commit()
    
    # Notify shop owner
    notification = Notification(
        user_id=shop.owner_id,
        title='Shop Approved!',
        message=f'Your shop "{shop.shop_name}" has been approved and is now live!',
        type='success',
        link=url_for('shop.shop_detail', shop_id=shop.id)
    )
    db.session.add(notification)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Shop {shop.shop_name} has been approved'})

@admin_bp.route('/shops/<int:shop_id>/suspend', methods=['POST'])
@login_required
@admin_required
def suspend_shop(shop_id):
    """Suspend a shop"""
    shop = Shop.query.get_or_404(shop_id)
    shop.status = 'suspended'
    db.session.commit()
    
    notification = Notification(
        user_id=shop.owner_id,
        title='Shop Suspended',
        message=f'Your shop "{shop.shop_name}" has been suspended. Please contact support.',
        type='danger'
    )
    db.session.add(notification)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Shop {shop.shop_name} has been suspended'})

@admin_bp.route('/orders')
@login_required
@admin_required
def orders():
    """Manage all orders"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    payment_status = request.args.get('payment', '')
    search = request.args.get('search', '')
    
    query = Order.query
    
    if status_filter:
        query = query.filter_by(order_status=status_filter)
    
    if payment_status:
        query = query.filter_by(payment_status=payment_status)
    
    if search:
        query = query.filter(Order.order_number.ilike(f'%{search}%'))
    
    orders = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=30)
    
    # Statistics
    order_stats = {
        'pending': Order.query.filter_by(order_status='pending').count(),
        'processing': Order.query.filter(Order.order_status.in_(['confirmed', 'preparing', 'ready'])).count(),
        'in_transit': Order.query.filter_by(order_status='in_transit').count(),
        'delivered': Order.query.filter_by(order_status='delivered').count(),
        'cancelled': Order.query.filter_by(order_status='cancelled').count()
    }
    
    return render_template('admin/orders.html',
                         orders=orders,
                         status_filter=status_filter,
                         payment_status=payment_status,
                         search=search,
                         order_stats=order_stats)

@admin_bp.route('/orders/<order_number>')
@login_required
@admin_required
def order_detail(order_number):
    """View order details"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    
    items = json.loads(order.items_json) if order.items_json else []
    status_history = OrderStatus.query.filter_by(order_id=order.id)\
                                     .order_by(OrderStatus.created_at.asc())\
                                     .all()
    
    return render_template('admin/order_detail.html',
                         order=order,
                         items=items,
                         status_history=status_history,
                         format_currency=format_currency)

@admin_bp.route('/delivery-zones', methods=['GET', 'POST'])
@login_required
@admin_required
def delivery_zones():
    """Manage delivery zones"""
    form = DeliveryZoneForm()
    
    if form.validate_on_submit():
        zone = DeliveryZone(
            name=form.name.data,
            description=form.description.data,
            delivery_fee=float(form.delivery_fee.data),
            estimated_time=form.estimated_time.data,
            min_order=float(form.min_order.data) if form.min_order.data else 0,
            is_active=form.is_active.data
        )
        db.session.add(zone)
        db.session.commit()
        flash('Delivery zone added successfully!', 'success')
        return redirect(url_for('admin.delivery_zones'))
    
    zones = DeliveryZone.query.all()
    return render_template('admin/delivery_zones.html', form=form, zones=zones)

@admin_bp.route('/delivery-zones/<int:zone_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_delivery_zone(zone_id):
    """Edit delivery zone"""
    zone = DeliveryZone.query.get_or_404(zone_id)
    
    data = request.get_json()
    zone.name = data.get('name')
    zone.description = data.get('description')
    zone.delivery_fee = float(data.get('delivery_fee'))
    zone.estimated_time = int(data.get('estimated_time'))
    zone.min_order = float(data.get('min_order', 0))
    zone.is_active = data.get('is_active', True)
    
    db.session.commit()
    return jsonify({'success': True})

@admin_bp.route('/delivery-zones/<int:zone_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_delivery_zone(zone_id):
    """Delete delivery zone"""
    zone = DeliveryZone.query.get_or_404(zone_id)
    db.session.delete(zone)
    db.session.commit()
    return jsonify({'success': True})

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    """System settings"""
    if request.method == 'POST':
        # General settings
        Settings.set('app_name', request.form.get('app_name', 'Jozini Move'))
        Settings.set('app_description', request.form.get('app_description', ''))
        Settings.set('contact_email', request.form.get('contact_email', ''))
        Settings.set('contact_phone', request.form.get('contact_phone', ''))
        Settings.set('address', request.form.get('address', ''))
        
        # Delivery settings
        Settings.set('delivery_fee', request.form.get('delivery_fee', '20'))
        Settings.set('service_fee', request.form.get('service_fee', '5'))
        Settings.set('driver_percentage', request.form.get('driver_percentage', '70'))
        Settings.set('free_delivery_min', request.form.get('free_delivery_min', '200'))
        
        # Payment settings
        Settings.set('payment_methods', request.form.get('payment_methods', 'cash,card,mobile_money'))
        Settings.set('cash_on_delivery', request.form.get('cash_on_delivery', 'true'))
        
        # Notification settings
        Settings.set('sms_enabled', request.form.get('sms_enabled', 'false'))
        Settings.set('email_enabled', request.form.get('email_enabled', 'false'))
        
        # Commission settings
        Settings.set('platform_commission', request.form.get('platform_commission', '10'))
        
        flash('Settings saved successfully!', 'success')
        return redirect(url_for('admin.settings'))
    
    # Get current settings
    settings = {
        'app_name': Settings.get('app_name', 'Jozini Move'),
        'app_description': Settings.get('app_description', ''),
        'contact_email': Settings.get('contact_email', ''),
        'contact_phone': Settings.get('contact_phone', ''),
        'address': Settings.get('address', ''),
        'delivery_fee': Settings.get('delivery_fee', '20'),
        'service_fee': Settings.get('service_fee', '5'),
        'driver_percentage': Settings.get('driver_percentage', '70'),
        'free_delivery_min': Settings.get('free_delivery_min', '200'),
        'payment_methods': Settings.get('payment_methods', 'cash,card,mobile_money'),
        'cash_on_delivery': Settings.get('cash_on_delivery', 'true'),
        'sms_enabled': Settings.get('sms_enabled', 'false'),
        'email_enabled': Settings.get('email_enabled', 'false'),
        'platform_commission': Settings.get('platform_commission', '10')
    }
    
    return render_template('admin/settings.html', settings=settings)

@admin_bp.route('/reports/sales')
@login_required
@admin_required
def reports_sales():
    """Sales report page"""
    from datetime import datetime, timedelta
    from sqlalchemy import func, extract
    
    # Get filter parameters
    period = request.args.get('period', 'monthly')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Set date range based on period
    today = datetime.utcnow().date()
    
    if start_date and end_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            start_date = today - timedelta(days=30)
            end_date = today
    elif period == 'daily':
        start_date = today
        end_date = today
    elif period == 'weekly':
        start_date = today - timedelta(days=7)
        end_date = today
    elif period == 'monthly':
        start_date = today.replace(day=1)
        end_date = today
    elif period == 'yearly':
        start_date = today.replace(month=1, day=1)
        end_date = today
    else:
        start_date = today - timedelta(days=30)
        end_date = today
    
    # Get sales data
    sales_results = db.session.query(
        func.date(Order.created_at).label('date'),
        func.count(Order.id).label('orders'),
        func.sum(Order.grand_total).label('revenue'),
        func.avg(Order.grand_total).label('avg_order'),
        func.sum(Order.delivery_fee).label('total_delivery_fees'),
        func.sum(Order.service_fee).label('total_service_fees')
    ).filter(
        Order.created_at >= start_date,
        Order.created_at <= end_date + timedelta(days=1),
        Order.order_status == 'delivered'
    ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()
    
    # Convert to list of dictionaries with string dates
    sales_data = []
    for result in sales_results:
        sales_data.append({
            'date': result.date.strftime('%Y-%m-%d') if hasattr(result.date, 'strftime') else str(result.date),
            'orders': result.orders,
            'revenue': float(result.revenue or 0),
            'avg_order': float(result.avg_order or 0),
            'total_delivery_fees': float(result.total_delivery_fees or 0),
            'total_service_fees': float(result.total_service_fees or 0)
        })
    
    # Calculate totals
    total_orders = sum(s['orders'] for s in sales_data)
    total_revenue = sum(s['revenue'] for s in sales_data)
    total_delivery_fees = sum(s['total_delivery_fees'] for s in sales_data)
    total_service_fees = sum(s['total_service_fees'] for s in sales_data)
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
    
    # Platform revenue (30% of delivery fees)
    platform_revenue = total_delivery_fees * 0.3
    
    # Get top shops
    top_shops = db.session.query(
        Shop.id,
        Shop.shop_name,
        Shop.logo,
        func.count(Order.id).label('orders'),
        func.sum(Order.grand_total).label('revenue')
    ).join(Order, Order.shop_id == Shop.id)\
     .filter(
         Order.created_at >= start_date,
         Order.created_at <= end_date + timedelta(days=1),
         Order.order_status == 'delivered'
     )\
     .group_by(Shop.id)\
     .order_by(func.sum(Order.grand_total).desc())\
     .limit(10).all()
    
    # Get top customers
    top_customers = db.session.query(
        User.id,
        User.name,
        User.email,
        func.count(Order.id).label('orders'),
        func.sum(Order.grand_total).label('spent')
    ).join(Order, Order.customer_id == User.id)\
     .filter(
         Order.created_at >= start_date,
         Order.created_at <= end_date + timedelta(days=1),
         Order.order_status == 'delivered'
     )\
     .group_by(User.id)\
     .order_by(func.sum(Order.grand_total).desc())\
     .limit(10).all()
    
    # Prepare chart data
    chart_labels = [s['date'] for s in sales_data]
    chart_orders = [s['orders'] for s in sales_data]
    chart_revenue = [s['revenue'] for s in sales_data]
    
    return render_template('admin/reports_sales.html',
                         sales_data=sales_data,
                         total_orders=total_orders,
                         total_revenue=total_revenue,
                         total_delivery_fees=total_delivery_fees,
                         total_service_fees=total_service_fees,
                         avg_order_value=avg_order_value,
                         platform_revenue=platform_revenue,
                         top_shops=top_shops,
                         top_customers=top_customers,
                         chart_labels=chart_labels,
                         chart_orders=chart_orders,
                         chart_revenue=chart_revenue,
                         period=period,
                         start_date=start_date.strftime('%Y-%m-%d'),
                         end_date=end_date.strftime('%Y-%m-%d'),
                         format_currency=format_currency)

@admin_bp.route('/audit-logs')
@login_required
@admin_required
def audit_logs():
    """View system audit logs"""
    from datetime import datetime, timedelta
    
    page = request.args.get('page', 1, type=int)
    action = request.args.get('action', '')
    user_id = request.args.get('user_id', '', type=int)
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    
    query = AuditLog.query
    
    if action:
        query = query.filter(AuditLog.action == action)
    
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(AuditLog.created_at >= start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(AuditLog.created_at <= end)
        except ValueError:
            pass
    
    logs = query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    
    # Get unique actions for filter
    actions = db.session.query(AuditLog.action).distinct().all()
    actions = [a[0] for a in actions if a[0]]
    
    # Get users for filter
    users = User.query.all()
    
    return render_template('admin/audit_logs.html',
                         logs=logs,
                         actions=actions,
                         users=users,
                         selected_action=action,
                         selected_user_id=user_id,
                         start_date=start_date,
                         end_date=end_date)

@admin_bp.route('/clear-cache', methods=['POST'])
@login_required
@admin_required
def clear_cache():
    """Clear application cache"""
    cache.clear()
    return jsonify({'success': True, 'message': 'Cache cleared successfully'})

@admin_bp.route('/backup', methods=['POST'])
@login_required
@admin_required
def backup_database():
    """Trigger database backup"""
    # Implement database backup logic here
    # This would typically call a backup script
    return jsonify({'success': True, 'message': 'Backup initiated'})

@admin_bp.route('/api/stats')
@login_required
@admin_required
def api_stats():
    """API endpoint for real-time stats"""
    # Real-time statistics for dashboard widgets
    stats = {
        'online_users': 0,  # Would need session tracking
        'active_drivers': User.query.filter_by(user_type='driver', is_active=True).count(),
        'pending_orders': Order.query.filter_by(order_status='pending').count(),
        'today_revenue': float(db.session.query(func.sum(Order.grand_total)).filter(
            func.date(Order.created_at) == datetime.utcnow().date(),
            Order.order_status == 'delivered'
        ).scalar() or 0)
    }
    return jsonify(stats)

@admin_bp.route('/shops/<int:shop_id>')
@login_required
@admin_required
def shop_detail(shop_id):
    """View shop details"""
    shop = Shop.query.get_or_404(shop_id)
    
    # Get shop statistics
    total_orders = Order.query.filter_by(shop_id=shop_id).count()
    completed_orders = Order.query.filter_by(shop_id=shop_id, order_status='delivered').count()
    total_revenue = db.session.query(func.sum(Order.grand_total)).filter(
        Order.shop_id == shop_id,
        Order.order_status == 'delivered'
    ).scalar() or 0
    
    # Get recent orders
    recent_orders = Order.query.filter_by(shop_id=shop_id)\
                               .order_by(Order.created_at.desc())\
                               .limit(10).all()
    
    # Get menu items
    menu_items = Item.query.filter_by(shop_id=shop_id).all()
    
    return render_template('admin/shop_detail.html',
                         shop=shop,
                         total_orders=total_orders,
                         completed_orders=completed_orders,
                         total_revenue=total_revenue,
                         recent_orders=recent_orders,
                         menu_items=menu_items,
                         format_currency=format_currency)
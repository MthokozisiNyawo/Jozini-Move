from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Shop, Item, Cart, Order, Notification, User
from app.forms import ShopRegistrationForm, ItemForm
from app.utils.helpers import save_shop_logo, save_item_image, format_currency
from app.utils.decorators import shop_owner_required
from sqlalchemy import func
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import os
import json
import qrcode
from io import BytesIO
import base64

shop_bp = Blueprint('shop', __name__)

@shop_bp.route('/')
def browse():
    """Browse all shops"""
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', 'all')
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'rating')
    
    query = Shop.query.filter_by(status='active')
    
    # If user is a shop owner, exclude their own shops from browsing
    if current_user.is_authenticated and current_user.is_shop_owner():
        user_shop_ids = [shop.id for shop in current_user.shops.all()]
        if user_shop_ids:
            query = query.filter(Shop.id.notin_(user_shop_ids))
    
    if category != 'all':
        query = query.filter_by(category=category)
    
    if search:
        query = query.filter(Shop.shop_name.ilike(f'%{search}%') | 
                            Shop.description.ilike(f'%{search}%'))
    
    if sort == 'rating':
        query = query.order_by(Shop.rating.desc())
    elif sort == 'newest':
        query = query.order_by(Shop.created_at.desc())
    elif sort == 'name':
        query = query.order_by(Shop.shop_name.asc())
    
    pagination = query.paginate(page=page, per_page=12, error_out=False)
    shops = pagination.items
    
    # Get all categories for filter
    categories = db.session.query(Shop.category, func.count(Shop.id))\
                          .filter_by(status='active')\
                          .group_by(Shop.category)\
                          .all()
    
    return render_template('shop/browse.html', 
                          shops=shops,
                          pagination=pagination,
                          categories=categories,
                          selected_category=category,
                          search=search,
                          sort=sort,
                          format_currency=format_currency)

@shop_bp.route('/<int:shop_id>')
def shop_detail(shop_id):
    """Shop details page"""
    shop = Shop.query.get_or_404(shop_id)
    
    if shop.status != 'active':
        flash('This shop is currently not available.', 'warning')
        return redirect(url_for('shop.browse'))
    
    # Get menu items grouped by category
    items = Item.query.filter_by(shop_id=shop_id, available=True)\
                     .order_by(Item.category, Item.name).all()
    
    items_by_category = {}
    for item in items:
        category = item.category or 'Other'
        if category not in items_by_category:
            items_by_category[category] = []
        items_by_category[category].append(item)
    
    # Get cart count for this shop
    cart_count = 0
    if current_user.is_authenticated and current_user.is_customer():
        cart_count = Cart.query.filter_by(
            user_id=current_user.id, 
            shop_id=shop_id
        ).count()
    
    # Get shop reviews from completed orders
    reviews = Order.query.filter_by(
        shop_id=shop_id, 
        order_status='delivered'
    ).filter(Order.customer_review.isnot(None))\
     .order_by(Order.updated_at.desc())\
     .limit(10).all()
    
    return render_template('shop/menu.html', 
                          shop=shop, 
                          items_by_category=items_by_category,
                          cart_count=cart_count,
                          reviews=reviews,
                          format_currency=format_currency)

@shop_bp.route('/add-to-cart', methods=['POST'])
@login_required
def add_to_cart():
    """Add item to cart (AJAX)"""
    # Shop owners cannot add items to cart from their own shop
    if current_user.is_shop_owner():
        return jsonify({'success': False, 'message': 'Shop owners cannot add items to cart. Please use a customer account.'})
    
    if not current_user.is_customer():
        return jsonify({'success': False, 'message': 'Only customers can add items to cart'})
    
    try:
        data = request.get_json()
        item_id = data.get('item_id')
        quantity = int(data.get('quantity', 1))
        
        if not item_id:
            return jsonify({'success': False, 'message': 'Item ID required'})
        
        item = Item.query.get_or_404(item_id)
        
        # Check if the shop owner is trying to add their own item
        if item.shop.owner_id == current_user.id:
            return jsonify({'success': False, 'message': 'You cannot add items from your own shop to cart.'})
        
        if not item.available:
            return jsonify({'success': False, 'message': 'Item is not available'})
        
        if not item.is_in_stock(quantity):
            return jsonify({'success': False, 'message': 'Insufficient stock'})
        
        # Check if item already in cart
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
        
        # Get updated cart count for this shop
        cart_count = Cart.query.filter_by(
            user_id=current_user.id,
            shop_id=item.shop_id
        ).count()
        
        return jsonify({
            'success': True,
            'message': f'{item.name} added to cart',
            'cart_count': cart_count
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@shop_bp.route('/cart/<int:shop_id>')
@login_required
def view_cart(shop_id):
    """View cart for a specific shop"""
    if not current_user.is_customer():
        flash('Only customers can view cart', 'danger')
        return redirect(url_for('main.index'))
    
    shop = Shop.query.get_or_404(shop_id)
    cart_items = Cart.query.filter_by(
        user_id=current_user.id,
        shop_id=shop_id
    ).all()
    
    if not cart_items:
        flash('Your cart is empty', 'info')
        return redirect(url_for('shop.shop_detail', shop_id=shop_id))
    
    # Calculate subtotal
    subtotal = sum(item.item.price * item.quantity for item in cart_items)
    
    return render_template('shop/cart.html', 
                          shop=shop, 
                          cart_items=cart_items,
                          subtotal=subtotal,
                          format_currency=format_currency)

@shop_bp.route('/update-cart', methods=['POST'])
@login_required
def update_cart():
    """Update cart item quantity (AJAX)"""
    if not current_user.is_customer():
        return jsonify({'success': False, 'message': 'Only customers can update cart'})
    
    try:
        cart_id = request.form.get('cart_id')
        action = request.form.get('action')
        
        cart_item = Cart.query.get_or_404(cart_id)
        
        if cart_item.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'})
        
        if action == 'increase':
            if not cart_item.item.is_in_stock(cart_item.quantity + 1):
                return jsonify({'success': False, 'message': 'Insufficient stock'})
            cart_item.quantity += 1
        elif action == 'decrease':
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
            else:
                db.session.delete(cart_item)
        elif action == 'remove':
            db.session.delete(cart_item)
        
        db.session.commit()
        
        # Recalculate totals
        cart_items = Cart.query.filter_by(
            user_id=current_user.id,
            shop_id=cart_item.shop_id
        ).all()
        
        subtotal = sum(item.item.price * item.quantity for item in cart_items)
        
        return jsonify({
            'success': True,
            'subtotal': format_currency(subtotal),
            'item_count': len(cart_items)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@shop_bp.route('/dashboard')
@login_required
@shop_owner_required
def shop_dashboard():
    """Shop owner dashboard"""
    # Get user's shops
    shops = current_user.shops.all()
    
    if not shops:
        return redirect(url_for('shop.register_shop'))
    
    # Get section from query parameter
    section = request.args.get('section', 'overview')
    selected_shop_id = request.args.get('shop_id', type=int)
    
    # Select shop (first shop if none selected)
    if selected_shop_id:
        selected_shop = Shop.query.get(selected_shop_id)
        if selected_shop and selected_shop.owner_id == current_user.id:
            shop_ids = [selected_shop.id]
            selected_shop_obj = selected_shop
        else:
            shop_ids = [shop.id for shop in shops]
            selected_shop_obj = shops[0]
    else:
        shop_ids = [shop.id for shop in shops]
        selected_shop_obj = shops[0]
    
    # Get recent orders for selected shops
    orders = Order.query.filter(Order.shop_id.in_(shop_ids))\
                       .order_by(Order.created_at.desc())\
                       .limit(20).all()
    
    # Parse items JSON for each order
    for order in orders:
        if order.items_json:
            try:
                order.parsed_items = json.loads(order.items_json)
            except:
                order.parsed_items = []
        else:
            order.parsed_items = []
    
    # Statistics
    today = datetime.utcnow().date()
    today_orders = Order.query.filter(
        Order.shop_id.in_(shop_ids),
        func.date(Order.created_at) == today
    ).count()
    
    total_orders = Order.query.filter(Order.shop_id.in_(shop_ids)).count()
    completed_orders = Order.query.filter(
        Order.shop_id.in_(shop_ids),
        Order.order_status == 'delivered'
    ).count()
    cancelled_orders = Order.query.filter(
        Order.shop_id.in_(shop_ids),
        Order.order_status == 'cancelled'
    ).count()
    
    total_revenue = db.session.query(func.sum(Order.grand_total)).filter(
        Order.shop_id.in_(shop_ids),
        Order.order_status == 'delivered'
    ).scalar() or 0
    
    # Monthly revenue chart data
    monthly_revenue = []
    for i in range(6):
        month_start = today.replace(day=1) - relativedelta(months=i)
        month_end = month_start + relativedelta(months=1)
        revenue = db.session.query(func.sum(Order.grand_total)).filter(
            Order.shop_id.in_(shop_ids),
            Order.order_status == 'delivered',
            Order.updated_at >= month_start,
            Order.updated_at < month_end
        ).scalar() or 0
        monthly_revenue.append({
            'month': month_start.strftime('%B'),
            'revenue': float(revenue)
        })
    
    # Low stock items
    low_stock_items = Item.query.filter(
        Item.shop_id.in_(shop_ids),
        Item.stock_quantity >= 0,
        Item.stock_quantity <= 10
    ).all()
    
    # Popular items for analytics
    popular_items = db.session.query(
        Item.name,
        func.sum(Cart.quantity).label('total_sold')
    ).join(Cart, Cart.item_id == Item.id)\
     .filter(Item.shop_id.in_(shop_ids))\
     .group_by(Item.id)\
     .order_by(func.sum(Cart.quantity).desc())\
     .limit(5).all()
    
    return render_template('dashboard/shop.html',
                         shops=shops,
                         selected_shop=selected_shop_obj,
                         section=section,
                         orders=orders,
                         today_orders=today_orders,
                         total_orders=total_orders,
                         completed_orders=completed_orders,
                         cancelled_orders=cancelled_orders,
                         total_revenue=total_revenue,
                         monthly_revenue=monthly_revenue[::-1],
                         low_stock_items=low_stock_items,
                         popular_items=popular_items,
                         format_currency=format_currency)

@shop_bp.route('/register-shop', methods=['GET', 'POST'])
@login_required
@shop_owner_required
def register_shop():
    """Register a new shop"""
    form = ShopRegistrationForm()
    
    if form.validate_on_submit():
        shop = Shop(
            owner_id=current_user.id,
            shop_name=form.shop_name.data,
            category=form.category.data,
            address=form.address.data,
            phone=form.phone.data,
            email=form.email.data,
            description=form.description.data,
            opening_hours=form.opening_hours.data,
            closing_hours=form.closing_hours.data,
            delivery_fee=float(form.delivery_fee.data) if form.delivery_fee.data else 20.00,
            min_order=float(form.min_order.data) if form.min_order.data else 0,
            status='pending'  # Requires admin approval
        )
        
        try:
            db.session.add(shop)
            db.session.flush()  # Get shop ID
            
            # Save logo if uploaded
            if form.logo.data:
                filename = save_shop_logo(form.logo.data, shop.id)
                if filename:
                    shop.logo = filename
            
            db.session.commit()
            
            # Notify admin
            admin = User.query.filter_by(user_type='admin').first()
            if admin:
                admin_notification = Notification(
                    user_id=admin.id,
                    title='New Shop Registration',
                    message=f'{shop.shop_name} has been registered and pending approval.',
                    type='info',
                    link=url_for('admin.shops')
                )
                db.session.add(admin_notification)
                db.session.commit()
            
            flash('Shop registered successfully! It will be reviewed by admin.', 'success')
            return redirect(url_for('shop.shop_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to register shop: {str(e)}', 'danger')
    
    return render_template('shop/register.html', form=form)

@shop_bp.route('/<int:shop_id>/add-item', methods=['GET', 'POST'])
@login_required
@shop_owner_required
def add_item(shop_id):
    """Add item to shop menu"""
    shop = Shop.query.get_or_404(shop_id)
    
    if shop.owner_id != current_user.id:
        flash('Access denied. You do not own this shop.', 'danger')
        return redirect(url_for('shop.shop_dashboard'))
    
    form = ItemForm()
    
    if form.validate_on_submit():
        item = Item(
            shop_id=shop_id,
            name=form.name.data,
            description=form.description.data,
            price=float(form.price.data),
            category=form.category.data,
            available=form.available.data,
            is_featured=form.is_featured.data,
            preparation_time=form.preparation_time.data or 15,
            stock_quantity=form.stock_quantity.data or -1
        )
        
        try:
            db.session.add(item)
            db.session.flush()
            
            if form.image.data:
                filename = save_item_image(form.image.data, item.id)
                if filename:
                    item.image = filename
            
            db.session.commit()
            flash('Item added successfully!', 'success')
            return redirect(url_for('shop.shop_detail', shop_id=shop_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to add item: {str(e)}', 'danger')
    
    return render_template('shop/add_item.html', form=form, shop=shop)

@shop_bp.route('/edit-item/<int:item_id>', methods=['GET', 'POST'])
@login_required
@shop_owner_required
def edit_item(item_id):
    """Edit shop item"""
    item = Item.query.get_or_404(item_id)
    shop = Shop.query.get_or_404(item.shop_id)
    
    if shop.owner_id != current_user.id:
        flash('Access denied. You do not own this shop.', 'danger')
        return redirect(url_for('shop.shop_dashboard'))
    
    form = ItemForm(obj=item)
    
    if form.validate_on_submit():
        item.name = form.name.data
        item.description = form.description.data
        item.price = float(form.price.data)
        item.category = form.category.data
        item.available = form.available.data
        item.is_featured = form.is_featured.data
        item.preparation_time = form.preparation_time.data
        item.stock_quantity = form.stock_quantity.data
        
        if form.image.data:
            filename = save_item_image(form.image.data, item.id)
            if filename:
                item.image = filename
        
        try:
            db.session.commit()
            flash('Item updated successfully!', 'success')
            return redirect(url_for('shop.shop_detail', shop_id=shop.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to update item: {str(e)}', 'danger')
    
    return render_template('shop/edit_item.html', form=form, item=item, shop=shop)

@shop_bp.route('/delete-item/<int:item_id>', methods=['POST'])
@login_required
@shop_owner_required
def delete_item(item_id):
    """Delete shop item"""
    try:
        item = Item.query.get_or_404(item_id)
        shop = Shop.query.get_or_404(item.shop_id)
        
        # Check if user owns this shop
        if shop.owner_id != current_user.id:
            return jsonify({'success': False, 'message': 'Access denied. You do not own this shop.'})
        
        # Delete the image file if exists
        if item.image:
            image_path = os.path.join(current_app.root_path, 'static/uploads/items', item.image)
            if os.path.exists(image_path):
                os.remove(image_path)
        
        # Delete the item
        db.session.delete(item)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Item deleted successfully!'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})
    
@shop_bp.route('/orders/<order_number>/update', methods=['GET', 'POST'])
@login_required
@shop_owner_required
def update_order_status(order_number):
    """Update order status from shop dashboard"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    
    if order.shop.owner_id != current_user.id:
        flash('Access denied. You do not own this shop.', 'danger')
        return redirect(url_for('shop.shop_dashboard'))
    
    if request.method == 'POST':
        status = request.form.get('status')
        notes = request.form.get('notes')
        
        allowed_statuses = ['confirmed', 'preparing', 'ready', 'cancelled']
        if status not in allowed_statuses:
            flash('Invalid status update.', 'danger')
            return redirect(url_for('shop.shop_dashboard'))
        
        order.add_status_update(status, notes, current_user.id)
        
        # Notify customer
        notification = Notification(
            user_id=order.customer_id,
            title=f'Order {status.replace("_", " ").title()}',
            message=f'Your order #{order.order_number} has been {status}.',
            type='info',
            link=url_for('order.order_detail', order_number=order.order_number)
        )
        db.session.add(notification)
        db.session.commit()
        
        flash(f'Order status updated to {status}', 'success')
        return redirect(url_for('shop.shop_dashboard'))
    
    return render_template('shop/update_order.html', order=order)

@shop_bp.route('/analytics')
@login_required
@shop_owner_required
def shop_analytics():
    """Shop analytics and reports"""
    from app.models import Order, Item, Cart, User
    from sqlalchemy import func, extract
    from datetime import datetime, timedelta
    from dateutil.relativedelta import relativedelta
    
    # Get user's shops
    shops = current_user.shops.all()
    
    if not shops:
        flash('You need to register a shop first.', 'warning')
        return redirect(url_for('shop.register_shop'))
    
    # Get selected shop or first shop
    selected_shop_id = request.args.get('shop_id', type=int)
    if selected_shop_id:
        selected_shop = Shop.query.get(selected_shop_id)
        if selected_shop and selected_shop.owner_id == current_user.id:
            shop_ids = [selected_shop.id]
        else:
            shop_ids = [shop.id for shop in shops]
            selected_shop = shops[0]
    else:
        shop_ids = [shop.id for shop in shops]
        selected_shop = shops[0]
    
    # Get date range
    days = request.args.get('days', 30, type=int)
    period = request.args.get('period', 'daily')
    start_date = datetime.utcnow().date() - timedelta(days=days)
    
    # Prepare data structures
    labels = []
    revenue_data = []
    orders_data = []
    sales_data = []
    
    if period == 'daily':
        # Daily data
        daily_results = db.session.query(
            func.date(Order.created_at).label('date'),
            func.count(Order.id).label('orders'),
            func.sum(Order.grand_total).label('revenue'),
            func.avg(Order.grand_total).label('avg_order')
        ).filter(
            Order.shop_id.in_(shop_ids),
            func.date(Order.created_at) >= start_date
        ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()
        
        for result in daily_results:
            if result.date:
                date_str = result.date.strftime('%Y-%m-%d')
                labels.append(date_str)
                orders_data.append(result.orders or 0)
                revenue_data.append(float(result.revenue or 0))
                sales_data.append({
                    'date': date_str,
                    'orders': result.orders or 0,
                    'revenue': float(result.revenue or 0)
                })
    else:
        # Monthly data - use extract for year and month
        monthly_results = db.session.query(
            extract('year', Order.created_at).label('year'),
            extract('month', Order.created_at).label('month'),
            func.count(Order.id).label('orders'),
            func.sum(Order.grand_total).label('revenue')
        ).filter(
            Order.shop_id.in_(shop_ids),
            Order.created_at >= start_date
        ).group_by('year', 'month').order_by('year', 'month').all()
        
        for result in monthly_results:
            if result.year and result.month:
                month_name = datetime(int(result.year), int(result.month), 1).strftime('%B %Y')
                labels.append(month_name)
                orders_data.append(result.orders or 0)
                revenue_data.append(float(result.revenue or 0))
                sales_data.append({
                    'date': month_name,
                    'orders': result.orders or 0,
                    'revenue': float(result.revenue or 0)
                })
    
    # Total statistics
    total_orders = Order.query.filter(Order.shop_id.in_(shop_ids)).count()
    total_revenue = db.session.query(func.sum(Order.grand_total)).filter(
        Order.shop_id.in_(shop_ids),
        Order.order_status == 'delivered'
    ).scalar() or 0
    total_customers = Order.query.filter(Order.shop_id.in_(shop_ids)).distinct(Order.customer_id).count()
    avg_rating = db.session.query(func.avg(Order.customer_rating)).filter(
        Order.shop_id.in_(shop_ids),
        Order.customer_rating.isnot(None)
    ).scalar() or 0
    
    # Order status distribution
    status_data = db.session.query(
        Order.order_status,
        func.count(Order.id).label('count')
    ).filter(Order.shop_id.in_(shop_ids)).group_by(Order.order_status).all()
    
    status_distribution = {}
    for result in status_data:
        status_distribution[result.order_status] = result.count
    
    # Popular items
    popular_items = db.session.query(
        Item.id,
        Item.name,
        Item.price,
        Item.image,
        func.sum(Cart.quantity).label('total_sold'),
        func.sum(Cart.quantity * Item.price).label('total_revenue')
    ).join(Cart, Cart.item_id == Item.id)\
     .filter(Item.shop_id.in_(shop_ids))\
     .group_by(Item.id)\
     .order_by(func.sum(Cart.quantity).desc())\
     .limit(10).all()
    
    # Top customers
    top_customers = db.session.query(
        User.id,
        User.name,
        User.email,
        User.phone,
        func.count(Order.id).label('order_count'),
        func.sum(Order.grand_total).label('total_spent')
    ).join(Order, Order.customer_id == User.id)\
     .filter(Order.shop_id.in_(shop_ids))\
     .group_by(User.id)\
     .order_by(func.sum(Order.grand_total).desc())\
     .limit(10).all()
    
    # Hourly order distribution
    hourly_results = db.session.query(
        extract('hour', Order.created_at).label('hour'),
        func.count(Order.id).label('count')
    ).filter(Order.shop_id.in_(shop_ids)).group_by('hour').order_by('hour').all()
    
    hourly_data = []
    for result in hourly_results:
        if result.hour is not None:
            hourly_data.append({
                'hour': int(result.hour),
                'count': result.count or 0
            })
    
    # Calculate percentage for status chart
    total_with_status = sum(status_distribution.values())
    
    return render_template('shop/analytics.html',
                         shops=shops,
                         selected_shop=selected_shop,
                         days=days,
                         period=period,
                         total_orders=total_orders,
                         total_revenue=float(total_revenue),
                         total_customers=total_customers,
                         avg_rating=float(avg_rating),
                         status_distribution=status_distribution,
                         popular_items=popular_items,
                         top_customers=top_customers,
                         sales_data=sales_data,
                         labels=labels,
                         orders_data=orders_data,
                         revenue_data=revenue_data,
                         hourly_data=hourly_data,
                         format_currency=format_currency)

@shop_bp.route('/clear-cart/<int:shop_id>', methods=['POST'])
@login_required
def clear_cart(shop_id):
    """Clear all items from cart for a specific shop"""
    if not current_user.is_customer():
        return jsonify({'success': False, 'message': 'Only customers can clear cart'})
    
    try:
        Cart.query.filter_by(
            user_id=current_user.id,
            shop_id=shop_id
        ).delete()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Cart cleared successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@shop_bp.route('/save-for-later', methods=['POST'])
@login_required
def save_for_later():
    """Move item to saved for later"""
    if not current_user.is_customer():
        return jsonify({'success': False, 'message': 'Only customers can save items'})
    
    try:
        cart_id = request.form.get('cart_id')
        cart_item = Cart.query.get_or_404(cart_id)
        
        if cart_item.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'})
        
        # Here you would implement saved for later functionality
        # For now, just remove from cart
        db.session.delete(cart_item)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Item saved for later'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

# ==================== SHOP PROFILE ROUTES ====================

@shop_bp.route('/profile/<int:shop_id>')
@login_required
@shop_owner_required
def shop_profile(shop_id):
    """Shop profile management page"""
    shop = Shop.query.get_or_404(shop_id)
    
    # Check if user owns this shop
    if shop.owner_id != current_user.id:
        flash('Access denied. You do not own this shop.', 'danger')
        return redirect(url_for('shop.shop_dashboard'))
    
    # Generate QR code if requested
    qr_code = None
    if request.args.get('qr') == '1':
        try:
            qr_code = shop.get_qr_code()
        except Exception as e:
            current_app.logger.error(f"QR generation failed: {e}")
    
    return render_template('shop/profile.html', shop=shop, qr_code=qr_code, format_currency=format_currency)

@shop_bp.route('/profile/<int:shop_id>/update-info', methods=['POST'])
@login_required
@shop_owner_required
def update_shop_info(shop_id):
    """Update shop information"""
    shop = Shop.query.get_or_404(shop_id)
    
    if shop.owner_id != current_user.id:
        flash('Access denied. You do not own this shop.', 'danger')
        return redirect(url_for('shop.shop_dashboard'))
    
    try:
        shop.shop_name = request.form.get('shop_name')
        shop.category = request.form.get('category')
        shop.address = request.form.get('address')
        shop.phone = request.form.get('phone')
        shop.email = request.form.get('email')
        shop.description = request.form.get('description')
        shop.is_open = 'is_open' in request.form
        
        # Handle logo upload
        if 'logo' in request.files and request.files['logo'].filename:
            logo_file = request.files['logo']
            # Delete old logo
            if shop.logo:
                old_logo_path = os.path.join(current_app.root_path, 'static/uploads/logos', shop.logo)
                if os.path.exists(old_logo_path):
                    os.remove(old_logo_path)
            filename = save_shop_logo(logo_file, shop.id)
            if filename:
                shop.logo = filename
        
        db.session.commit()
        flash('Shop information updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating shop information: {str(e)}', 'danger')
    
    return redirect(url_for('shop.shop_profile', shop_id=shop.id))

@shop_bp.route('/profile/<int:shop_id>/update-hours', methods=['POST'])
@login_required
@shop_owner_required
def update_shop_hours(shop_id):
    """Update shop business hours"""
    shop = Shop.query.get_or_404(shop_id)
    
    if shop.owner_id != current_user.id:
        flash('Access denied. You do not own this shop.', 'danger')
        return redirect(url_for('shop.shop_dashboard'))
    
    try:
        shop.opening_hours = request.form.get('opening_hours')
        shop.closing_hours = request.form.get('closing_hours')
        db.session.commit()
        flash('Business hours updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating business hours: {str(e)}', 'danger')
    
    return redirect(url_for('shop.shop_profile', shop_id=shop.id))

@shop_bp.route('/profile/<int:shop_id>/update-delivery', methods=['POST'])
@login_required
@shop_owner_required
def update_shop_delivery(shop_id):
    """Update shop delivery settings"""
    shop = Shop.query.get_or_404(shop_id)
    
    if shop.owner_id != current_user.id:
        flash('Access denied. You do not own this shop.', 'danger')
        return redirect(url_for('shop.shop_dashboard'))
    
    try:
        shop.delivery_fee = float(request.form.get('delivery_fee'))
        shop.min_order = float(request.form.get('min_order'))
        shop.preparation_time = int(request.form.get('preparation_time'))
        db.session.commit()
        flash('Delivery settings updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating delivery settings: {str(e)}', 'danger')
    
    return redirect(url_for('shop.shop_profile', shop_id=shop.id))

@shop_bp.route('/profile/<int:shop_id>/remove-logo', methods=['POST'])
@login_required
@shop_owner_required
def remove_logo(shop_id):
    """Remove shop logo"""
    shop = Shop.query.get_or_404(shop_id)
    
    if shop.owner_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    try:
        if shop.logo:
            logo_path = os.path.join(current_app.root_path, 'static/uploads/logos', shop.logo)
            if os.path.exists(logo_path):
                os.remove(logo_path)
            shop.logo = None
            db.session.commit()
            return jsonify({'success': True, 'message': 'Logo removed successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    
    return jsonify({'success': False, 'message': 'No logo found'})

@shop_bp.route('/profile/<int:shop_id>/generate-qr')
@login_required
@shop_owner_required
def generate_qr(shop_id):
    """Generate QR code for shop"""
    shop = Shop.query.get_or_404(shop_id)
    
    if shop.owner_id != current_user.id:
        flash('Access denied. You do not own this shop.', 'danger')
        return redirect(url_for('shop.shop_dashboard'))
    
    try:
        qr_code = shop.get_qr_code()
        if qr_code:
            return render_template('shop/profile.html', shop=shop, qr_code=qr_code, format_currency=format_currency)
        else:
            flash('Failed to generate QR code. Please try again.', 'danger')
    except Exception as e:
        current_app.logger.error(f"QR generation error: {e}")
        flash('Error generating QR code.', 'danger')
    
    return redirect(url_for('shop.shop_profile', shop_id=shop.id))

@shop_bp.route('/update-notification-settings', methods=['POST'])
@login_required
def update_notification_settings():
    """Update notification settings for shop owner"""
    try:
        email_notifications = request.form.get('email_notifications') == 'true'
        sms_notifications = request.form.get('sms_notifications') == 'true'
        
        # Here you would save these settings to the database
        # For now, just return success
        
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@shop_bp.route('/analytics/export/<format>')
@login_required
@shop_owner_required
def export_analytics(format):
    """Export analytics report as PDF or CSV"""
    from app.models import Order, Item, Cart, User
    from sqlalchemy import func, extract
    from datetime import datetime, timedelta
    import csv
    from io import StringIO, BytesIO
    from flask import Response, send_file
    import tempfile
    import os
    
    # Get user's shops
    shops = current_user.shops.all()
    
    if not shops:
        flash('You need to register a shop first.', 'warning')
        return redirect(url_for('shop.register_shop'))
    
    # Get selected shop or first shop
    selected_shop_id = request.args.get('shop_id', type=int)
    days = request.args.get('days', 30, type=int)
    period = request.args.get('period', 'daily')
    
    if selected_shop_id:
        selected_shop = Shop.query.get(selected_shop_id)
        if selected_shop and selected_shop.owner_id == current_user.id:
            shop_ids = [selected_shop.id]
        else:
            shop_ids = [shop.id for shop in shops]
            selected_shop = shops[0]
    else:
        shop_ids = [shop.id for shop in shops]
        selected_shop = shops[0]
    
    start_date = datetime.utcnow().date() - timedelta(days=days)
    
    # Get data
    total_orders = Order.query.filter(Order.shop_id.in_(shop_ids)).count()
    total_revenue = db.session.query(func.sum(Order.grand_total)).filter(
        Order.shop_id.in_(shop_ids),
        Order.order_status == 'delivered'
    ).scalar() or 0
    total_customers = Order.query.filter(Order.shop_id.in_(shop_ids)).distinct(Order.customer_id).count()
    
    # Sales data
    sales_data = []
    if period == 'daily':
        daily_results = db.session.query(
            func.date(Order.created_at).label('date'),
            func.count(Order.id).label('orders'),
            func.sum(Order.grand_total).label('revenue')
        ).filter(
            Order.shop_id.in_(shop_ids),
            func.date(Order.created_at) >= start_date
        ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()
        
        for result in daily_results:
            # Handle both date objects and strings
            if result.date:
                if hasattr(result.date, 'strftime'):
                    date_str = result.date.strftime('%Y-%m-%d')
                else:
                    date_str = str(result.date)
            else:
                date_str = 'Unknown'
            
            sales_data.append({
                'date': date_str,
                'orders': result.orders or 0,
                'revenue': float(result.revenue or 0)
            })
    else:
        monthly_results = db.session.query(
            extract('year', Order.created_at).label('year'),
            extract('month', Order.created_at).label('month'),
            func.count(Order.id).label('orders'),
            func.sum(Order.grand_total).label('revenue')
        ).filter(
            Order.shop_id.in_(shop_ids),
            Order.created_at >= start_date
        ).group_by('year', 'month').order_by('year', 'month').all()
        
        for result in monthly_results:
            if result.year and result.month:
                try:
                    # Convert to integers
                    year = int(result.year)
                    month = int(result.month)
                    month_name = datetime(year, month, 1).strftime('%B %Y')
                except:
                    month_name = f"{result.year}-{result.month}"
                
                sales_data.append({
                    'date': month_name,
                    'orders': result.orders or 0,
                    'revenue': float(result.revenue or 0)
                })
    
    # Popular items
    popular_items = db.session.query(
        Item.name,
        func.sum(Cart.quantity).label('total_sold'),
        func.sum(Cart.quantity * Item.price).label('total_revenue')
    ).join(Cart, Cart.item_id == Item.id)\
     .filter(Item.shop_id.in_(shop_ids))\
     .group_by(Item.id)\
     .order_by(func.sum(Cart.quantity).desc())\
     .limit(10).all()
    
    # Prepare data for export
    report_data = {
        'shop_name': selected_shop.shop_name,
        'generated_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        'period': f'Last {days} days',
        'total_orders': total_orders,
        'total_revenue': float(total_revenue),
        'total_customers': total_customers,
        'sales_data': sales_data,
        'popular_items': popular_items
    }
    
    if format == 'csv':
        return export_csv(report_data)
    elif format == 'pdf':
        return export_pdf(report_data)
    else:
        flash('Invalid export format', 'danger')
        return redirect(url_for('shop.shop_analytics'))

def export_csv(report_data):
    """Export report as CSV"""
    import csv
    from io import StringIO
    from flask import Response
    from datetime import datetime
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Shop Info
    writer.writerow(['Jozini Move - Shop Analytics Report'])
    writer.writerow([f'Shop: {report_data["shop_name"]}'])
    writer.writerow([f'Generated: {report_data["generated_date"]}'])
    writer.writerow([f'Period: {report_data["period"]}'])
    writer.writerow([])
    
    # Summary
    writer.writerow(['SUMMARY STATISTICS'])
    writer.writerow(['Total Orders', report_data['total_orders']])
    writer.writerow(['Total Revenue', f'R {report_data["total_revenue"]:,.2f}'])
    writer.writerow(['Total Customers', report_data['total_customers']])
    writer.writerow([])
    
    # Sales Data
    writer.writerow(['SALES DATA'])
    writer.writerow(['Date', 'Orders', 'Revenue'])
    for data in report_data['sales_data']:
        writer.writerow([data['date'], data['orders'], f'R {data["revenue"]:,.2f}'])
    writer.writerow([])
    
    # Popular Items
    if report_data['popular_items']:
        writer.writerow(['TOP SELLING ITEMS'])
        writer.writerow(['Item Name', 'Quantity Sold', 'Revenue'])
        for item in report_data['popular_items']:
            writer.writerow([item.name, item.total_sold, f'R {item.total_revenue:,.2f}'])
    
    # Create response
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename=analytics_report_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'
    return response

def export_pdf(report_data):
    """Export report as PDF"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from flask import send_file
    import tempfile
    import os
    from datetime import datetime
    
    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    temp_file.close()
    
    # Create PDF document
    doc = SimpleDocTemplate(temp_file.name, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#0d6efd'),
        spaceAfter=30,
        alignment=1  # Center
    )
    story.append(Paragraph("Jozini Move - Analytics Report", title_style))
    story.append(Spacer(1, 0.2 * inch))
    
    # Shop Info
    info_style = ParagraphStyle(
        'InfoStyle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=6
    )
    story.append(Paragraph(f"<b>Shop:</b> {report_data['shop_name']}", info_style))
    story.append(Paragraph(f"<b>Generated:</b> {report_data['generated_date']}", info_style))
    story.append(Paragraph(f"<b>Period:</b> {report_data['period']}", info_style))
    story.append(Spacer(1, 0.3 * inch))
    
    # Summary Statistics
    story.append(Paragraph("Summary Statistics", styles['Heading2']))
    story.append(Spacer(1, 0.1 * inch))
    
    summary_data = [
        ['Metric', 'Value'],
        ['Total Orders', str(report_data['total_orders'])],
        ['Total Revenue', f'R {report_data["total_revenue"]:,.2f}'],
        ['Total Customers', str(report_data['total_customers'])]
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5 * inch, 2.5 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#0d6efd')),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (1, 0), 12),
        ('BACKGROUND', (0, 1), (1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (1, -1), colors.black),
        ('ALIGN', (0, 0), (1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (1, -1), 10),
        ('TOPPADDING', (0, 1), (1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (1, -1), 6),
        ('GRID', (0, 0), (1, -1), 1, colors.grey)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.3 * inch))
    
    # Sales Data
    story.append(Paragraph("Sales Data", styles['Heading2']))
    story.append(Spacer(1, 0.1 * inch))
    
    sales_table_data = [['Date', 'Orders', 'Revenue']]
    for data in report_data['sales_data']:
        sales_table_data.append([
            data['date'],
            str(data['orders']),
            f'R {data["revenue"]:,.2f}'
        ])
    
    sales_table = Table(sales_table_data, colWidths=[2 * inch, 1.5 * inch, 2 * inch])
    sales_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (2, 0), colors.HexColor('#10b981')),
        ('TEXTCOLOR', (0, 0), (2, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (2, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (2, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (2, 0), 11),
        ('BOTTOMPADDING', (0, 0), (2, 0), 10),
        ('BACKGROUND', (0, 1), (2, -1), colors.white),
        ('ALIGN', (0, 0), (2, -1), 'CENTER'),
        ('FONTSIZE', (0, 1), (2, -1), 9),
        ('TOPPADDING', (0, 1), (2, -1), 6),
        ('BOTTOMPADDING', (0, 1), (2, -1), 6),
        ('GRID', (0, 0), (2, -1), 1, colors.grey),
        ('VALIGN', (0, 0), (2, -1), 'MIDDLE')
    ]))
    story.append(sales_table)
    story.append(Spacer(1, 0.3 * inch))
    
    # Top Selling Items
    if report_data['popular_items']:
        story.append(Paragraph("Top Selling Items", styles['Heading2']))
        story.append(Spacer(1, 0.1 * inch))
        
        items_table_data = [['Item Name', 'Quantity Sold', 'Revenue']]
        for item in report_data['popular_items']:
            items_table_data.append([
                item.name,
                str(item.total_sold),
                f'R {item.total_revenue:,.2f}'
            ])
        
        items_table = Table(items_table_data, colWidths=[2.5 * inch, 1.5 * inch, 2 * inch])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (2, 0), colors.HexColor('#0d6efd')),
            ('TEXTCOLOR', (0, 0), (2, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (2, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (2, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (2, 0), 11),
            ('BOTTOMPADDING', (0, 0), (2, 0), 10),
            ('BACKGROUND', (0, 1), (2, -1), colors.white),
            ('ALIGN', (0, 0), (2, -1), 'CENTER'),
            ('FONTSIZE', (0, 1), (2, -1), 9),
            ('TOPPADDING', (0, 1), (2, -1), 6),
            ('BOTTOMPADDING', (0, 1), (2, -1), 6),
            ('GRID', (0, 0), (2, -1), 1, colors.grey),
            ('VALIGN', (0, 0), (2, -1), 'MIDDLE')
        ]))
        story.append(items_table)
    
    # Build PDF
    doc.build(story)
    
    # Send file
    return send_file(temp_file.name, as_attachment=True, download_name=f'analytics_report_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf', mimetype='application/pdf')
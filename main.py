from flask import Blueprint, render_template, request, jsonify, current_app, abort, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db, cache
from datetime import datetime
from app.models import Shop, Item, Order, Settings, User, Notification
from app.utils.helpers import format_currency, get_delivery_zones
from sqlalchemy import func, or_

main_bp = Blueprint('main', __name__)

# Add this function at the top of main.py after imports
def get_category_icon(category):
    """Return Font Awesome icon for category"""
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
    return icons.get(category.lower(), 'store')

# Then in the index route, pass it to the template
@main_bp.route('/')
@cache.cached(timeout=300)
def index():
    """Home page"""
    featured_shops = Shop.query.filter_by(status='active', is_open=True)\
                               .order_by(Shop.rating.desc())\
                               .limit(8).all()
    
    popular_items = Item.query.filter_by(available=True, is_featured=True)\
                              .order_by(Item.created_at.desc())\
                              .limit(12).all()
    
    categories = db.session.query(Shop.category, func.count(Shop.id))\
                          .filter_by(status='active')\
                          .group_by(Shop.category)\
                          .all()
    
    # Get stats
    total_shops = Shop.query.filter_by(status='active').count()
    total_drivers = User.query.filter_by(user_type='driver', is_active=True).count()
    total_deliveries = Order.query.filter_by(order_status='delivered').count()
    
    return render_template('index.html', 
                         featured_shops=featured_shops,
                         popular_items=popular_items,
                         categories=categories,
                         total_shops=total_shops,
                         total_drivers=total_drivers,
                         total_deliveries=total_deliveries,
                         format_currency=format_currency,
                         get_category_icon=get_category_icon)  # Add this line
@main_bp.route('/about')
def about():
    """About page"""
    return render_template('about.html')

@main_bp.route('/contact')
def contact():
    """Contact page"""
    return render_template('contact.html')

@main_bp.route('/search')
def search():
    """Global search"""
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '')
    
    shops = []
    items = []
    
    if query:
        # Search shops
        shop_query = Shop.query.filter(Shop.status == 'active')
        if query:
            shop_query = shop_query.filter(
                or_(
                    Shop.shop_name.ilike(f'%{query}%'),
                    Shop.description.ilike(f'%{query}%')
                )
            )
        if category and category != 'all':
            shop_query = shop_query.filter_by(category=category)
        
        shops = shop_query.limit(20).all()
        
        # Search items
        items = Item.query.filter(
            Item.available == True,
            or_(
                Item.name.ilike(f'%{query}%'),
                Item.description.ilike(f'%{query}%')
            )
        ).limit(20).all()
    
    return render_template('search.html', 
                         query=query, 
                         shops=shops, 
                         items=items,
                         category=category,
                         format_currency=format_currency)

@main_bp.route('/api/shops')
@cache.cached(timeout=600)
def api_shops():
    """API: Get all shops"""
    shops = Shop.query.filter_by(status='active').all()
    return jsonify([shop.to_dict() for shop in shops])

@main_bp.route('/api/shops/<int:shop_id>')
@cache.cached(timeout=300)
def api_shop_detail(shop_id):
    """API: Get shop details"""
    shop = Shop.query.get_or_404(shop_id)
    items = Item.query.filter_by(shop_id=shop_id, available=True).all()
    
    return jsonify({
        'shop': shop.to_dict(),
        'items': [item.to_dict() for item in items]
    })

@main_bp.route('/api/order-status/<order_number>')
def api_order_status(order_number):
    """API: Get order status"""
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    return jsonify(order.to_dict())

@main_bp.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        db_status = 'healthy'
    except Exception as e:
        db_status = 'unhealthy'
        current_app.logger.error(f'Database health check failed: {e}')
    
    return jsonify({
        'status': 'healthy' if db_status == 'healthy' else 'unhealthy',
        'app': current_app.config['APP_NAME'],
        'version': current_app.config['APP_VERSION'],
        'database': db_status,
        'environment': current_app.config.get('ENV', 'production')
    }), 200 if db_status == 'healthy' else 500

@main_bp.route('/offline')
def offline():
    """Offline page for PWA"""
    return render_template('offline.html')

@main_bp.route('/robots.txt')
def robots():
    """Robots.txt for SEO"""
    content = """User-agent: *
Allow: /
Disallow: /admin/
Disallow: /auth/login/
Disallow: /auth/register/
Sitemap: {}/sitemap.xml
""".format(current_app.config['APP_URL'])
    return content, 200, {'Content-Type': 'text/plain'}

@main_bp.route('/sitemap.xml')
@cache.cached(timeout=86400)
def sitemap():
    """Generate sitemap for SEO"""
    from datetime import date
    pages = []
    
    # Static pages
    static_pages = ['/', '/about', '/contact', '/search']
    for page in static_pages:
        pages.append({
            'loc': f"{current_app.config['APP_URL']}{page}",
            'lastmod': date.today().isoformat(),
            'priority': '1.0'
        })
    
    # Shop pages
    shops = Shop.query.filter_by(status='active').all()
    for shop in shops:
        pages.append({
            'loc': f"{current_app.config['APP_URL']}/shop/{shop.id}",
            'lastmod': shop.updated_at.date().isoformat() if shop.updated_at else date.today().isoformat(),
            'priority': '0.8'
        })
    
    # Generate XML
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for page in pages:
        xml += '  <url>\n'
        xml += f'    <loc>{page["loc"]}</loc>\n'
        xml += f'    <lastmod>{page["lastmod"]}</lastmod>\n'
        xml += f'    <priority>{page["priority"]}</priority>\n'
        xml += '  </url>\n'
    xml += '</urlset>'
    
    return xml, 200, {'Content-Type': 'application/xml'}


@main_bp.route('/help-center')
def help_center():
    """Help Center page"""
    return render_template('help_center.html')

@main_bp.route('/terms')
def terms():
    """Terms & Conditions page"""
    return render_template('terms.html')

@main_bp.route('/privacy')
def privacy():
    """Privacy Policy page"""
    return render_template('privacy.html')

@main_bp.route('/refund')
def refund():
    """Refund Policy page"""
    return render_template('refund.html')

@main_bp.route('/refund-request')
@login_required
def refund_request():
    """Refund request page - step 1: select order"""
    from app.models import RefundRequest
    from datetime import timedelta
    
    # Get eligible orders (delivered in last 30 days, not already refunded)
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    eligible_orders = Order.query.filter(
        Order.customer_id == current_user.id,
        Order.order_status == 'delivered',
        Order.created_at >= cutoff_date
    ).all()
    
    # Filter out orders that already have a refund request
    existing_refunds = RefundRequest.query.filter_by(user_id=current_user.id).all()
    refunded_order_ids = [r.order_id for r in existing_refunds]
    eligible_orders = [o for o in eligible_orders if o.id not in refunded_order_ids]
    
    return render_template('main/refund_request.html', step=1, eligible_orders=eligible_orders, format_currency=format_currency)

@main_bp.route('/refund-request/order/<int:order_id>')
@login_required
def refund_request_step2(order_id):
    """Refund request page - step 2: provide details"""
    order = Order.query.get_or_404(order_id)
    
    # Verify ownership
    if order.customer_id != current_user.id:
        flash('You do not have permission to request refund for this order.', 'danger')
        return redirect(url_for('main.refund_request'))
    
    return render_template('main/refund_request.html', step=2, order=order, format_currency=format_currency)

@main_bp.route('/refund-request/submit', methods=['POST'])
@login_required
def refund_request_submit():
    """Submit refund request"""
    from app.models import RefundRequest
    import os
    from werkzeug.utils import secure_filename
    
    order_id = request.form.get('order_id')
    reason = request.form.get('reason')
    description = request.form.get('description')
    refund_method = request.form.get('refund_method', 'original')
    
    order = Order.query.get_or_404(order_id)
    
    # Verify ownership
    if order.customer_id != current_user.id:
        flash('You do not have permission to request refund for this order.', 'danger')
        return redirect(url_for('main.refund_request'))
    
    # Handle file uploads
    evidence_files = []
    if 'evidence' in request.files:
        files = request.files.getlist('evidence')
        for file in files:
            if file and file.filename:
                filename = secure_filename(f"{datetime.utcnow().timestamp()}_{file.filename}")
                upload_path = os.path.join(current_app.root_path, 'static/uploads/refunds')
                os.makedirs(upload_path, exist_ok=True)
                file.save(os.path.join(upload_path, filename))
                evidence_files.append(filename)
    
    # Create refund request
    refund_request = RefundRequest(
        order_id=order.id,
        user_id=current_user.id,
        reason=reason,
        description=description,
        amount=order.grand_total,
        refund_method=refund_method,
        evidence=','.join(evidence_files) if evidence_files else None,
        status='pending'
    )
    
    db.session.add(refund_request)
    db.session.commit()
    
    # Notify admin
    admin = User.query.filter_by(user_type='admin').first()
    if admin:
        notification = Notification(
            user_id=admin.id,
            title='New Refund Request',
            message=f'Refund request #{refund_request.id} from {current_user.name} for order #{order.order_number}',
            type='info',
            link=url_for('admin.refund_requests')
        )
        db.session.add(notification)
        db.session.commit()
    
    flash('Your refund request has been submitted successfully!', 'success')
    return render_template('main/refund_request.html', step=3, refund_request=refund_request, format_currency=format_currency)

@main_bp.route('/refund-tracking/<int:request_id>')
@login_required
def refund_tracking(request_id):
    """Track refund request status"""
    from app.models import RefundRequest
    
    refund_request = RefundRequest.query.get_or_404(request_id)
    
    # Verify ownership or admin access
    if refund_request.user_id != current_user.id and not current_user.is_admin():
        flash('You do not have permission to view this refund request.', 'danger')
        return redirect(url_for('main.refund_request'))
    
    return render_template('main/refund_tracking.html', refund_request=refund_request, format_currency=format_currency)

@main_bp.route('/my-refunds')
@login_required
def my_refunds():
    """View all user refund requests"""
    from app.models import RefundRequest
    
    refund_requests = RefundRequest.query.filter_by(user_id=current_user.id).order_by(RefundRequest.created_at.desc()).all()
    
    return render_template('main/refund_request.html', step=1, refund_requests=refund_requests, format_currency=format_currency)
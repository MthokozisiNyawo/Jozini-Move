from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_user, logout_user, current_user, login_required
from app import db, limiter
from app.models import User, Notification
from app.forms import LoginForm, RegisterForm, ForgotPasswordForm, ResetPasswordForm, ProfileForm, ChangePasswordForm
from app.utils.helpers import send_verification_sms, send_verification_email, send_password_reset_email
from datetime import datetime, timedelta
import secrets

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(phone=form.phone.data).first()
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'danger')
                return render_template('auth/login.html', form=form)
            
            if not user.is_verified:
                flash('Please verify your account first. Check your email/SMS for verification link.', 'warning')
                return render_template('auth/login.html', form=form)
            
            login_user(user, remember=form.remember.data)
            user.last_login = datetime.utcnow()
            user.last_ip = request.remote_addr
            db.session.commit()
            
            flash(f'Welcome back, {user.name}!', 'success')
            
            # Redirect based on user type
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            elif user.is_customer():
                return redirect(url_for('shop.browse'))
            elif user.is_driver():
                return redirect(url_for('driver.dashboard'))
            elif user.is_shop_owner():
                return redirect(url_for('shop.shop_dashboard'))
            elif user.is_admin():
                return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid phone number or password', 'danger')
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    """Registration page"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = RegisterForm()
    
    if form.validate_on_submit():
        # Create new user
        user = User(
            name=form.name.data,
            phone=form.phone.data,
            email=form.email.data,
            address=form.address.data,
            user_type=form.user_type.data,
            vehicle=form.vehicle.data if form.user_type.data == 'driver' else None,
            shop_category=form.shop_category.data if form.user_type.data == 'shop_owner' else None
        )
        user.set_password(form.password.data)
        user.generate_verification_token()
        
        try:
            db.session.add(user)
            db.session.commit()
            
            # Send verification
            if current_app.config['SMS_ENABLED']:
                send_verification_sms(user.phone, user.verification_token)
            if current_app.config['EMAIL_ENABLED']:
                send_verification_email(user.email, user.verification_token)
            
            flash('Registration successful! Please check your phone/email for verification.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Registration failed: {e}')
            flash('Registration failed. Please try again.', 'danger')
    
    return render_template('auth/register.html', form=form)

@auth_bp.route('/verify/<token>')
def verify_email(token):
    """Verify user email/phone"""
    user = User.query.filter_by(verification_token=token).first()
    if user and not user.is_verified:
        user.is_verified = True
        user.verification_token = None
        db.session.commit()
        
        # Create welcome notification
        notification = Notification(
            user_id=user.id,
            title='Welcome to Jozini Move!',
            message=f'Welcome {user.name}! Your account has been verified. Start ordering or delivering today!',
            type='success'
        )
        db.session.add(notification)
        db.session.commit()
        
        flash('Your account has been verified! You can now log in.', 'success')
    else:
        flash('Invalid or expired verification token.', 'danger')
    
    return redirect(url_for('auth.login'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def forgot_password():
    """Forgot password page"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = ForgotPasswordForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            token = user.generate_reset_token()
            if current_app.config['EMAIL_ENABLED']:
                send_password_reset_email(user.email, token)
            flash('Password reset instructions have been sent to your email.', 'info')
        else:
            flash('No account found with that email address.', 'danger')
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html', form=form)

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password page"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    user = User.query.filter_by(reset_password_token=token).first()
    if not user or user.reset_password_expires < datetime.utcnow():
        flash('Invalid or expired reset token.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    
    form = ResetPasswordForm()
    
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.reset_password_token = None
        user.reset_password_expires = None
        db.session.commit()
        
        flash('Your password has been reset! You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', form=form, token=token)

@auth_bp.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('main.index'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile page"""
    form = ProfileForm(obj=current_user)
    
    if form.validate_on_submit():
        current_user.name = form.name.data
        current_user.email = form.email.data
        current_user.address = form.address.data
        
        if form.profile_image.data:
            # Handle image upload
            from app.utils.helpers import save_profile_image
            filename = save_profile_image(form.profile_image.data, current_user.id)
            if filename:
                current_user.profile_image = filename
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/profile.html', form=form, user=current_user)

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password page"""
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        if current_user.check_password(form.current_password.data):
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('auth.profile'))
        else:
            flash('Current password is incorrect.', 'danger')
    
    return render_template('auth/change_password.html', form=form)

@auth_bp.route('/notifications')
@login_required
def notifications():
    """User notifications page"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', 'all')
    
    query = Notification.query.filter_by(user_id=current_user.id)
    
    if status == 'unread':
        query = query.filter_by(is_read=False)
    elif status == 'read':
        query = query.filter_by(is_read=True)
    
    notifications = query.order_by(Notification.created_at.desc()).paginate(page=page, per_page=20)
    
    # Get counts
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    total_count = Notification.query.filter_by(user_id=current_user.id).count()
    
    return render_template('auth/notifications.html', 
                         notifications=notifications,
                         unread_count=unread_count,
                         total_count=total_count,
                         current_status=status)

@auth_bp.route('/notification/<int:notification_id>')
@login_required
def view_notification(notification_id):
    """View single notification and mark as read"""
    notification = Notification.query.get_or_404(notification_id)
    
    # Check if notification belongs to current user
    if notification.user_id != current_user.id:
        flash('You do not have permission to view this notification.', 'danger')
        return redirect(url_for('auth.notifications'))
    
    # Mark as read if not already
    if not notification.is_read:
        notification.is_read = True
        db.session.commit()
    
    return render_template('auth/notification_detail.html', notification=notification)

@auth_bp.route('/notifications/mark-read/<int:notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a single notification as read"""
    try:
        notification = Notification.query.get_or_404(notification_id)
        if notification.user_id == current_user.id:
            notification.is_read = True
            db.session.commit()
            return jsonify({'success': True, 'message': 'Notification marked as read'})
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@auth_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read"""
    try:
        Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
        db.session.commit()
        return jsonify({'success': True, 'message': 'All notifications marked as read'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@auth_bp.route('/notifications/delete/<int:notification_id>', methods=['POST'])
@login_required
def delete_notification(notification_id):
    """Delete a single notification"""
    try:
        notification = Notification.query.get_or_404(notification_id)
        if notification.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        db.session.delete(notification)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Notification deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@auth_bp.route('/notifications/delete-all-read', methods=['POST'])
@login_required
def delete_all_read_notifications():
    """Delete all read notifications"""
    try:
        Notification.query.filter_by(user_id=current_user.id, is_read=True).delete()
        db.session.commit()
        return jsonify({'success': True, 'message': 'All read notifications deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@auth_bp.route('/api/notifications/unread-count')
@login_required
def unread_notifications_count():
    """Get unread notifications count for badge"""
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'unread_count': count})
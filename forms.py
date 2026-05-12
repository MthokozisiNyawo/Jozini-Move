from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, TextAreaField, SelectField, IntegerField, DecimalField, BooleanField, SubmitField, FloatField, HiddenField, TimeField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, NumberRange, Optional, Regexp
from app.models import User

# Try to import email_validator for better email validation
try:
    from email_validator import validate_email, EmailNotValidError
    HAS_EMAIL_VALIDATOR = True
except ImportError:
    HAS_EMAIL_VALIDATOR = False
    print("Warning: email-validator not installed. Using basic email validation.")

# Custom email validator that works with or without email_validator package
class ExtendedEmail(object):
    """
    Extended email validator that uses email-validator package if available,
    otherwise falls back to basic WTForms Email validator.
    """
    def __init__(self, message=None, granular_message=False, check_deliverability=False):
        self.message = message
        self.granular_message = granular_message
        self.check_deliverability = check_deliverability
        
    def __call__(self, form, field):
        if HAS_EMAIL_VALIDATOR and field.data:
            # Use the full email_validator package
            try:
                validate_email(field.data, check_deliverability=self.check_deliverability)
            except EmailNotValidError as e:
                message = self.message or str(e)
                raise ValidationError(message)
        else:
            # Fall back to basic validation
            email_validator = Email(message=self.message)
            email_validator(form, field)

class LoginForm(FlaskForm):
    phone = StringField('Phone Number', validators=[
        DataRequired(message="Phone number is required"),
        Regexp(r'^[0-9]{10}$', message="Please enter a valid 10-digit phone number")
    ])
    password = PasswordField('Password', validators=[DataRequired(message="Password is required")])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class RegisterForm(FlaskForm):
    name = StringField('Full Name', validators=[
        DataRequired(message="Full name is required"),
        Length(min=2, max=100, message="Name must be between 2 and 100 characters")
    ])
    phone = StringField('Phone Number', validators=[
        DataRequired(message="Phone number is required"),
        Regexp(r'^[0-9]{10}$', message="Please enter a valid 10-digit phone number")
    ])
    email = StringField('Email Address', validators=[
        DataRequired(message="Email address is required"),
        ExtendedEmail(message="Please enter a valid email address")
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required"),
        Length(min=6, message="Password must be at least 6 characters long")
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message="Please confirm your password"),
        EqualTo('password', message="Passwords must match")
    ])
    address = TextAreaField('Address', validators=[
        DataRequired(message="Address is required"),
        Length(min=5, max=500, message="Address must be between 5 and 500 characters")
    ])
    user_type = SelectField('Account Type', 
                           choices=[
                               ('customer', 'Customer - Order food and items'), 
                               ('driver', 'Delivery Driver - Earn money delivering'),
                               ('shop_owner', 'Shop Owner - Sell your products')
                           ],
                           validators=[DataRequired(message="Please select account type")])
    vehicle = StringField('Vehicle Type', validators=[Optional(), Length(max=50)])
    shop_category = StringField('Shop Category', validators=[Optional(), Length(max=50)])
    submit = SubmitField('Register')
    
    def validate_phone(self, phone):
        user = User.query.filter_by(phone=phone.data).first()
        if user:
            raise ValidationError('Phone number already registered. Please use a different number or login.')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email address already registered. Please use a different email or login.')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email Address', validators=[
        DataRequired(message="Email address is required"),
        ExtendedEmail(message="Please enter a valid email address")
    ])
    submit = SubmitField('Reset Password')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[
        DataRequired(message="Password is required"),
        Length(min=6, message="Password must be at least 6 characters long")
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message="Please confirm your password"),
        EqualTo('password', message="Passwords must match")
    ])
    submit = SubmitField('Reset Password')

class ShopRegistrationForm(FlaskForm):
    shop_name = StringField('Shop Name', validators=[
        DataRequired(message="Shop name is required"),
        Length(min=2, max=100, message="Shop name must be between 2 and 100 characters")
    ])
    category = SelectField('Category', 
                          choices=[
                              ('restaurant', 'Restaurant/Food'), 
                              ('butchery', 'Butchery'), 
                              ('grocery', 'Grocery Store'),
                              ('pharmacy', 'Pharmacy'),
                              ('hardware', 'Hardware'),
                              ('clothing', 'Clothing'),
                              ('electronics', 'Electronics'),
                              ('other', 'Other')
                          ],
                          validators=[DataRequired(message="Please select a category")])
    address = TextAreaField('Shop Address', validators=[
        DataRequired(message="Address is required"),
        Length(min=5, max=500, message="Address must be between 5 and 500 characters")
    ])
    phone = StringField('Shop Phone', validators=[
        DataRequired(message="Phone number is required"),
        Regexp(r'^[0-9]{10}$', message="Please enter a valid 10-digit phone number")
    ])
    email = StringField('Shop Email', validators=[
        Optional(),
        ExtendedEmail(message="Please enter a valid email address")
    ])
    description = TextAreaField('Description', validators=[Optional(), Length(max=1000)])
    opening_hours = StringField('Opening Hours', validators=[Optional(), Length(max=100)])
    closing_hours = StringField('Closing Hours', validators=[Optional(), Length(max=100)])
    delivery_fee = DecimalField('Delivery Fee', validators=[Optional(), NumberRange(min=0)], default=20.00)
    min_order = DecimalField('Minimum Order Amount', validators=[Optional(), NumberRange(min=0)], default=0)
    logo = FileField('Shop Logo', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])
    submit = SubmitField('Register Shop')

class ItemForm(FlaskForm):
    name = StringField('Item Name', validators=[
        DataRequired(message="Item name is required"),
        Length(min=2, max=100)
    ])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    price = DecimalField('Price (R)', validators=[
        DataRequired(message="Price is required"),
        NumberRange(min=0.01, message="Price must be greater than 0")
    ])
    category = StringField('Category', validators=[Optional(), Length(max=50)])
    available = BooleanField('Available', default=True)
    is_featured = BooleanField('Featured Item', default=False)
    preparation_time = IntegerField('Preparation Time (minutes)', validators=[
        Optional(),
        NumberRange(min=1, max=120)
    ], default=15)
    stock_quantity = IntegerField('Stock Quantity', validators=[
        Optional(),
        NumberRange(min=-1)
    ], default=-1)
    image = FileField('Item Image', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])
    submit = SubmitField('Save Item')

class CheckoutForm(FlaskForm):
    delivery_address = TextAreaField('Delivery Address', validators=[
        DataRequired(message="Delivery address is required"),
        Length(min=5, max=500)
    ])
    delivery_zone = SelectField('Delivery Zone', validators=[DataRequired()], choices=[])
    payment_method = SelectField('Payment Method', 
                                choices=[
                                    ('cash', 'Cash on Delivery'),
                                    ('card', 'Credit/Debit Card'),
                                    ('mobile_money', 'Mobile Money')
                                ],
                                validators=[DataRequired()])
    order_notes = TextAreaField('Special Instructions', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Place Order')

class OrderStatusForm(FlaskForm):
    status = SelectField('Update Status', choices=[
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready for Pickup'),
        ('accepted', 'Accepted by Driver'),
        ('picked_up', 'Picked Up'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    ], validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Update Status')

class ReviewForm(FlaskForm):
    rating = IntegerField('Rating', validators=[
        DataRequired(message="Please select a rating"),
        NumberRange(min=1, max=5, message="Rating must be between 1 and 5")
    ])
    review = TextAreaField('Review', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Submit Review')
    
class ProfileForm(FlaskForm):
    name = StringField('Full Name', validators=[
        DataRequired(),
        Length(min=2, max=100)
    ])
    email = StringField('Email Address', validators=[
        DataRequired(),
        ExtendedEmail()
    ])
    address = TextAreaField('Address', validators=[
        DataRequired(),
        Length(min=5, max=500)
    ])
    profile_image = FileField('Profile Picture', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])
    submit = SubmitField('Update Profile')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[
        DataRequired(message="Current password is required")
    ])
    new_password = PasswordField('New Password', validators=[
        DataRequired(message="New password is required"),
        Length(min=6, message="Password must be at least 6 characters")
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message="Please confirm your password"),
        EqualTo('new_password', message="Passwords must match")
    ])
    submit = SubmitField('Change Password')

class DeliveryZoneForm(FlaskForm):
    name = StringField('Zone Name', validators=[
        DataRequired(),
        Length(min=2, max=50)
    ])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    delivery_fee = DecimalField('Delivery Fee (R)', validators=[
        DataRequired(),
        NumberRange(min=0)
    ])
    estimated_time = IntegerField('Estimated Time (minutes)', validators=[
        DataRequired(),
        NumberRange(min=5, max=180)
    ])
    min_order = DecimalField('Minimum Order Amount', validators=[
        DataRequired(),
        NumberRange(min=0)
    ], default=0)
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Zone')

class ShopInfoForm(FlaskForm):
    """Form for updating shop information"""
    shop_name = StringField('Shop Name', validators=[
        DataRequired(message="Shop name is required"),
        Length(min=2, max=100)
    ])
    category = SelectField('Category', 
                          choices=[
                              ('restaurant', 'Restaurant/Food'), 
                              ('butchery', 'Butchery'), 
                              ('grocery', 'Grocery Store'),
                              ('pharmacy', 'Pharmacy'),
                              ('hardware', 'Hardware'),
                              ('clothing', 'Clothing'),
                              ('electronics', 'Electronics'),
                              ('other', 'Other')
                          ])
    address = TextAreaField('Address', validators=[
        DataRequired(),
        Length(min=5, max=500)
    ])
    phone = StringField('Phone Number', validators=[
        DataRequired(),
        Regexp(r'^[0-9]{10}$', message="Please enter a valid 10-digit phone number")
    ])
    email = StringField('Email Address', validators=[
        Optional(),
        ExtendedEmail()
    ])
    description = TextAreaField('Description', validators=[Optional(), Length(max=1000)])
    is_open = BooleanField('Shop is Open for Business', default=True)
    logo = FileField('Shop Logo', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])
    submit = SubmitField('Save Information')

class ShopHoursForm(FlaskForm):
    """Form for updating shop business hours"""
    opening_hours = TimeField('Opening Hours', validators=[Optional()])
    closing_hours = TimeField('Closing Hours', validators=[Optional()])
    submit = SubmitField('Save Hours')

class ShopDeliveryForm(FlaskForm):
    """Form for updating shop delivery settings"""
    delivery_fee = DecimalField('Delivery Fee (R)', validators=[
        DataRequired(),
        NumberRange(min=0)
    ])
    min_order = DecimalField('Minimum Order Amount (R)', validators=[
        DataRequired(),
        NumberRange(min=0)
    ])
    preparation_time = IntegerField('Preparation Time (minutes)', validators=[
        DataRequired(),
        NumberRange(min=1, max=180)
    ])
    submit = SubmitField('Save Delivery Settings')
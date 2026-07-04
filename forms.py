from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, DateField, TimeField, IntegerField, FloatField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, Regexp, ValidationError
import re

def validate_indian_mobile(form, field):
    mobile_number = str(field.data or '').strip()
    if not mobile_number.isdigit():
        if not re.match(r'^\d+$', mobile_number):
            raise ValidationError("Only numbers are allowed.")
    if len(mobile_number) < 10:
        raise ValidationError("Mobile number must contain exactly 10 digits.")
    if len(mobile_number) > 10:
        raise ValidationError("Mobile number cannot exceed 10 digits.")
    if not re.match(r'^[6-9][0-9]{9}$', mobile_number):
        raise ValidationError("Enter a valid 10-digit Indian mobile number.")

class LoginForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Log In')

class RegisterForm(FlaskForm):
    # User fields
    email = StringField('Email Address', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long.'),
        Regexp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]', 
               message='Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character.')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match.')
    ])
    
    # Volunteer fields
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    mobile_number = StringField('Mobile Number', validators=[DataRequired(), validate_indian_mobile])
    address = StringField('Address', validators=[Optional(), Length(max=255)])
    gender = SelectField('Gender', choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')], validators=[DataRequired()])
    date_of_birth = DateField('Date of Birth', format='%Y-%m-%d', validators=[DataRequired()])
    skills = StringField('Skills (comma-separated)', validators=[Optional(), Length(max=255)])
    interests = StringField('Interests (comma-separated)', validators=[Optional(), Length(max=255)])
    availability = SelectField('Availability', choices=[
        ('Weekdays', 'Weekdays'),
        ('Weekends', 'Weekends'),
        ('All', 'All Availability'),
        ('Evenings', 'Evenings')
    ], validators=[DataRequired()])
    
    submit = SubmitField('Register')

class VolunteerProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email Address', validators=[DataRequired(), Email(), Length(max=120)])
    mobile_number = StringField('Mobile Number', validators=[DataRequired(), validate_indian_mobile])
    address = StringField('Address', validators=[Optional(), Length(max=255)])
    gender = SelectField('Gender', choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')], validators=[DataRequired()])
    date_of_birth = DateField('Date of Birth', format='%Y-%m-%d', validators=[DataRequired()])
    skills = StringField('Skills (comma-separated)', validators=[Optional(), Length(max=255)])
    interests = StringField('Interests (comma-separated)', validators=[Optional(), Length(max=255)])
    availability = SelectField('Availability', choices=[
        ('Weekdays', 'Weekdays'),
        ('Weekends', 'Weekends'),
        ('All', 'All Availability'),
        ('Evenings', 'Evenings')
    ], validators=[DataRequired()])
    
    submit = SubmitField('Update Profile')

class AdminVolunteerForm(FlaskForm):
    # This combines User creation + Volunteer creation for Admin to use
    email = StringField('Email Address', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[
        Optional(),
        Length(min=8, message='Password must be at least 8 characters long.')
    ])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    mobile_number = StringField('Mobile Number', validators=[DataRequired(), validate_indian_mobile])
    address = StringField('Address', validators=[Optional(), Length(max=255)])
    gender = SelectField('Gender', choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')], validators=[DataRequired()])
    date_of_birth = DateField('Date of Birth', format='%Y-%m-%d', validators=[DataRequired()])
    skills = StringField('Skills (comma-separated)', validators=[Optional(), Length(max=255)])
    interests = StringField('Interests (comma-separated)', validators=[Optional(), Length(max=255)])
    availability = SelectField('Availability', choices=[
        ('Weekdays', 'Weekdays'),
        ('Weekends', 'Weekends'),
        ('All', 'All Availability'),
        ('Evenings', 'Evenings')
    ], validators=[DataRequired()])
    
    submit = SubmitField('Save Volunteer')

class EventForm(FlaskForm):
    name = StringField('Event Name', validators=[DataRequired(), Length(max=150)])
    description = TextAreaField('Description', validators=[DataRequired()])
    category = SelectField('Category', choices=[
        ('Medical Camp', 'Medical Camp'),
        ('Education', 'Education'),
        ('Disaster Relief', 'Disaster Relief'),
        ('Food Drive', 'Food Drive'),
        ('Fundraising', 'Fundraising'),
        ('Environment', 'Environment'),
        ('Other', 'Other')
    ], validators=[DataRequired()])
    date = DateField('Date', format='%Y-%m-%d', validators=[DataRequired()])
    time = TimeField('Time', format='%H:%M', validators=[DataRequired()])
    venue = StringField('Venue', validators=[DataRequired(), Length(max=150)])
    required_volunteers = IntegerField('Required Volunteers', validators=[DataRequired(), NumberRange(min=1)])
    status = SelectField('Status', choices=[
        ('Upcoming', 'Upcoming'),
        ('Completed', 'Completed'),
        ('Closed', 'Closed')
    ], validators=[DataRequired()])
    
    submit = SubmitField('Save Event')

class ResourceForm(FlaskForm):
    name = StringField('Resource Name', validators=[DataRequired(), Length(max=100)])
    category = SelectField('Category', choices=[
        ('Food', 'Food'),
        ('Clothes', 'Clothes'),
        ('Books', 'Books'),
        ('Medical Supplies', 'Medical Supplies'),
        ('Educational Kits', 'Educational Kits'),
        ('Equipment', 'Equipment'),
        ('Other', 'Other')
    ], validators=[DataRequired()])
    quantity_available = IntegerField('Total Available Quantity', validators=[DataRequired(), NumberRange(min=0)])
    
    submit = SubmitField('Save Resource')

class AllocationForm(FlaskForm):
    resource_id = SelectField('Resource Name', coerce=int, validators=[DataRequired()])
    quantity_allocated = IntegerField('Quantity to Allocate', validators=[DataRequired(), NumberRange(min=1)])
    quantity_used = IntegerField('Quantity Used', validators=[Optional(), NumberRange(min=0)])
    
    submit = SubmitField('Allocate Resource')

def validate_not_future_date(form, field):
    import pytz
    from datetime import datetime
    kolkata_tz = pytz.timezone('Asia/Kolkata')
    today_kolkata = datetime.now(kolkata_tz).date()
    if field.data and field.data > today_kolkata:
        raise ValidationError("Donation date cannot be in the future.")

class DonationForm(FlaskForm):
    donor_name = StringField('Donor Name', validators=[DataRequired(), Length(max=100)])
    phone_number = StringField('Phone Number', validators=[DataRequired(), validate_indian_mobile])
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    amount = FloatField('Donation Amount (₹)', validators=[DataRequired(), NumberRange(min=0.01)])
    donation_date = DateField('Donation Date', format='%Y-%m-%d', validators=[DataRequired(), validate_not_future_date])
    payment_method = SelectField('Payment Method', choices=[
        ('Cash', 'Cash'),
        ('Card', 'Card'),
        ('Bank Transfer', 'Bank Transfer'),
        ('UPI', 'UPI'),
        ('Cheque', 'Cheque')
    ], validators=[DataRequired()])
    purpose = StringField('Purpose / Project', validators=[Optional(), Length(max=255)])
    
    submit = SubmitField('Log Donation')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long.'),
        Regexp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]', 
               message='Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character.')
    ])
    confirm_new_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('new_password', message='Passwords must match.')
    ])
    
    submit = SubmitField('Change Password')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

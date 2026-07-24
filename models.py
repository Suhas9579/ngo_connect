from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import synonym
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='volunteer') # 'admin' or 'volunteer'
    is_active = db.Column(db.Boolean, default=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    email_verified = db.Column(db.Boolean, default=False, nullable=True)
    ngo_name = db.Column(db.String(120), nullable=True)
    google_id = db.Column(db.String(100), nullable=True, unique=True)
    full_name = db.Column(db.String(100), nullable=True)
    profile_photo = db.Column(db.String(255), nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    mobile_number = db.Column(db.String(15), nullable=True)
    volunteer_id = db.Column(db.String(30), unique=True, nullable=True)
    
    # Relationships
    volunteer = db.relationship('Volunteer', backref='user', uselist=False, cascade="all, delete-orphan")
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    
    def set_password(self, password):
        try:
            import bcrypt
            salt = bcrypt.gensalt()
            self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        except (ImportError, AttributeError):
            from werkzeug.security import generate_password_hash
            self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        import bcrypt
        try:
            return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
        except Exception:
            # Fallback to check if it matches legacy generate_password_hash from werkzeug
            from werkzeug.security import check_password_hash
            try:
                return check_password_hash(self.password_hash, password)
            except Exception:
                return False

class Volunteer(db.Model):
    __tablename__ = 'volunteers'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    volunteer_id = db.Column(db.String(30), unique=True, nullable=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    mobile_number = db.Column(db.String(10), nullable=False)
    address = db.Column(db.String(255), nullable=True)
    gender = db.Column(db.String(10), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    skills = db.Column(db.String(255), nullable=True)  # Comma-separated list of skills
    interests = db.Column(db.String(255), nullable=True)  # Comma-separated list of interests
    availability = db.Column(db.String(50), nullable=False)  # 'Weekdays', 'Weekends', 'All', 'Evenings'
    join_date = db.Column(db.Date, default=datetime.utcnow().date)
    participation_count = db.Column(db.Integer, default=0)
    
    # Relationships
    applications = db.relationship('VolunteerApplication', backref='volunteer', lazy='dynamic', cascade="all, delete-orphan")
    attendance = db.relationship('Attendance', backref='volunteer', lazy='dynamic', cascade="all, delete-orphan")
    certificates = db.relationship('Certificate', backref='volunteer', lazy='dynamic', cascade="all, delete-orphan")

class Event(db.Model):
    __tablename__ = 'events'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)  # 'Medical Camp', 'Education', 'Disaster Relief', 'Food Drive', 'Fundraising', 'Environment', 'Other'
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    venue = db.Column(db.String(150), nullable=False)
    required_volunteers = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), nullable=False, default='Upcoming')  # 'Upcoming', 'Completed', 'Closed'
    @property
    def assigned_count(self):
        if hasattr(self, '_assigned_count'):
            return self._assigned_count
        return VolunteerApplication.query.filter(
            VolunteerApplication.event_id == self.id,
            VolunteerApplication.status.in_(['Applied', 'Approved'])
        ).count()

    @assigned_count.setter
    def assigned_count(self, value):
        self._assigned_count = value
    
    # Relationships
    applications = db.relationship('VolunteerApplication', backref='event', lazy='dynamic', cascade="all, delete-orphan")
    attendance = db.relationship('Attendance', backref='event', lazy='dynamic', cascade="all, delete-orphan")
    allocations = db.relationship('ResourceAllocation', backref='event', lazy='dynamic', cascade="all, delete-orphan")
    certificates = db.relationship('Certificate', backref='event', lazy='dynamic', cascade="all, delete-orphan")

class VolunteerApplication(db.Model):
    __tablename__ = 'volunteer_applications'
    
    id = db.Column(db.Integer, primary_key=True)
    volunteer_id = db.Column(db.Integer, db.ForeignKey('volunteers.id', ondelete='CASCADE'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Applied')  # 'Applied', 'Approved', 'Rejected', 'Cancelled'
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Attendance(db.Model):
    __tablename__ = 'attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    volunteer_id = db.Column(db.Integer, db.ForeignKey('volunteers.id', ondelete='CASCADE'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Present')  # 'Present', 'Absent'
    marked_by = db.Column(db.String(20), nullable=False)  # 'QR Code', 'Manual'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Manager Tracking Fields
    ip_address = db.Column(db.String(50), nullable=True)
    device_info = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Synonym / Aliases
    check_in_time = synonym('timestamp')

class Resource(db.Model):
    __tablename__ = 'resources'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(50), nullable=False)  # 'Food', 'Clothes', 'Books', 'Medical Supplies', 'Educational Kits', 'Equipment', 'Other'
    quantity_available = db.Column(db.Integer, nullable=False, default=0)
    quantity_allocated = db.Column(db.Integer, nullable=False, default=0)
    quantity_used = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Synonyms / Aliases to support both naming conventions seamlessly
    resource_name = synonym('name')
    available_quantity = synonym('quantity_available')
    allocated_quantity = synonym('quantity_allocated')
    used_quantity = synonym('quantity_used')
    
    # Relationships
    allocations = db.relationship('ResourceAllocation', backref='resource', lazy='dynamic', cascade="all, delete-orphan")
    
    @property
    def remaining_quantity(self):
        return self.quantity_available - self.quantity_allocated - self.quantity_used

class ResourceAllocation(db.Model):
    __tablename__ = 'resource_allocations'
    
    id = db.Column(db.Integer, primary_key=True)
    resource_id = db.Column(db.Integer, db.ForeignKey('resources.id', ondelete='CASCADE'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    quantity_allocated = db.Column(db.Integer, nullable=False)
    quantity_used = db.Column(db.Integer, nullable=False, default=0)
    allocated_at = db.Column(db.DateTime, default=datetime.utcnow)
    allocated_by = db.Column(db.String(100), nullable=False, default='Admin')

    # Synonyms / Aliases
    allocated_quantity = synonym('quantity_allocated')
    used_quantity = synonym('quantity_used')

class Donation(db.Model):
    __tablename__ = 'donations'
    
    id = db.Column(db.Integer, primary_key=True)
    donor_name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(10), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    donation_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    payment_method = db.Column(db.String(30), nullable=False)  # 'Cash', 'Card', 'Bank Transfer', 'UPI', 'Cheque'
    purpose = db.Column(db.String(255), nullable=True)

class Certificate(db.Model):
    __tablename__ = 'certificates'
    
    id = db.Column(db.Integer, primary_key=True)
    volunteer_id = db.Column(db.Integer, db.ForeignKey('volunteers.id', ondelete='CASCADE'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    certificate_number = db.Column(db.String(100), unique=True, nullable=False)
    issue_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    file_path = db.Column(db.String(255), nullable=False)

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)  # Null means broadcast to all users
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(30), nullable=False)  # 'Event', 'Approval', 'Reminder', 'Attendance', 'Certificate', 'General'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

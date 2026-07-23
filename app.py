import os
import io
import csv
import base64
import random
import socket
import qrcode
from datetime import datetime, date, time, timedelta

def get_local_ip():
    """Automatically detect local machine LAN IP for cross-device mobile testing"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def get_external_attendance_url(event_id):
    """Generate dynamic QR URLs using local machine IP (e.g. http://192.168.x.x:5000/attendance/scan/<id>)"""
    local_ip = get_local_ip()
    return f"http://{local_ip}:5000/attendance/scan/{event_id}"

from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_file, abort, session
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect

from config import Config
from models import db, User, Volunteer, Event, VolunteerApplication, Attendance, Resource, ResourceAllocation, Donation, Certificate, Notification
from forms import LoginForm, RegisterForm, EventForm, ResourceForm, AllocationForm, DonationForm, ChangePasswordForm, ForgotPasswordForm, VolunteerProfileForm, AdminVolunteerForm

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

import pytz

def convert_to_ist(dt):
    if not dt:
        return ""
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, time.min)
    if dt.tzinfo is None:
        utc = pytz.utc
        dt = utc.localize(dt)
    ist_tz = pytz.timezone('Asia/Kolkata')
    ist_dt = dt.astimezone(ist_tz)
    return ist_dt

def format_ist(dt, format_str='%d %b %Y, %I:%M %p'):
    if not dt:
        return ""
    ist_dt = convert_to_ist(dt)
    return ist_dt.strftime(format_str)

def format_ist_time_only(dt):
    return format_ist(dt, '%I:%M %p IST')

def format_full_attendance_date(dt):
    if not dt:
        return "Not Available"
    try:
        ist_dt = convert_to_ist(dt)
        date_str = ist_dt.strftime("%d %b %Y")
        time_str = ist_dt.strftime("%I:%M %p")
        return f"📅 {date_str} • 🕘 {time_str} IST"
    except Exception:
        return "Not Available"

app.jinja_env.filters['ist'] = format_ist
app.jinja_env.filters['to_ist'] = convert_to_ist
app.jinja_env.filters['ist_time'] = format_ist_time_only
app.jinja_env.filters['attendance_date'] = format_full_attendance_date

# Initialize Extensions
db.init_app(app)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'danger'

def manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if current_user.role != 'admin':
            flash("Unauthorized access. Redirected to your dashboard.", "warning")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def volunteer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if current_user.role != 'volunteer':
            flash("Unauthorized access. Redirected to your dashboard.", "warning")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    if user:
        session['user_id'] = user.id
        session['user_role'] = user.role
    return user

@app.before_request
def check_session_role_sync():
    if current_user.is_authenticated:
        session['user_id'] = current_user.id
        session['user_role'] = current_user.role

# Create folders if not exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['CERTIFICATE_FOLDER'], exist_ok=True)
os.makedirs(app.config['REPORTS_FOLDER'], exist_ok=True)

# Custom versioned url_for for static files cache busting
def versioned_url_for(endpoint, **values):
    if endpoint == 'static':
        filename = values.get('filename')
        if filename:
            file_path = os.path.join(app.root_path, endpoint, filename)
            if os.path.exists(file_path):
                mtime = int(os.stat(file_path).st_mtime)
                values['v'] = mtime
    return url_for(endpoint, **values)

@app.context_processor
def override_url_for():
    return dict(url_for=versioned_url_for)

# Disable caching for all dynamic html/json pages
@app.after_request
def add_header(response):
    if response.content_type and ('text/html' in response.content_type or 'application/json' in response.content_type):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Context processor for global templates variables
@app.context_processor
def inject_global_vars():
    import pytz
    kolkata_tz = pytz.timezone('Asia/Kolkata')
    today_date = datetime.now(kolkata_tz).date().strftime('%Y-%m-%d')
    if current_user.is_authenticated:
        # Get count of unread notifications
        unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        # Get top 5 notifications
        notifs = Notification.query.filter(
            (Notification.user_id == current_user.id) | (Notification.user_id == None)
        ).order_by(Notification.created_at.desc()).limit(5)
        return {
            'unread_notifications_count': unread_count,
            'notifications_list': notifs,
            'today_date': today_date
        }
    return {
        'unread_notifications_count': 0,
        'notifications_list': [],
        'today_date': today_date
    }

def create_notification(user_id, title, message, notification_type):
    """Helper to log a user notification"""
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type
    )
    db.session.add(notif)
    db.session.commit()

def format_currency_inr(amount):
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return "₹0"
    is_neg = amount < 0
    amount = abs(amount)
    s, *d = f"{amount:.2f}".split('.')
    if len(s) > 3:
        last3 = s[-3:]
        other = s[:-3]
        res = ""
        while len(other) > 2:
            res = "," + other[-2:] + res
            other = other[:-2]
        s = other + res + "," + last3
    dec = f".{d[0]}" if d and int(d[0]) > 0 else ""
    sign = "-" if is_neg else ""
    return f"{sign}₹{s}{dec}"

app.jinja_env.filters['format_currency'] = format_currency_inr
app.jinja_env.filters['inr'] = format_currency_inr

def sync_resource_totals(resource):
    allocations = ResourceAllocation.query.filter_by(resource_id=resource.id).all()
    resource.quantity_allocated = sum(a.quantity_allocated for a in allocations)
    resource.quantity_used = sum(a.quantity_used for a in allocations)

# --- SMART MATCHING ALGORITHM ---
CATEGORY_KEYWORDS = {
    'Medical Camp': ['medical', 'first aid', 'doctor', 'nurse', 'health', 'clinic', 'paramedic', 'cpr'],
    'Education': ['teach', 'tutor', 'educate', 'child', 'school', 'mentor', 'books', 'literacy'],
    'Disaster Relief': ['rescue', 'emergency', 'logistics', 'shelter', 'supply', 'first aid', 'driving'],
    'Food Drive': ['cook', 'food', 'nutrition', 'kitchen', 'distribution', 'logistics', 'packing'],
    'Fundraising': ['marketing', 'sales', 'finance', 'social media', 'events', 'outreach', 'writing'],
    'Environment': ['planting', 'cleanup', 'conservation', 'recycling', 'gardening', 'outdoors'],
    'Other': ['general', 'support', 'organize', 'driving', 'admin']
}

def calculate_match_score(volunteer, event):
    """
    Intelligent Matching Engine:
    1. Skill overlap matching: 40 points
    2. Date Availability: 30 points
    3. Category history match: 20 points
    4. General Experience: 10 points
    Returns (Score %, Matching Skills list, IsBusy bool)
    """
    score = 0
    matching_skills = []
    
    # 1. Skill overlap checking
    vol_skills_raw = volunteer.skills or ""
    vol_skills = [s.strip().lower() for s in vol_skills_raw.split(',') if s.strip()]
    keywords = CATEGORY_KEYWORDS.get(event.category, [])
    
    skill_hits = 0
    for keyword in keywords:
        for skill in vol_skills:
            if keyword in skill or skill in keyword:
                if keyword not in matching_skills:
                    matching_skills.append(skill)
                skill_hits += 1
    
    if skill_hits > 0:
        score += min(skill_hits * 15, 40) # cap skill match at 40
        
    # 2. Availability checking
    # Check if event day is weekend or weekday
    event_weekday = event.date.weekday() # 0 = Monday, 6 = Sunday
    is_weekend = event_weekday in [5, 6]
    
    avail = volunteer.availability
    avail_match = False
    if avail == 'All':
        avail_match = True
    elif avail == 'Weekends' and is_weekend:
        avail_match = True
    elif avail == 'Weekdays' and not is_weekend:
        avail_match = True
        
    if avail_match:
        score += 30
        
    # Check if volunteer is busy on this specific event date (assigned to another event)
    # Check approved event applications on the same date
    busy_check = db.session.query(VolunteerApplication).join(Event).filter(
        VolunteerApplication.volunteer_id == volunteer.id,
        VolunteerApplication.status == 'Approved',
        Event.date == event.date,
        Event.id != event.id
    ).first()
    is_busy = True if busy_check else False
    
    # 3. Category history match
    # Check if volunteer has participated (present) in events of same category
    past_participation = db.session.query(Attendance).join(Event).filter(
        Attendance.volunteer_id == volunteer.id,
        Attendance.status == 'Present',
        Event.category == event.category
    ).count()
    
    if past_participation > 0:
        score += min(past_participation * 10, 20) # cap category history at 20
        
    # 4. General Experience
    # Base on total participation count
    score += min(volunteer.participation_count * 2, 10) # cap experience points at 10
    
    # If the volunteer is busy, they can still be matched, but we record it.
    return score, matching_skills, is_busy

# --- REPORTLAB PDF GENERATOR HELPERS ---
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def generate_certificate_pdf(volunteer, event, cert_number):
    """Generates an elegant Landscape PDF Certificate of Appreciation"""
    pdf_filename = f"certificate_{cert_number}.pdf"
    file_path = os.path.join(app.config['CERTIFICATE_FOLDER'], pdf_filename)
    
    # Page settings: Landscape Letter size
    doc = SimpleDocTemplate(
        file_path,
        pagesize=landscape(letter),
        leftMargin=0.5*inch, rightMargin=0.5*inch,
        topMargin=0.5*inch, bottomMargin=0.5*inch
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CertTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=28,
        textColor=colors.HexColor('#0d9488'), # Teal
        alignment=1, # Centered
        spaceAfter=15
    )
    
    subtitle_style = ParagraphStyle(
        'CertSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=14,
        textColor=colors.HexColor('#475569'), # Slate 600
        alignment=1,
        spaceAfter=25
    )
    
    name_style = ParagraphStyle(
        'CertName',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        textColor=colors.HexColor('#4f46e5'), # Indigo
        alignment=1,
        spaceAfter=20
    )
    
    body_style = ParagraphStyle(
        'CertBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        textColor=colors.HexColor('#1e293b'),
        alignment=1,
        spaceAfter=25
    )
    
    meta_style = ParagraphStyle(
        'CertMeta',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#64748b'),
        alignment=0 # Left
    )
    
    meta_right = ParagraphStyle(
        'CertMetaRight',
        parent=meta_style,
        alignment=2 # Right
    )

    story = []
    
    # Spacing and layout
    story.append(Spacer(1, 0.8*inch))
    story.append(Paragraph("CERTIFICATE OF APPRECIATION", title_style))
    story.append(Paragraph("PROUDLY PRESENTED TO", subtitle_style))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(volunteer.full_name.upper(), name_style))
    story.append(Spacer(1, 0.1*inch))
    
    event_str = f"<b>{event.name}</b> ({event.category})"
    date_str = event.date.strftime('%B %d, %Y')
    
    body_text = f"in recognition of their outstanding service, dedication, and invaluable contribution as a volunteer<br/>" \
                f"during the community outreach program at {event_str}<br/>" \
                f"held on <b>{date_str}</b> at {event.venue}."
    
    story.append(Paragraph(body_text, body_style))
    story.append(Spacer(1, 0.4*inch))
    
    # Metadata footer table (Signatures, Certificate No, Date)
    footer_data = [
        [
            Paragraph(f"DATE ISSUED:<br/><b>{format_ist(datetime.utcnow(), '%Y-%m-%d')}</b>", meta_style),
            Paragraph("AUTHORIZED SIGNATURE:<br/><br/>________________________<br/><b>NGO Executive Manager</b>", ParagraphStyle('CenterMeta', parent=meta_style, alignment=1)),
            Paragraph(f"CERTIFICATE NUMBER:<br/><b>{cert_number}</b>", meta_right)
        ]
    ]
    
    footer_table = Table(footer_data, colWidths=[2.5*inch, 3*inch, 2.5*inch])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    
    story.append(footer_table)
    
    # Drawing border callback
    def draw_background(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#0d9488'))
        canvas.setLineWidth(3)
        canvas.rect(20, 20, doc.pagesize[0]-40, doc.pagesize[1]-40)
        
        canvas.setStrokeColor(colors.HexColor('#6366f1'))
        canvas.setLineWidth(1)
        canvas.rect(25, 25, doc.pagesize[0]-50, doc.pagesize[1]-50)
        
        # Draw logo in top-left corner
        page_width, page_height = doc.pagesize
        logo_path = os.path.join(app.root_path, 'static', 'images', 'logo.png')
        if os.path.exists(logo_path):
            try:
                from PIL import Image as PILImage
                with PILImage.open(logo_path) as img:
                    aspect = img.height / img.width
                    logo_w = 60
                    logo_h = logo_w * aspect
                canvas.drawImage(logo_path, 35, page_height - 35 - logo_h, width=logo_w, height=logo_h, mask='auto')
            except Exception:
                pass
        
        # Draw nice watermarks or seals
        canvas.setFillColor(colors.HexColor('#f8fafc'))
        canvas.restoreState()
        
    doc.build(story, onFirstPage=draw_background)
    return file_path

def generate_report_pdf(title, headers, data, filename):
    """Generates a professional tabular Report PDF"""
    file_path = os.path.join(app.config['REPORTS_FOLDER'], filename)
    doc = SimpleDocTemplate(
        file_path,
        pagesize=letter,
        leftMargin=0.5*inch, rightMargin=0.5*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'RepTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        textColor=colors.HexColor('#0d9488'),
        spaceAfter=15
    )
    
    meta_style = ParagraphStyle(
        'RepMeta',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=20
    )
    
    logo_path = os.path.join(app.root_path, 'static', 'images', 'logo.png')
    logo_flowable = None
    if os.path.exists(logo_path):
        try:
            from PIL import Image as PILImage
            with PILImage.open(logo_path) as img:
                aspect = img.height / img.width
                logo_height = 80 * aspect
            logo_flowable = Image(logo_path, width=80, height=logo_height)
        except Exception:
            logo_flowable = Image(logo_path, width=80, height=40)
            
    story = []
    if logo_flowable:
        story.append(logo_flowable)
        story.append(Spacer(1, 10))
        
    story.extend([
        Paragraph(title, title_style),
        Paragraph(f"Generated on {format_ist(datetime.utcnow(), '%Y-%m-%d %H:%M IST')} | NGO Connect Platform", meta_style)
    ])
    
    table_data = [headers]
    for row in data:
        table_data.append(row)

    # Calculate widths based on page width
    available_width = doc.width
    num_cols = len(headers)
    col_width = available_width / num_cols
    
    t = Table(table_data, colWidths=[col_width]*num_cols)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0d9488')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('TOPPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f8fafc')),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#ffffff'), colors.HexColor('#f1f5f9')]),
        ('TOPPADDING', (0,1), (-1,-1), 6),
        ('BOTTOMPADDING', (0,1), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    
    story.append(t)
    doc.build(story)
    return file_path

# --- ROUTE HANDLERS ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        flash("You are already logged in as another user. Please logout first.", "warning")
        return redirect(url_for('dashboard'))
        
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            session['user_id'] = user.id
            session['user_role'] = user.role
            flash("Successfully logged in!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid email or password.", "danger")
            
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        flash("You are already logged in as another user. Please logout first.", "warning")
        return redirect(url_for('dashboard'))
        
    form = RegisterForm()
    if form.validate_on_submit():
        # Check duplicate email
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash("Email already registered.", "danger")
            return render_template('register.html', form=form)
            
        # Create user
        user = User(email=form.email.data, role='volunteer')
        user.set_password(form.password.data)
        
        # Create volunteer profile
        vol = Volunteer(
            user=user,
            full_name=form.full_name.data,
            email=form.email.data,
            mobile_number=form.mobile_number.data,
            address=form.address.data,
            gender=form.gender.data,
            date_of_birth=form.date_of_birth.data,
            skills=form.skills.data,
            interests=form.interests.data,
            availability=form.availability.data
        )
        
        db.session.add(user)
        db.session.add(vol)
        db.session.commit()
        
        # Notify admin of new volunteer
        admin = User.query.filter_by(role='admin').first()
        if admin:
            create_notification(
                user_id=admin.id,
                title="New Volunteer Registered",
                message=f"{vol.full_name} has registered on the platform.",
                notification_type="Approval"
            )
            
        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for('login'))
        
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('user_id', None)
    session.pop('user_role', None)
    flash("You have logged out.", "success")
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    email = request.form.get('email')
    # Mocking Forgot Password UI response
    flash(f"If {email} is registered, a password reset link has been simulated to your inbox!", "success")
    return redirect(url_for('login'))

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Invalid current password.", "danger")
        else:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("Password updated successfully!", "success")
            return redirect(url_for('dashboard'))
            
    return render_template('change_password.html', form=form, active_page='')

# --- DASHBOARD ---
@app.route('/dashboard')
@login_required
def dashboard():
    current_date = datetime.utcnow().strftime('%A, %b %d, %Y')
    
    if current_user.role == 'admin':
        # Admin statistics
        total_volunteers = Volunteer.query.count()
        # Active volunteers = attended at least 1 event
        active_volunteers = Volunteer.query.filter(Volunteer.participation_count > 0).count()
        upcoming_events = Event.query.filter_by(status='Upcoming').count()
        completed_events = Event.query.filter_by(status='Completed').count()
        total_donations = db.session.query(db.func.sum(Donation.amount)).scalar() or 0.0
        resources_count = Resource.query.count()
        total_resources = db.session.query(db.func.sum(Resource.quantity_available)).scalar() or 0
        allocated_resources = db.session.query(db.func.sum(ResourceAllocation.quantity_allocated)).scalar() or 0
        used_resources = db.session.query(db.func.sum(ResourceAllocation.quantity_used)).scalar() or 0
        remaining_resources = total_resources - allocated_resources - used_resources
        
        # Calculate attendance rate = present checkins / total assignments
        total_assignments = db.session.query(VolunteerApplication).filter_by(status='Approved').count()
        total_presence = db.session.query(Attendance).filter_by(status='Present').count()
        attendance_rate = (total_presence / total_assignments * 100) if total_assignments > 0 else 100.0
        
        stats = {
            'total_volunteers': total_volunteers,
            'active_volunteers': active_volunteers,
            'upcoming_events': upcoming_events,
            'completed_events': completed_events,
            'total_donations': total_donations,
            'resources_count': resources_count,
            'total_resources': total_resources,
            'allocated_resources': allocated_resources,
            'used_resources': used_resources,
            'remaining_resources': remaining_resources,
            'attendance_rate': attendance_rate
        }
        
        # Dynamic Chart.js values
        # 1. Real dynamic donations monthly trend
        monthly_dons = db.session.query(
            db.func.strftime('%m', Donation.donation_date),
            db.func.sum(Donation.amount)
        ).group_by(db.func.strftime('%m', Donation.donation_date)).all()
        
        month_names = {
            '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr', '05': 'May', '06': 'Jun',
            '07': 'Jul', '08': 'Aug', '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
        }
        
        trend_labels = []
        trend_values = []
        for m_num in sorted(month_names.keys())[:6]:
            val = 0.0
            for m, amt in monthly_dons:
                if m == m_num:
                    val = float(amt)
                    break
            trend_labels.append(month_names[m_num])
            trend_values.append(val)
            
        # 2. Real dynamic volunteer growth trend
        monthly_vols = db.session.query(
            db.func.strftime('%m', Volunteer.join_date),
            db.func.count(Volunteer.id)
        ).group_by(db.func.strftime('%m', Volunteer.join_date)).all()
        
        vol_labels = []
        vol_values = []
        cumulative = 0
        for m_num in sorted(month_names.keys())[:6]:
            count = 0
            for m, cnt in monthly_vols:
                if m == m_num:
                    count = cnt
                    break
            cumulative += count
            vol_labels.append(month_names[m_num])
            vol_values.append(cumulative)
        
        # 3. Resources categories split
        res_categories = db.session.query(Resource.category, db.func.sum(Resource.quantity_available)).group_by(Resource.category).all()
        res_labels = [c[0] for c in res_categories]
        res_values = [c[1] for c in res_categories]
        
        charts_data = {
            'donations': {'labels': trend_labels, 'values': trend_values},
            'volunteers': {'labels': vol_labels, 'values': vol_values},
            'resources': {'labels': res_labels, 'values': res_values}
        }
        
        # Recent activities
        recent_activities = []
        # Recent volunteers
        recent_vols = Volunteer.query.order_by(Volunteer.join_date.desc()).limit(3).all()
        for v in recent_vols:
            recent_activities.append({
                'icon': 'bi-person-plus',
                'title': f"New Volunteer Onboarded",
                'desc': f"{v.full_name} registered with skills: {v.skills or 'None'}",
                'time': v.join_date.strftime('%b %d')
            })
            
        # Recent donations
        recent_dons = Donation.query.order_by(Donation.donation_date.desc()).limit(3).all()
        for d in recent_dons:
            recent_activities.append({
                'icon': 'bi-cash',
                'title': f"Received Donation",
                'desc': f"{format_currency_inr(d.amount)} contributed by {d.donor_name} via {d.payment_method}",
                'time': d.donation_date.strftime('%b %d')
            })
            
        # Sort recent activities (simulating time diff, just show latest)
        
        return render_template('dashboard.html', stats=stats, charts_data=charts_data, recent_activities=recent_activities, current_date=current_date, active_page='dashboard')
    
    else:
        # Volunteer statistics
        vol = current_user.volunteer
        applied_events = VolunteerApplication.query.filter_by(volunteer_id=vol.id).count()
        assigned_events = VolunteerApplication.query.filter_by(volunteer_id=vol.id, status='Approved').count()
        attended_events = Attendance.query.filter_by(volunteer_id=vol.id, status='Present').count()
        
        # Attendance percentage = Attended Events / Assigned Events * 100
        attendance_pct = (attended_events / assigned_events * 100) if assigned_events > 0 else 100.0
        
        stats = {
            'applied_events': applied_events,
            'assigned_events': assigned_events,
            'attended_events': attended_events,
            'attendance_pct': attendance_pct
        }
        
        # Upcoming Assigned Events
        upcoming_assigned = db.session.query(Event).join(VolunteerApplication).filter(
            VolunteerApplication.volunteer_id == vol.id,
            VolunteerApplication.status == 'Approved',
            Event.status == 'Upcoming'
        ).all()
        
        return render_template('dashboard.html', stats=stats, upcoming_assigned=upcoming_assigned, current_date=current_date, active_page='dashboard')

# --- VOLUNTEER MODULE (CRUD) ---
@app.route('/volunteers', methods=['GET'])
@login_required
@manager_required
def volunteers():
    if current_user.role == 'admin':
        # Admin Directory View
        search_query = request.args.get('search')
        skill_filter = request.args.get('skill')
        availability_filter = request.args.get('availability')
        
        query = Volunteer.query
        
        if search_query:
            query = query.filter(
                (Volunteer.full_name.like(f"%{search_query}%")) | 
                (Volunteer.email.like(f"%{search_query}%")) | 
                (Volunteer.mobile_number.like(f"%{search_query}%"))
            )
        if skill_filter:
            query = query.filter(Volunteer.skills.like(f"%{skill_filter}%"))
        if availability_filter:
            query = query.filter_by(availability=availability_filter)
            
        volunteers_list = query.all()
        
        # Build forms
        add_form = AdminVolunteerForm()
        
        # Retrieve all skills for filter dropdown
        vols_skills = db.session.query(Volunteer.skills).all()
        all_skills = set()
        for skills in vols_skills:
            if skills[0]:
                for s in skills[0].split(','):
                    all_skills.add(s.strip())
                    
        filters = {'search': search_query, 'skill': skill_filter, 'availability': availability_filter}
        
        return render_template(
            'volunteers.html',
            volunteers_list=volunteers_list,
            add_form=add_form,
            all_skills_list=sorted(list(all_skills)),
            filters=filters,
            active_page='volunteers'
        )
    else:
        # Volunteer profile editing view
        return redirect(url_for('volunteer_profile'))

@app.route('/volunteers/profile', methods=['GET', 'POST'])
@login_required
@volunteer_required
def volunteer_profile():
    if current_user.role != 'volunteer':
        abort(403)
        
    vol = current_user.volunteer
    profile_form = VolunteerProfileForm(obj=vol)
    
    if profile_form.validate_on_submit():
        new_email = profile_form.email.data
        if new_email != vol.email:
            existing_user = User.query.filter(User.email == new_email, User.id != vol.user_id).first()
            if existing_user:
                flash("Email address is already in use by another account.", "danger")
                return redirect(url_for('volunteer_profile'))
            vol.email = new_email
            vol.user.email = new_email
            
        profile_form.populate_obj(vol)
        db.session.commit()
        db.session.refresh(vol)
        db.session.refresh(vol.user)
        flash("Profile updated successfully!", "success")
        return redirect(url_for('volunteer_profile'))
        
    # Get attendance statistics
    assigned_events = VolunteerApplication.query.filter_by(volunteer_id=vol.id, status='Approved').count()
    attended_events = Attendance.query.filter_by(volunteer_id=vol.id, status='Present').count()
    attendance_pct = (attended_events / assigned_events * 100) if assigned_events > 0 else 100.0
    
    # Applications history
    applications_history = VolunteerApplication.query.filter_by(volunteer_id=vol.id).order_by(VolunteerApplication.applied_at.desc()).all()
    
    # Attendance dictionary mapping event_id -> Attendance
    attendance_list = Attendance.query.filter_by(volunteer_id=vol.id).all()
    attendance_map = {att.event_id: att for att in attendance_list}
    
    return render_template(
        'volunteers.html',
        profile_form=profile_form,
        attendance_pct=attendance_pct,
        applications_history=applications_history,
        attendance_map=attendance_map,
        active_page='profile'
    )

@app.route('/volunteers/add', methods=['POST'])
@login_required
@manager_required
def add_volunteer():
    if current_user.role != 'admin':
        abort(403)
        
    form = AdminVolunteerForm()
    if form.validate_on_submit():
        # Check duplicate
        existing = User.query.filter_by(email=form.email.data).first()
        if existing:
            flash("Email already registered.", "danger")
            return redirect(url_for('volunteers'))
            
        temp_pass = form.password.data if form.password.data else "vol12345"
        
        user = User(email=form.email.data, role='volunteer')
        user.set_password(temp_pass)
        
        vol = Volunteer(
            user=user,
            full_name=form.full_name.data,
            email=form.email.data,
            mobile_number=form.mobile_number.data,
            address=form.address.data,
            gender=form.gender.data,
            date_of_birth=form.date_of_birth.data,
            skills=form.skills.data,
            interests=form.interests.data,
            availability=form.availability.data
        )
        
        db.session.add(user)
        db.session.add(vol)
        db.session.commit()
        
        flash(f"Volunteer {vol.full_name} onboarded successfully! Temporary Password: {temp_pass}", "success")
    else:
        # Flash form errors
        for field, errors in form.errors.items():
            for err in errors:
                flash(f"Error in {field}: {err}", "danger")
                
    return redirect(url_for('volunteers'))

@app.route('/volunteers/edit/<int:id>', methods=['POST'])
@login_required
@manager_required
def edit_volunteer(id):
    if current_user.role != 'admin':
        abort(403)
        
    vol = Volunteer.query.get_or_404(id)
    # Extract fields from standard request form
    mobile_number = request.form.get('mobile_number', '').strip()
    import re
    err = None
    if not mobile_number.isdigit():
        if not re.match(r'^\d+$', mobile_number):
            err = "Only numbers are allowed."
    if not err and len(mobile_number) < 10:
        err = "Mobile number must contain exactly 10 digits."
    if not err and len(mobile_number) > 10:
        err = "Mobile number cannot exceed 10 digits."
    if not err and not re.match(r'^[6-9][0-9]{9}$', mobile_number):
        err = "Enter a valid 10-digit Indian mobile number."
        
    if err:
        flash(f"Error: {err}", "danger")
        return redirect(url_for('volunteers'))

    new_email = request.form.get('email', '').strip()
    if new_email and new_email != vol.email:
        existing_user = User.query.filter(User.email == new_email, User.id != vol.user_id).first()
        if existing_user:
            flash("Email address is already in use by another account.", "danger")
            return redirect(url_for('volunteers'))
        vol.email = new_email
        vol.user.email = new_email

    vol.full_name = request.form.get('full_name')
    vol.mobile_number = mobile_number
    vol.gender = request.form.get('gender')
    dob_str = request.form.get('date_of_birth')
    if dob_str:
        vol.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date()
    vol.availability = request.form.get('availability')
    vol.address = request.form.get('address')
    vol.skills = request.form.get('skills')
    vol.interests = request.form.get('interests')
    
    db.session.commit()
    db.session.refresh(vol)
    db.session.refresh(vol.user)
    flash(f"Volunteer profile updated successfully.", "success")
    return redirect(url_for('volunteers'))

@app.route('/volunteers/delete/<int:id>', methods=['POST'])
@login_required
@manager_required
def delete_volunteer(id):
    if current_user.role != 'admin':
        abort(403)
        
    vol = Volunteer.query.get_or_404(id)
    user = vol.user
    
    db.session.delete(vol)
    db.session.delete(user)
    db.session.commit()
    
    flash("Volunteer successfully deleted.", "success")
    return redirect(url_for('volunteers'))


# --- EVENT MODULE ---
@app.route('/events')
@login_required
def events():
    events_list = Event.query.order_by(Event.date.desc()).all()
    create_form = EventForm()
    
    # Pre-populate some properties if volunteer
    applications_map = {}
    certificates_map = {}
    
    if current_user.role == 'volunteer':
        vol = current_user.volunteer
        apps = VolunteerApplication.query.filter_by(volunteer_id=vol.id).all()
        applications_map = {app.event_id: app for app in apps}
        
        certs = Certificate.query.filter_by(volunteer_id=vol.id).all()
        certificates_map = {c.event_id: c for c in certs}
        
    # Count assigned/attended for templates
    for ev in events_list:
        ev.assigned_count = VolunteerApplication.query.filter(
            VolunteerApplication.event_id == ev.id,
            VolunteerApplication.status.in_(['Applied', 'Approved'])
        ).count()
        ev.attendance_count = Attendance.query.filter_by(event_id=ev.id, status='Present').count()
        
    return render_template(
        'events.html',
        events_list=events_list,
        create_form=create_form,
        applications_map=applications_map,
        certificates_map=certificates_map,
        active_page='events'
    )

@app.route('/events/create', methods=['POST'])
@login_required
@manager_required
def create_event():
    if current_user.role != 'admin':
        abort(403)
        
    form = EventForm()
    if form.validate_on_submit():
        event = Event(
            name=form.name.data,
            description=form.description.data,
            category=form.category.data,
            date=form.date.data,
            time=form.time.data,
            venue=form.venue.data,
            required_volunteers=form.required_volunteers.data,
            status=form.status.data
        )
        db.session.add(event)
        db.session.commit()
        
        # Broadcast notification to all volunteers
        volunteers = User.query.filter_by(role='volunteer').all()
        for v in volunteers:
            create_notification(
                user_id=v.id,
                title="New Event Scheduled",
                message=f"A new event '{event.name}' under {event.category} is scheduled on {event.date}.",
                notification_type="Event"
            )
            
        flash(f"Event '{event.name}' created successfully!", "success")
    else:
        for field, errors in form.errors.items():
            for err in errors:
                flash(f"Error in {field}: {err}", "danger")
                
    return redirect(url_for('events'))

@app.route('/events/edit/<int:id>', methods=['POST'])
@login_required
@manager_required
def edit_event(id):
    if current_user.role != 'admin':
        abort(403)
        
    event = Event.query.get_or_404(id)
    event.name = request.form.get('name')
    event.description = request.form.get('description')
    event.category = request.form.get('category')
    event.required_volunteers = int(request.form.get('required_volunteers'))
    event.venue = request.form.get('venue')
    event.status = request.form.get('status')
    
    date_str = request.form.get('date')
    if date_str:
        event.date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
    time_str = request.form.get('time')
    if time_str:
        event.time = datetime.strptime(time_str, '%H:%M').time()
        
    db.session.commit()
    db.session.refresh(event)
    flash("Event details modified successfully.", "success")
    return redirect(url_for('event_details', id=event.id))

@app.route('/events/apply/<int:event_id>', methods=['POST'])
@login_required
@volunteer_required
def apply_event(event_id):
    if current_user.role != 'volunteer':
        abort(403)
        
    vol = current_user.volunteer
    event = Event.query.get_or_404(event_id)
    
    # 1. Verify event capacity
    if event.assigned_count >= event.required_volunteers:
        flash("This event has already reached its volunteer registration capacity.", "warning")
        return redirect(url_for('events'))
        
    # 2. Prevent duplicate applications
    existing = VolunteerApplication.query.filter_by(volunteer_id=vol.id, event_id=event_id).first()
    if existing:
        if existing.status == 'Cancelled':
            existing.status = 'Applied'
            db.session.commit()
            flash("Application submitted successfully!", "success")
        else:
            flash("You have already applied for this event.", "info")
        return redirect(url_for('events'))
        
    # 3. Create Application record
    app_ticket = VolunteerApplication(
        volunteer_id=vol.id,
        event_id=event_id,
        status='Applied'
    )
    db.session.add(app_ticket)
    db.session.commit()
    
    # Notify admin
    admin = User.query.filter_by(role='admin').first()
    if admin:
        create_notification(
            user_id=admin.id,
            title="Volunteer Sign-up Request",
            message=f"{vol.full_name} applied for upcoming event.",
            notification_type="Approval"
        )
        
    flash("Application submitted successfully!", "success")
    return redirect(url_for('events'))

@app.route('/events/cancel/<int:event_id>', methods=['POST'])
@login_required
@volunteer_required
def cancel_event_application(event_id):
    if current_user.role != 'volunteer':
        abort(403)
        
    vol = current_user.volunteer
    app_ticket = VolunteerApplication.query.filter_by(volunteer_id=vol.id, event_id=event_id).first()
    
    if app_ticket:
        db.session.delete(app_ticket)
        db.session.commit()
        flash("Application cancelled successfully.", "success")
    else:
        flash("Application record not found.", "danger")
        
    return redirect(url_for('events'))

@app.route('/events/details/<int:id>')
@login_required
@manager_required
def event_details(id):
    if current_user.role != 'admin':
        abort(403)
        
    event = Event.query.get_or_404(id)
    
    # Lists of volunteers
    assigned_list = VolunteerApplication.query.filter(
        VolunteerApplication.event_id == event.id,
        VolunteerApplication.status.in_(['Applied', 'Approved'])
    ).all()
    pending_list = VolunteerApplication.query.filter_by(event_id=event.id, status='Pending').all()
    
    # Resource Allocations
    allocations = ResourceAllocation.query.filter_by(event_id=event.id).all()
    # Available resources for dropdown allocation selector
    available_resources = Resource.query.all()
    
    # Smart recommendations
    # Fetch all volunteers not assigned or pending to this event
    assigned_vol_ids = [a.volunteer_id for a in assigned_list]
    pending_vol_ids = [p.volunteer_id for p in pending_list]
    excluded_ids = assigned_vol_ids + pending_vol_ids
    
    vols = Volunteer.query.filter(~Volunteer.id.in_(excluded_ids)).all() if excluded_ids else Volunteer.query.all()
    
    recommendations = []
    for volunteer in vols:
        score, matching_skills, is_busy = calculate_match_score(volunteer, event)
        recommendations.append({
            'volunteer': volunteer,
            'score': score,
            'matching_skills': matching_skills,
            'is_busy': is_busy
        })
        
    # Sort recommendations by match score descending
    recommendations.sort(key=lambda x: x['score'], reverse=True)
    # Cap recommendations at top 10
    recommendations = recommendations[:10]
    
    # Generate event QR code as Base64 representation
    qr = qrcode.QRCode(version=1, box_size=8, border=3)
    qr_url = get_external_attendance_url(event.id)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_code_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    # Attendance mapping for completed events manual verify
    attendance_records = Attendance.query.filter_by(event_id=event.id).all()
    attendance_map = {att.volunteer_id: att for att in attendance_records}
    
    # Certificates mapping for completed event
    certs = Certificate.query.filter_by(event_id=event.id).all()
    certificates_map = {c.volunteer_id: c for c in certs}
    
    return render_template(
        'event_details.html',
        event=event,
        assigned_list=assigned_list,
        pending_list=pending_list,
        allocations=allocations,
        available_resources=available_resources,
        recommendations=recommendations,
        qr_code_base64=qr_code_base64,
        qr_url=qr_url,
        attendance_map=attendance_map,
        certificates_map=certificates_map,
        active_page='events'
    )

@app.route('/events/update-app-status/<int:app_id>/<string:status>', methods=['POST'])
@login_required
@manager_required
def update_application_status(app_id, status):
    if current_user.role != 'admin':
        abort(403)
        
    app_ticket = VolunteerApplication.query.get_or_404(app_id)
    app_ticket.status = status
    db.session.commit()
    
    # Notify volunteer
    create_notification(
        user_id=app_ticket.volunteer.user_id,
        title=f"Application {status}",
        message=f"Your volunteer request for event '{app_ticket.event.name}' has been {status}.",
        notification_type="Approval"
    )
    
    flash(f"Application ticket updated to {status}.", "success")
    return redirect(url_for('event_details', id=app_ticket.event_id))

@app.route('/events/assign-direct/<int:event_id>/<int:volunteer_id>', methods=['POST'])
@login_required
@manager_required
def assign_volunteer_direct(event_id, volunteer_id):
    if current_user.role != 'admin':
        abort(403)
        
    # Check if application ticket already exists
    app_ticket = VolunteerApplication.query.filter_by(event_id=event_id, volunteer_id=volunteer_id).first()
    if app_ticket:
        app_ticket.status = 'Approved'
    else:
        app_ticket = VolunteerApplication(
            event_id=event_id,
            volunteer_id=volunteer_id,
            status='Approved'
        )
        db.session.add(app_ticket)
        
    db.session.commit()
    
    # Notify volunteer
    vol = Volunteer.query.get(volunteer_id)
    create_notification(
        user_id=vol.user_id,
        title="Assigned to Event",
        message=f"You have been assigned to volunteer at '{app_ticket.event.name}' directly by administration.",
        notification_type="Event"
    )
    
    flash(f"Assigned {vol.full_name} to event.", "success")
    return redirect(url_for('event_details', id=event_id))

@app.route('/events/close/<int:id>/<string:status>', methods=['POST'])
@login_required
@manager_required
def close_event_admin(id, status):
    if current_user.role != 'admin':
        abort(403)
        
    event = Event.query.get_or_404(id)
    event.status = status
    db.session.commit()
    
    # If completed, check off default attendance entries as Present (or let admin mark manual check sheet)
    if status == 'Completed':
        # Default all assigned volunteers to Present if attendance record doesn't exist yet
        assigned = VolunteerApplication.query.filter_by(event_id=event.id, status='Approved').all()
        for app_ticket in assigned:
            existing_att = Attendance.query.filter_by(event_id=event.id, volunteer_id=app_ticket.volunteer_id).first()
            if not existing_att:
                att = Attendance(
                    volunteer_id=app_ticket.volunteer_id,
                    event_id=event.id,
                    date=event.date,
                    status='Present',
                    marked_by='Manual'
                )
                db.session.add(att)
                
                # Increment participation count
                app_ticket.volunteer.participation_count += 1
                
        db.session.commit()
        flash("Event completed! Default attendance recorded.", "success")
    else:
        flash(f"Event status set to {status}.", "info")
        
    return redirect(url_for('event_details', id=event.id))


# --- RESOURCE MODULE (CRUD) ---
@app.route('/resources')
@login_required
@manager_required
def resources():
    if current_user.role != 'admin':
        abort(403)
        
    resources_list = Resource.query.all()
    for res in resources_list:
        sync_resource_totals(res)
    db.session.commit()
    
    search_history = request.args.get('search_history', '')
    event_filter = request.args.get('event_filter', '')
    date_filter = request.args.get('date_filter', '')
    
    history_query = ResourceAllocation.query.join(Resource).join(Event)
    if search_history:
        history_query = history_query.filter(
            (Resource.name.like(f"%{search_history}%")) |
            (Event.name.like(f"%{search_history}%"))
        )
    if event_filter:
        try:
            history_query = history_query.filter(ResourceAllocation.event_id == int(event_filter))
        except ValueError:
            pass
    if date_filter:
        try:
            d_obj = datetime.strptime(date_filter, '%Y-%m-%d').date()
            history_query = history_query.filter(db.func.date(ResourceAllocation.allocated_at) == d_obj)
        except ValueError:
            pass
            
    allocations_list = history_query.order_by(ResourceAllocation.allocated_at.desc()).all()
    resource_form = ResourceForm()
    events_list = Event.query.order_by(Event.name).all()
    
    return render_template(
        'resources.html',
        resources_list=resources_list,
        allocations_list=allocations_list,
        resource_form=resource_form,
        events_list=events_list,
        search_history=search_history,
        event_filter=event_filter,
        date_filter=date_filter,
        active_page='resources'
    )

@app.route('/resources/add', methods=['POST'])
@login_required
@manager_required
def add_resource():
    if current_user.role != 'admin':
        abort(403)
        
    form = ResourceForm()
    if form.validate_on_submit():
        try:
            qty = form.quantity_available.data
            if qty is None or qty < 0:
                flash("Remaining quantity cannot be negative.", "danger")
                return redirect(url_for('resources'))
                
            existing = Resource.query.filter_by(name=form.name.data).first()
            if existing:
                flash("Resource type already exists.", "danger")
                return redirect(url_for('resources'))
                
            res = Resource(
                name=form.name.data,
                category=form.category.data,
                quantity_available=qty,
                quantity_allocated=0,
                quantity_used=0
            )
            db.session.add(res)
            db.session.commit()
            flash(f"Resource '{res.name}' added successfully.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding resource: {str(e)}", "danger")
    else:
        for field, errors in form.errors.items():
            for err in errors:
                flash(f"Error in {field}: {err}", "danger")
                
    return redirect(url_for('resources'))

@app.route('/resources/edit/<int:id>', methods=['POST'])
@login_required
@manager_required
def edit_resource(id):
    if current_user.role != 'admin':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
        abort(403)
        
    res = Resource.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    
    try:
        new_name = request.form.get('name', '').strip()
        new_category = request.form.get('category', '').strip()
        raw_avail = request.form.get('quantity_available')
        raw_alloc = request.form.get('quantity_allocated', res.quantity_allocated)
        raw_used = request.form.get('quantity_used', res.quantity_used)
        
        if not new_name:
            msg = "Resource name cannot be empty."
            if is_ajax: return jsonify({'success': False, 'message': msg}), 400
            flash(msg, "danger")
            return redirect(url_for('resources'))
            
        if new_name != res.name:
            existing = Resource.query.filter(Resource.name == new_name, Resource.id != id).first()
            if existing:
                msg = f"Resource name '{new_name}' already exists."
                if is_ajax: return jsonify({'success': False, 'message': msg}), 400
                flash(msg, "danger")
                return redirect(url_for('resources'))
                
        try:
            new_avail = int(raw_avail)
            new_alloc = int(raw_alloc)
            new_used = int(raw_used)
            if new_avail < 0 or new_alloc < 0 or new_used < 0:
                raise ValueError()
        except (ValueError, TypeError):
            msg = "Resource quantities must be non-negative integers."
            if is_ajax: return jsonify({'success': False, 'message': msg}), 400
            flash(msg, "danger")
            return redirect(url_for('resources'))
            
        if new_used > new_alloc:
            msg = f"Used Quantity ({new_used}) cannot exceed Allocated Quantity ({new_alloc})."
            if is_ajax: return jsonify({'success': False, 'message': msg}), 400
            flash(msg, "danger")
            return redirect(url_for('resources'))
            
        if new_avail - new_alloc - new_used < 0:
            msg = f"Remaining Quantity cannot be negative. Total allocated ({new_alloc}) and used ({new_used}) exceed available ({new_avail})."
            if is_ajax: return jsonify({'success': False, 'message': msg}), 400
            flash(msg, "danger")
            return redirect(url_for('resources'))
            
        res.name = new_name
        res.category = new_category
        res.quantity_available = new_avail
        res.quantity_allocated = new_alloc
        res.quantity_used = new_used
        
        db.session.commit()
        db.session.refresh(res)
        
        msg = "Resource inventory details updated successfully."
        if is_ajax:
            return jsonify({
                'success': True,
                'message': msg,
                'resource': {
                    'id': res.id,
                    'name': res.name,
                    'category': res.category,
                    'quantity_available': res.quantity_available,
                    'quantity_allocated': res.quantity_allocated,
                    'quantity_used': res.quantity_used,
                    'remaining_quantity': res.remaining_quantity
                }
            })
            
        flash(msg, "success")
    except Exception as e:
        db.session.rollback()
        msg = f"Error updating resource: {str(e)}"
        if is_ajax: return jsonify({'success': False, 'message': msg}), 500
        flash(msg, "danger")
        
    return redirect(url_for('resources'))

@app.route('/resources/delete/<int:id>', methods=['POST'])
@login_required
@manager_required
def delete_resource(id):
    if current_user.role != 'admin':
        abort(403)
        
    try:
        res = Resource.query.get_or_404(id)
        db.session.delete(res)
        db.session.commit()
        flash("Resource successfully deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting resource: {str(e)}", "danger")
        
    return redirect(url_for('resources'))

@app.route('/resources/allocate/<int:event_id>', methods=['POST'])
@login_required
@manager_required
def allocate_resource_event(event_id):
    if current_user.role != 'admin':
        abort(403)
        
    try:
        resource_id = int(request.form.get('resource_id', 0))
        qty_alloc = int(request.form.get('quantity_allocated', 0))
        
        if qty_alloc <= 0:
            flash("Allocation quantity must be a positive integer.", "danger")
            return redirect(url_for('event_details', id=event_id))
            
        res = Resource.query.get_or_404(resource_id)
        
        if qty_alloc > res.remaining_quantity:
            flash("Cannot allocate more than available quantity.", "danger")
            return redirect(url_for('event_details', id=event_id))
            
        allocator_name = current_user.volunteer.full_name if (current_user.is_authenticated and current_user.volunteer and current_user.volunteer.full_name) else "Admin"
        
        alloc = ResourceAllocation.query.filter_by(event_id=event_id, resource_id=resource_id).first()
        if alloc:
            alloc.quantity_allocated += qty_alloc
            alloc.allocated_by = allocator_name
            alloc.allocated_at = datetime.utcnow()
        else:
            alloc = ResourceAllocation(
                event_id=event_id,
                resource_id=resource_id,
                quantity_allocated=qty_alloc,
                quantity_used=0,
                allocated_by=allocator_name,
                allocated_at=datetime.utcnow()
            )
            db.session.add(alloc)
            
        res.quantity_allocated += qty_alloc
        db.session.commit()
        
        sync_resource_totals(res)
        db.session.commit()
        
        flash(f"Allocated {qty_alloc} units of {res.name} to event.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error allocating resource: {str(e)}", "danger")
        
    return redirect(url_for('event_details', id=event_id))

@app.route('/resources/update-usage/<int:alloc_id>', methods=['POST'])
@login_required
@manager_required
def update_allocation_usage(alloc_id):
    if current_user.role != 'admin':
        abort(403)
        
    try:
        alloc = ResourceAllocation.query.get_or_404(alloc_id)
        qty_used_new = int(request.form.get('quantity_used', 0))
        
        if qty_used_new < 0:
            flash("Used quantity cannot be negative.", "danger")
            return redirect(url_for('event_details', id=alloc.event_id))
            
        if qty_used_new > alloc.quantity_allocated:
            flash("Used quantity cannot exceed allocated quantity.", "danger")
            return redirect(url_for('event_details', id=alloc.event_id))
            
        diff = qty_used_new - alloc.quantity_used
        alloc.quantity_used = qty_used_new
        
        res = alloc.resource
        res.quantity_used += diff
        db.session.commit()
        
        sync_resource_totals(res)
        db.session.commit()
        
        flash(f"Resource usage updated: {qty_used_new} consumed.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating resource usage: {str(e)}", "danger")
        
    return redirect(url_for('event_details', id=alloc.event_id))

@app.route('/resources/delete-alloc/<int:id>', methods=['POST'])
@login_required
@manager_required
def delete_allocation(id):
    if current_user.role != 'admin':
        abort(403)
        
    try:
        alloc = ResourceAllocation.query.get_or_404(id)
        event_id = alloc.event_id
        res = alloc.resource
        
        res.quantity_allocated -= alloc.quantity_allocated
        res.quantity_used -= alloc.quantity_used
        
        db.session.delete(alloc)
        db.session.commit()
        
        sync_resource_totals(res)
        db.session.commit()
        
        flash("Resource allocation removed and inventory refunded.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting allocation: {str(e)}", "danger")
        
    return redirect(url_for('event_details', id=event_id))


# --- DONATIONS MODULE (CRUD) ---
@app.route('/donations', methods=['GET'])
@login_required
@manager_required
def donations():
    search_query = request.args.get('search', '')
    method_filter = request.args.get('method', '')
    
    query = Donation.query
    if search_query:
        query = query.filter(
            (Donation.donor_name.like(f"%{search_query}%")) |
            (Donation.email.like(f"%{search_query}%")) |
            (Donation.purpose.like(f"%{search_query}%"))
        )
    if method_filter:
        query = query.filter_by(payment_method=method_filter)
        
    donations_list = query.order_by(Donation.donation_date.desc()).all()
    form = DonationForm()
    
    # Metrics
    total_amount = db.session.query(db.func.sum(Donation.amount)).scalar() or 0.0
    avg_donation = total_amount / len(donations_list) if donations_list else 0.0
    
    # Month calculation (current month)
    curr_month = datetime.utcnow().date().replace(day=1)
    monthly_total = db.session.query(db.func.sum(Donation.amount)).filter(Donation.donation_date >= curr_month).scalar() or 0.0
    
    # Chart trends last 6 months
    trend_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
    trend_values = [total_amount * 0.1, total_amount * 0.15, total_amount * 0.12, total_amount * 0.2, total_amount * 0.18, total_amount * 0.25]
    
    # Payment method splits
    pay_methods = db.session.query(Donation.payment_method, db.func.count(Donation.id)).group_by(Donation.payment_method).all()
    payment_labels = [p[0] for p in pay_methods]
    payment_values = [p[1] for p in pay_methods]
    
    return render_template(
        'donations.html',
        donations_list=donations_list,
        form=form,
        total_amount=total_amount,
        monthly_total=monthly_total,
        avg_donation=avg_donation,
        trend_labels=trend_labels,
        trend_values=trend_values,
        payment_labels=payment_labels,
        payment_values=payment_values,
        search_query=search_query,
        method_filter=method_filter,
        active_page='donations'
    )

@app.route('/donations/add', methods=['POST'])
@login_required
@manager_required
def add_donation():
    form = DonationForm()
    if form.validate_on_submit():
        don = Donation(
            donor_name=form.donor_name.data,
            phone_number=form.phone_number.data,
            email=form.email.data,
            amount=form.amount.data,
            donation_date=form.donation_date.data,
            payment_method=form.payment_method.data,
            purpose=form.purpose.data
        )
        db.session.add(don)
        db.session.commit()
        flash(f"Donation of {format_currency_inr(don.amount)} from {don.donor_name} logged.", "success")
    else:
        for field, errors in form.errors.items():
            for err in errors:
                flash(f"Error in {field}: {err}", "danger")
                
    return redirect(url_for('donations'))

@app.route('/donations/edit/<int:id>', methods=['POST'])
@login_required
@manager_required
def edit_donation(id):
    if current_user.role != 'admin':
        abort(403)
        
    don = Donation.query.get_or_404(id)
    phone_number = request.form.get('phone_number', '').strip()
    import re
    err = None
    if not phone_number.isdigit():
        if not re.match(r'^\d+$', phone_number):
            err = "Only numbers are allowed."
    if not err and len(phone_number) < 10:
        err = "Mobile number must contain exactly 10 digits."
    if not err and len(phone_number) > 10:
        err = "Mobile number cannot exceed 10 digits."
    if not err and not re.match(r'^[6-9][0-9]{9}$', phone_number):
        err = "Enter a valid 10-digit Indian mobile number."
        
    if err:
        flash(f"Error: {err}", "danger")
        return redirect(url_for('donations'))

    don.donor_name = request.form.get('donor_name')
    don.email = request.form.get('email')
    don.phone_number = phone_number
    don.amount = float(request.form.get('amount'))
    don.payment_method = request.form.get('payment_method')
    don.purpose = request.form.get('purpose')
    
    date_str = request.form.get('donation_date')
    if date_str:
        req_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        import pytz
        kolkata_tz = pytz.timezone('Asia/Kolkata')
        today_kolkata = datetime.now(kolkata_tz).date()
        if req_date > today_kolkata:
            flash("Error: Donation date cannot be in the future.", "danger")
            return redirect(url_for('donations'))
        don.donation_date = req_date
        
    db.session.commit()
    db.session.refresh(don)
    flash("Donation record updated successfully.", "success")
    return redirect(url_for('donations'))

@app.route('/donations/delete/<int:id>', methods=['POST'])
@login_required
@manager_required
def delete_donation(id):
    if current_user.role != 'admin':
        abort(403)
        
    don = Donation.query.get_or_404(id)
    db.session.delete(don)
    db.session.commit()
    flash("Donation receipt deleted.", "success")
    return redirect(url_for('donations'))


# --- ATTENDANCE SYSTEM ---
@app.route('/attendance')
@login_required
def attendance():
    if current_user.role == 'admin':
        events_list = Event.query.all()
        events_attendance = []
        for ev in events_list:
            assigned = VolunteerApplication.query.filter(
                VolunteerApplication.event_id == ev.id,
                VolunteerApplication.status.in_(['Applied', 'Approved'])
            ).count()
            present = Attendance.query.filter_by(event_id=ev.id, status='Present').count()
            rate = (present / assigned * 100) if assigned > 0 else 0.0
            events_attendance.append({
                'event': ev,
                'assigned': assigned,
                'present': present,
                'rate': rate
            })
            
        total_registered = VolunteerApplication.query.filter(
            VolunteerApplication.status.in_(['Applied', 'Approved'])
        ).count()
        total_checked_in = Attendance.query.filter_by(status='Present').count()
        pending = total_registered - total_checked_in
        if pending < 0:
            pending = 0
        attendance_pct = (total_checked_in / total_registered * 100) if total_registered > 0 else 0.0
        
        recent_checkins = Attendance.query.order_by(Attendance.timestamp.desc()).limit(10).all()
        volunteers_list = Volunteer.query.all()
        
        return render_template(
            'attendance.html',
            events_attendance=events_attendance,
            events=events_list,
            volunteers=volunteers_list,
            total_registered=total_registered,
            total_checked_in=total_checked_in,
            pending=pending,
            attendance_pct=attendance_pct,
            recent_checkins=recent_checkins,
            active_page='attendance'
        )
    else:
        # Volunteer View: Attendance History Dashboard
        vol = current_user.volunteer
        checkin_history = Attendance.query.filter_by(volunteer_id=vol.id).order_by(Attendance.timestamp.desc()).all()
        total_attended = Attendance.query.filter_by(volunteer_id=vol.id, status='Present').count()
        return render_template('attendance.html', checkin_history=checkin_history, total_attended=total_attended, active_page='attendance')

@app.route('/attendance/generate-qr/<int:event_id>')
@login_required
@manager_required
def generate_qr_json(event_id):
    """AJAX endpoint serving Base64 QR code image and external LAN URL"""
    event = Event.query.get_or_404(event_id)
    qr = qrcode.QRCode(version=1, box_size=8, border=3)
    qr_url = get_external_attendance_url(event.id)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return jsonify({'success': True, 'qr_code': qr_base64, 'qr_url': qr_url})

@app.route('/attendance/print-qr/<int:event_id>')
@login_required
@manager_required
def print_qr_view(event_id):
    """Clean printable sheet layout for Event QR"""
    event = Event.query.get_or_404(event_id)
    qr = qrcode.QRCode(version=1, box_size=12, border=3)
    qr_url = get_external_attendance_url(event.id)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    html = f"""
    <html>
    <head><title>Print QR Check-In - {event.name}</title></head>
    <body style="text-align: center; font-family: sans-serif; padding-top: 60px;">
        <h2>NGO CONNECT CHECK-IN SHEET</h2>
        <h1>{event.name}</h1>
        <h3>Venue: {event.venue} | Date: {event.date}</h3>
        <img src="data:image/png;base64,{qr_base64}" style="border: 2px solid #000; padding: 20px; margin: 20px;"><br/>
        <div style="font-family: monospace; font-size: 1.1em; margin-bottom: 20px; color: #333; word-break: break-all;">
            <strong>Attendance Link:</strong> <a href="{qr_url}" target="_blank">{qr_url}</a>
        </div>
        <p style="font-size: 1.1em;">Scan with your mobile phone camera to register check-in instantly.</p>
        <button onclick="window.print()" style="padding: 10px 20px; font-size: 1.1em; cursor: pointer; margin-top: 20px;">Print Page</button>
    </body>
    </html>
    """
    return html

@app.route('/attendance/scan/<int:event_id>', methods=['GET', 'POST'])
def scan_attendance(event_id):
    """Verify and record check-in publicly without login"""
    event = Event.query.get(event_id)
    if not event:
        return render_template('public_checkin.html', error="Invalid QR Code.", event=None)
        
    if event.status == 'Closed':
        return render_template('public_checkin.html', error="Event is not active.", event=event)
        
    if request.method == 'GET':
        return render_template(
            'public_checkin.html',
            event=event,
            success=False
        )
        
    # POST Request - Process Mark Attendance
    volunteer_code = request.form.get('volunteer_code', '').strip()
    mobile_number = request.form.get('mobile_number', '').strip()
    
    vol = None
    if volunteer_code:
        digits = "".join([c for c in volunteer_code if c.isdigit()])
        if digits:
            try:
                vol = Volunteer.query.get(int(digits))
            except Exception:
                pass
                
    if not vol:
        return render_template(
            'public_checkin.html',
            event=event,
            error="Volunteer not found.",
            success=False
        )
        
    import re
    err = None
    if not mobile_number.isdigit():
        if not re.match(r'^\d+$', mobile_number):
            err = "Only numbers are allowed."
    if not err and len(mobile_number) < 10:
        err = "Mobile number must contain exactly 10 digits."
    if not err and len(mobile_number) > 10:
        err = "Mobile number cannot exceed 10 digits."
    if not err and not re.match(r'^[6-9][0-9]{9}$', mobile_number):
        err = "Enter a valid 10-digit Indian mobile number."
        
    if err:
        return render_template(
            'public_checkin.html',
            event=event,
            error=err,
            success=False
        )
        
    clean_entered = "".join([c for c in mobile_number if c.isdigit()])
    clean_db = "".join([c for c in (vol.mobile_number or "") if c.isdigit()])
    if clean_entered != clean_db:
        return render_template(
            'public_checkin.html',
            event=event,
            error="Mobile number does not match.",
            success=False
        )
        
    app_ticket = VolunteerApplication.query.filter(
        VolunteerApplication.event_id == event_id,
        VolunteerApplication.volunteer_id == vol.id,
        VolunteerApplication.status.in_(['Applied', 'Approved'])
    ).first()
    if not app_ticket:
        return render_template(
            'public_checkin.html',
            event=event,
            error="Volunteer is not registered for this event.",
            success=False
        )
        
    existing = Attendance.query.filter_by(event_id=event_id, volunteer_id=vol.id, status='Present').first()
    if existing:
        return render_template(
            'public_checkin.html',
            event=event,
            error="Attendance already marked.",
            success=False
        )
        
    checkin_time = datetime.utcnow()
    
    user_agent = request.headers.get('User-Agent', '').lower()
    if 'mobile' in user_agent or 'android' in user_agent or 'iphone' in user_agent:
        device_info = 'Mobile'
    elif 'tablet' in user_agent or 'ipad' in user_agent:
        device_info = 'Tablet'
    else:
        device_info = 'Desktop'
        
    ip_address = request.remote_addr or '127.0.0.1'
    if request.headers.get('X-Forwarded-For'):
        ip_address = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        
    att = Attendance(
        volunteer_id=vol.id,
        event_id=event_id,
        date=event.date,
        status='Present',
        marked_by='QR Code',
        timestamp=checkin_time,
        ip_address=ip_address,
        device_info=device_info
    )
    db.session.add(att)
    vol.participation_count += 1
    db.session.commit()
    
    if vol.user_id:
        create_notification(
            user_id=vol.user_id,
            title="Check-In Recorded",
            message=f"Attendance check-in logged via QR Code for event '{event.name}'.",
            notification_type="Attendance"
        )
        
    return render_template(
        'public_checkin.html',
        event=event,
        success=True,
        volunteer_name=vol.full_name,
        volunteer_id=vol.id,
        checkin_time=format_full_attendance_date(checkin_time)
    )


@app.route('/attendance/mock-scan', methods=['POST'])
@login_required
def mock_scan_attendance():
    """Fallback simulator route to log attendance without actual camera"""
    if current_user.role != 'volunteer':
        abort(403)
        
    event_id = int(request.form.get('event_id'))
    return redirect(url_for('scan_attendance', event_id=event_id))

@app.route('/attendance/mark-manual/<int:event_id>/<int:volunteer_id>', methods=['POST'])
@login_required
@manager_required
def mark_attendance_manual(event_id, volunteer_id):
    if current_user.role != 'admin':
        abort(403)
        
    new_status = request.form.get('status')
    
    att = Attendance.query.filter_by(event_id=event_id, volunteer_id=volunteer_id).first()
    vol = Volunteer.query.get(volunteer_id)
    
    if att:
        if att.status != new_status:
            att.status = new_status
            att.timestamp = datetime.utcnow()
            
            # Recalculate participation count
            if new_status == 'Present':
                vol.participation_count += 1
            else:
                vol.participation_count = max(0, vol.participation_count - 1)
    else:
        att = Attendance(
            volunteer_id=volunteer_id,
            event_id=event_id,
            date=Event.query.get(event_id).date,
            status=new_status,
            marked_by='Manual'
        )
        db.session.add(att)
        if new_status == 'Present':
            vol.participation_count += 1
            
    db.session.commit()
    
    # Notify volunteer
    create_notification(
        user_id=vol.user_id,
        title="Attendance Status Updated",
        message=f"Your attendance for event '{att.event.name}' has been updated to '{new_status}' by administration.",
        notification_type="Attendance"
    )
    
    flash(f"Attendance checks updated for {vol.full_name}.", "success")
    return redirect(url_for('event_details', id=event_id))

@app.route('/attendance/api/stats')
@login_required
@manager_required
def attendance_api_stats():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
    event_id = request.args.get('event_id')
    
    if event_id and event_id != "":
        total_registered = VolunteerApplication.query.filter(
            VolunteerApplication.event_id == int(event_id),
            VolunteerApplication.status.in_(['Applied', 'Approved'])
        ).count()
        total_checked_in = Attendance.query.filter_by(event_id=int(event_id), status='Present').count()
        recent_records = Attendance.query.filter_by(event_id=int(event_id)).order_by(Attendance.timestamp.desc()).limit(5).all()
        
        five_secs_ago = datetime.utcnow() - timedelta(seconds=5)
        newest = Attendance.query.filter(
            Attendance.event_id == int(event_id),
            Attendance.timestamp >= five_secs_ago
        ).order_by(Attendance.timestamp.desc()).first()
    else:
        total_registered = VolunteerApplication.query.filter(
            VolunteerApplication.status.in_(['Applied', 'Approved'])
        ).count()
        total_checked_in = Attendance.query.filter_by(status='Present').count()
        recent_records = Attendance.query.order_by(Attendance.timestamp.desc()).limit(5).all()
        
        five_secs_ago = datetime.utcnow() - timedelta(seconds=5)
        newest = Attendance.query.filter(Attendance.timestamp >= five_secs_ago).order_by(Attendance.timestamp.desc()).first()
        
    pending = total_registered - total_checked_in
    if pending < 0:
        pending = 0
    attendance_pct = (total_checked_in / total_registered * 100) if total_registered > 0 else 0.0
    
    recent_list = []
    for r in recent_records:
        recent_list.append({
            'volunteer_name': r.volunteer.full_name,
            'time': format_full_attendance_date(r.timestamp),
            'event_name': r.event.name
        })
        
    live_alert = None
    if newest:
        live_alert = f"🔔 {newest.volunteer.full_name} checked in."
        
    return jsonify({
        'success': True,
        'registered': total_registered,
        'checked_in': total_checked_in,
        'pending': pending,
        'percentage': round(attendance_pct, 1),
        'recent': recent_list,
        'live_alert': live_alert
    })

@app.route('/attendance/api/logs')
@login_required
@manager_required
def attendance_api_logs():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
    search = request.args.get('search', '').strip()
    event_id = request.args.get('event_id')
    date_val = request.args.get('date')
    status_val = request.args.get('status')
    sort_val = request.args.get('sort', 'desc')
    
    query = Attendance.query.join(Volunteer).join(Event)
    
    if search:
        query = query.filter(
            (Volunteer.full_name.like(f"%{search}%")) |
            (Volunteer.id.like(f"%{search}%"))
        )
    if event_id:
        query = query.filter(Attendance.event_id == int(event_id))
    if date_val:
        try:
            q_date = datetime.strptime(date_val, '%Y-%m-%d').date()
            query = query.filter(Attendance.date == q_date)
        except ValueError:
            pass
    if status_val:
        query = query.filter(Attendance.status == status_val)
        
    if sort_val == 'asc':
        query = query.order_by(Attendance.timestamp.asc())
    else:
        query = query.order_by(Attendance.timestamp.desc())
        
    logs = query.all()
    
    logs_list = []
    for l in logs:
        logs_list.append({
            'volunteer_name': l.volunteer.full_name,
            'volunteer_id': f"VOL-{l.volunteer.id:04d}",
            'event_name': l.event.name,
            'event_date': l.event.date.strftime('%Y-%m-%d'),
            'check_in_time': format_full_attendance_date(l.timestamp),
            'status': l.status,
            'ip_address': l.ip_address or '127.0.0.1',
            'device_info': l.device_info or 'Desktop',
            'created_at': format_ist(l.created_at) if l.created_at else format_ist(l.timestamp)
        })
        
    return jsonify({'success': True, 'logs': logs_list})

@app.route('/attendance/api/analytics')
@login_required
@manager_required
def attendance_api_analytics():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
    event_id = request.args.get('event_id')
    
    if event_id and event_id != "":
        present_count = Attendance.query.filter_by(event_id=int(event_id), status='Present').count()
        registered_count = VolunteerApplication.query.filter(
            VolunteerApplication.event_id == int(event_id),
            VolunteerApplication.status.in_(['Applied', 'Approved'])
        ).count()
        absent_count = max(0, registered_count - present_count)
        
        trend_labels = ['Present', 'Absent']
        trend_values = [present_count, absent_count]
        
        ev = Event.query.get(int(event_id))
        event_month = ev.date.strftime('%b') if ev else 'N/A'
        monthly_labels = [event_month]
        monthly_values = [present_count]
        
        total_checked = present_count
        total_pending = absent_count
        
        active_vols = db.session.query(
            Volunteer.full_name,
            db.func.count(Attendance.id)
        ).join(Attendance).filter(Attendance.event_id == int(event_id)).group_by(Volunteer.id).all()
        
        vol_labels = [v[0] for v in active_vols]
        vol_values = [v[1] for v in active_vols]
    else:
        events = Event.query.all()
        trend_labels = []
        trend_values = []
        for ev in events[-10:]:
            trend_labels.append(ev.name[:15] + "...")
            checked = Attendance.query.filter_by(event_id=ev.id, status='Present').count()
            trend_values.append(checked)
            
        monthly_data = db.session.query(
            db.func.strftime('%m', Attendance.timestamp),
            db.func.count(Attendance.id)
        ).group_by(db.func.strftime('%m', Attendance.timestamp)).all()
        
        month_names = {
            '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr', '05': 'May', '06': 'Jun',
            '07': 'Jul', '08': 'Aug', '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
        }
        monthly_labels = []
        monthly_values = []
        for m, c in monthly_data:
            monthly_labels.append(month_names.get(m, m))
            monthly_values.append(c)
            
        if not monthly_labels:
            monthly_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
            monthly_values = [0, 0, 0, 0, 0, 0]
            
        total_reg = VolunteerApplication.query.filter(
            VolunteerApplication.status.in_(['Applied', 'Approved'])
        ).count()
        total_checked = Attendance.query.filter_by(status='Present').count()
        total_pending = total_reg - total_checked
        if total_pending < 0:
            total_pending = 0
            
        active_vols = db.session.query(
            Volunteer.full_name,
            db.func.count(Attendance.id)
        ).join(Attendance).group_by(Volunteer.id).order_by(db.func.count(Attendance.id).desc()).limit(5).all()
        
        vol_labels = [v[0] for v in active_vols]
        vol_values = [v[1] for v in active_vols]
        
    return jsonify({
        'success': True,
        'trend_labels': trend_labels,
        'trend_values': trend_values,
        'monthly_labels': monthly_labels,
        'monthly_values': monthly_values,
        'participation': [total_checked, total_pending],
        'vol_labels': vol_labels,
        'vol_values': vol_values
    })

@app.route('/attendance/report/export')
@login_required
@manager_required
def export_attendance_report():
    if current_user.role != 'admin':
        abort(403)
        
    report_type = request.args.get('report_type')
    fmt = request.args.get('format', 'csv')
    
    query = Attendance.query.join(Volunteer).join(Event)
    
    title = "Attendance Report"
    if report_type == 'event':
        event_id = request.args.get('event_id')
        if event_id:
            query = query.filter(Attendance.event_id == int(event_id))
            ev = Event.query.get(event_id)
            title = f"Attendance Report - {ev.name}"
    elif report_type == 'volunteer':
        volunteer_id = request.args.get('volunteer_id')
        if volunteer_id:
            query = query.filter(Attendance.volunteer_id == int(volunteer_id))
            vol = Volunteer.query.get(volunteer_id)
            title = f"Attendance Report - {vol.full_name}"
    elif report_type == 'monthly':
        month_str = request.args.get('month')
        if month_str:
            try:
                parts = month_str.split('-')
                year = int(parts[0])
                month = int(parts[1])
                query = query.filter(
                    db.func.strftime('%Y', Attendance.timestamp) == str(year),
                    db.func.strftime('%m', Attendance.timestamp) == f"{month:02d}"
                )
                title = f"Attendance Report - {month_str}"
            except Exception:
                pass
                
    logs = query.all()
    
    if fmt == 'csv' or fmt == 'excel':
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Volunteer Name", "Volunteer ID", "Event Name", "Event Date", 
            "Check-In Time", "Attendance Status", "IP Address", "Device Type", "Created At"
        ])
        for l in logs:
            writer.writerow([
                l.volunteer.full_name,
                f"VOL-{l.volunteer.id:04d}",
                l.event.name,
                l.event.date.strftime('%Y-%m-%d'),
                format_full_attendance_date(l.timestamp),
                l.status,
                l.ip_address or '127.0.0.1',
                l.device_info or 'Desktop',
                format_ist(l.created_at) if l.created_at else ''
            ])
        output.seek(0)
        filename = f"{report_type}_report_{int(datetime.utcnow().timestamp())}.csv"
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    elif fmt == 'pdf':
        rows_data = []
        for l in logs:
            rows_data.append([
                l.volunteer.full_name,
                f"VOL-{l.volunteer.id:04d}",
                l.event.name,
                l.event.date.strftime('%Y-%m-%d'),
                format_full_attendance_date(l.timestamp),
                l.status,
                l.ip_address or '127.0.0.1',
                l.device_info or 'Desktop'
            ])
        filename = f"{report_type}_report_{int(datetime.utcnow().timestamp())}.pdf"
        file_path = generate_report_pdf(
            title,
            ["Volunteer Name", "Volunteer ID", "Event Name", "Event Date", "Time", "Status", "IP", "Device"],
            rows_data,
            filename
        )
        return send_file(file_path, as_attachment=True, download_name=filename)
    else:
        abort(400)



# --- CERTIFICATES GENERATION ---
@app.route('/certificates')
@login_required
@volunteer_required
def certificates():
    if current_user.role == 'admin':
        certificates_list = Certificate.query.order_by(Certificate.issue_date.desc()).all()
    else:
        vol = current_user.volunteer
        certificates_list = Certificate.query.filter_by(volunteer_id=vol.id).order_by(Certificate.issue_date.desc()).all()
        
    return render_template('certificates.html', certificates_list=certificates_list, active_page='certificates')

@app.route('/certificates/generate/<int:event_id>/<int:volunteer_id>', methods=['POST'])
@login_required
@manager_required
def generate_certificate_route(event_id, volunteer_id):
    if current_user.role != 'admin':
        abort(403)
        
    vol = Volunteer.query.get_or_404(volunteer_id)
    event = Event.query.get_or_404(event_id)
    
    # Verify attendance is marked present
    att = Attendance.query.filter_by(event_id=event_id, volunteer_id=volunteer_id, status='Present').first()
    if not att:
        flash("Cannot generate certificate: Volunteer is not marked as Present.", "danger")
        return redirect(url_for('event_details', id=event_id))
        
    # Check duplicate
    existing = Certificate.query.filter_by(event_id=event_id, volunteer_id=volunteer_id).first()
    if existing:
        flash("Certificate has already been issued.", "info")
        return redirect(url_for('event_details', id=event_id))
        
    cert_number = f"CERT-{datetime.utcnow().year}-{random.randint(100000, 999999)}"
    
    # Generate the actual PDF file
    file_path = generate_certificate_pdf(vol, event, cert_number)
    
    cert = Certificate(
        volunteer_id=volunteer_id,
        event_id=event_id,
        certificate_number=cert_number,
        file_path=os.path.basename(file_path)
    )
    db.session.add(cert)
    db.session.commit()
    
    # Notify volunteer
    create_notification(
        user_id=vol.user_id,
        title="Certificate Issued!",
        message=f"Congratulations! You received a certificate for attending '{event.name}'.",
        notification_type="Certificate"
    )
    
    flash("Certificate created and issued to volunteer.", "success")
    return redirect(url_for('event_details', id=event_id))

@app.route('/certificates/download/<int:id>')
@login_required
def download_certificate(id):
    cert = Certificate.query.get_or_404(id)
    
    # Security check: volunteers can only download their own certificates
    if current_user.role == 'volunteer' and cert.volunteer_id != current_user.volunteer.id:
        abort(403)
        
    full_path = os.path.join(app.config['CERTIFICATE_FOLDER'], cert.file_path)
    if os.path.exists(full_path):
        return send_file(full_path, as_attachment=True, download_name=cert.file_path)
    else:
        # Re-generate if deleted
        event = Event.query.get(cert.event_id)
        vol = Volunteer.query.get(cert.volunteer_id)
        generate_certificate_pdf(vol, event, cert.certificate_number)
        return send_file(full_path, as_attachment=True, download_name=cert.file_path)

@app.route('/certificates/delete/<int:id>', methods=['POST'])
@login_required
@manager_required
def delete_certificate(id):
    if current_user.role != 'admin':
        abort(403)
        
    cert = Certificate.query.get_or_404(id)
    full_path = os.path.join(app.config['CERTIFICATE_FOLDER'], cert.file_path)
    
    # Delete file
    if os.path.exists(full_path):
        try:
            os.remove(full_path)
        except Exception:
            pass
            
    db.session.delete(cert)
    db.session.commit()
    
    flash("Certificate entry deleted.", "success")
    return redirect(url_for('certificates'))


# --- EXPORTS & REPORTS ---
@app.route('/reports')
@login_required
@manager_required
def reports():
    if current_user.role != 'admin':
        abort(403)
        
    events_list = Event.query.all()
    return render_template('reports.html', events_list=events_list, active_page='reports')

@app.route('/reports/export-event/<int:event_id>')
@login_required
@manager_required
def export_event_report(event_id):
    """Specific event summary report export route"""
    if current_user.role != 'admin':
        abort(403)
        
    event = Event.query.get_or_404(event_id)
    assigned_apps = VolunteerApplication.query.filter_by(event_id=event.id, status='Approved').all()
    
    headers = ['VOL_ID', 'NAME', 'EMAIL', 'MOBILE', 'GENDER', 'ATTENDANCE']
    data = []
    
    for app_ticket in assigned_apps:
        att = Attendance.query.filter_by(event_id=event.id, volunteer_id=app_ticket.volunteer_id).first()
        att_status = att.status if att else 'Absent'
        data.append([
            f"VOL-{app_ticket.volunteer_id:04d}",
            app_ticket.volunteer.full_name,
            app_ticket.volunteer.email,
            app_ticket.volunteer.mobile_number,
            app_ticket.volunteer.gender,
            att_status
        ])
        
    filename = f"event_roster_{event.id}.pdf"
    file_path = generate_report_pdf(f"NGO Event Roster: {event.name}", headers, data, filename)
    return send_file(file_path, as_attachment=True, download_name=filename)

@app.route('/reports/export/<string:report_type>')
@login_required
@manager_required
def export_report(report_type):
    if current_user.role != 'admin':
        abort(403)
        
    fmt = request.args.get('format', 'pdf')
    
    headers = []
    data = []
    title = ""
    filename = f"{report_type}_report"
    
    # 1. VOLUNTEER PARTICIPATION
    if report_type == 'volunteer':
        title = "Volunteer Participation Audit Sheet"
        headers = ['Vol_ID', 'Full Name', 'Email', 'Mobile', 'Availability', 'Join Date', 'Participation Count']
        avail_filter = request.args.get('availability')
        
        query = Volunteer.query
        if avail_filter:
            query = query.filter_by(availability=avail_filter)
            
        for v in query.all():
            data.append([
                f"VOL-{v.id:04d}",
                v.full_name,
                v.email,
                v.mobile_number,
                v.availability,
                v.join_date.strftime('%Y-%m-%d'),
                str(v.participation_count)
            ])
            
    # 2. EVENT METRICS
    elif report_type == 'event':
        title = "NGO Events Master Report"
        headers = ['Event ID', 'Event Name', 'Category', 'Date', 'Venue', 'Required Vol', 'Assigned Vol', 'Status']
        cat_filter = request.args.get('category')
        
        query = Event.query
        if cat_filter:
            query = query.filter_by(category=cat_filter)
            
        for e in query.all():
            assigned = VolunteerApplication.query.filter_by(event_id=e.id, status='Approved').count()
            data.append([
                f"EV-{e.id:04d}",
                e.name,
                e.category,
                e.date.strftime('%Y-%m-%d'),
                e.venue,
                str(e.required_volunteers),
                str(assigned),
                e.status
            ])
            
    # 3. DONATIONS
    elif report_type == 'donation':
        title = "NGO Donation Log Book"
        headers = ['ID', 'Donor Name', 'Email', 'Amount', 'Date', 'Method', 'Purpose']
        start_str = request.args.get('start_date')
        end_str = request.args.get('end_date')
        
        query = Donation.query
        if start_str:
            query = query.filter(Donation.donation_date >= datetime.strptime(start_str, '%Y-%m-%d').date())
        if end_str:
            query = query.filter(Donation.donation_date <= datetime.strptime(end_str, '%Y-%m-%d').date())
            
        for d in query.all():
            data.append([
                f"DON-{d.id:04d}",
                d.donor_name,
                d.email,
                format_currency_inr(d.amount),
                d.donation_date.strftime('%Y-%m-%d'),
                d.payment_method,
                d.purpose or 'General'
            ])
            
    # 4. ATTENDANCE
    elif report_type == 'attendance':
        title = "Check-In Attendance Ledger"
        headers = ['Scan ID', 'Volunteer Name', 'Event Name', 'Event Date', 'Attendance Status', 'Verification Method', 'Timestamp']
        ev_id = request.args.get('event_id')
        
        query = Attendance.query
        if ev_id:
            query = query.filter_by(event_id=int(ev_id))
            
        for a in query.all():
            data.append([
                f"SCAN-{a.id:04d}",
                a.volunteer.full_name,
                a.event.name,
                a.event.date.strftime('%Y-%m-%d'),
                a.status,
                a.marked_by,
                format_full_attendance_date(a.timestamp)
            ])
            
    # 5. RESOURCE ALLOCATION
    elif report_type == 'resource':
        title = "NGO Resource Allocation & Stock Sheet"
        headers = ['Resource ID', 'Resource Name', 'Category', 'Available', 'Allocated', 'Used', 'Remaining']
        cat_filter = request.args.get('category')
        
        query = Resource.query
        if cat_filter:
            query = query.filter_by(category=cat_filter)
            
        for r in query.all():
            sync_resource_totals(r)
            data.append([
                f"RES-{r.id:04d}",
                r.name,
                r.category,
                str(r.quantity_available),
                str(r.quantity_allocated),
                str(r.quantity_used),
                str(r.remaining_quantity)
            ])
            
    # 6. MONTHLY NGO ACTIVITY
    elif report_type == 'activity':
        year = int(request.args.get('year', 2026))
        month = int(request.args.get('month', 6))
        title = f"Consolidated NGO Activity Report: {datetime(year, month, 1).strftime('%B %Y')}"
        headers = ['Parameter Metric', 'Monthly Count Summary']
        
        # Calculate monthly totals
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)
            
        new_vols = Volunteer.query.filter(Volunteer.join_date >= start_date, Volunteer.join_date <= end_date).count()
        new_events = Event.query.filter(Event.date >= start_date, Event.date <= end_date).count()
        dons_total = db.session.query(db.func.sum(Donation.amount)).filter(Donation.donation_date >= start_date, Donation.donation_date <= end_date).scalar() or 0.0
        att_presence = Attendance.query.filter(Attendance.date >= start_date, Attendance.date <= end_date, Attendance.status == 'Present').count()
        
        data = [
            ['New Volunteers Onboarded', str(new_vols)],
            ['Events Scheduled', str(new_events)],
            ['Monthly Funds Raised', format_currency_inr(dons_total)],
            ['Volunteer Check-Ins Verified', str(att_presence)]
        ]
        
    else:
        abort(400)
        
    # EXPORT AS PDF
    if fmt == 'pdf':
        filename_pdf = f"{filename}.pdf"
        file_path = generate_report_pdf(title, headers, data, filename_pdf)
        return send_file(file_path, as_attachment=True, download_name=filename_pdf)
        
    # EXPORT AS CSV
    else:
        si = io.StringIO()
        cw = csv.writer(si)
        cw.writerow(headers)
        cw.writerows(data)
        
        output = io.BytesIO()
        output.write(si.getvalue().encode('utf-8'))
        output.seek(0)
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f"{filename}.csv",
            mimetype='text/csv'
        )

# Notifications dropdown dynamic read-marker
@app.route('/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    unread_notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).all()
    for n in unread_notifs:
        n.is_read = True
    db.session.commit()
    return jsonify({'success': True})


# --- SEED DATA GENERATOR ---
def seed_database():
    """Initializes tables and populates required seed data"""
    db.create_all()
    
    # Correct any existing future donation dates
    import pytz
    kolkata_tz = pytz.timezone('Asia/Kolkata')
    today_kolkata = datetime.now(kolkata_tz).date()
    future_donations = Donation.query.filter(Donation.donation_date > today_kolkata).all()
    for d in future_donations:
        d.donation_date = today_kolkata
    if future_donations:
        db.session.commit()
        print(f"Corrected {len(future_donations)} future donation records.")

    # 1. Create Default Admin
    admin = User.query.filter_by(email="admin@ngo.com").first()
    if admin:
        print("Database already initialized. Skipping seeding.")
        return
        
    if not admin:
        admin = User(email="admin@ngo.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        
    # 2. Seed 10 Volunteers with diverse profiles
    vol_names = [
        ("Alice Smith", "Medical Camp", "Weekends", "Medical Camp, Healthcare, CPR, First Aid"),
        ("Bob Johnson", "Education", "Weekdays", "Teaching, Tutoring, Children"),
        ("Charlie Brown", "Disaster Relief", "All", "Logistics, Driving, Heavy Equipment"),
        ("Diana Prince", "Fundraising", "Evenings", "Social Media, Writing, Marketing"),
        ("Evan Wright", "Environment", "Weekends", "Planting, Gardening, Outdoors"),
        ("Fiona Gallagher", "Food Drive", "Weekdays", "Cooking, Food Service, Packing"),
        ("George Costanza", "Other", "Evenings", "Admin, Writing, Organizing"),
        ("Hannah Abbott", "Medical Camp", "Weekends", "Nursing, First Aid, Medicine"),
        ("Ian Malcolm", "Education", "Weekdays", "Math, Science, Mentoring"),
        ("Julia Roberts", "Fundraising", "All", "Outreach, Sales, Public Relations")
    ]
    
    skills_map = {
        "Medical Camp": "Medical Care, CPR, Nurse Assistant, Pharmacy",
        "Education": "English Tutor, Elementary Math, Child Counseling",
        "Disaster Relief": "Logistics Planning, Truck Driving, Heavy Lifting",
        "Fundraising": "Graphic Design, Copywriting, Event Planning",
        "Environment": "Horticulture, Gardening, Forest Conservation",
        "Food Drive": "Meal Preparation, Kitchen Sanitation, Supply Chain",
        "Other": "General Labor, Typing, Organizing Files"
    }
    
    for i, (name, interest, avail, skills) in enumerate(vol_names, 1):
        email = f"vol{i}@ngo.com"
        user = User(email=email, role="volunteer")
        user.set_password("volpass123") # Standard password for seeded vols
        
        # Calculate random DOB (between 18 and 50 years ago)
        dob = date(2026, 6, 21) - timedelta(days=365 * random.randint(18, 50) + random.randint(0, 360))
        
        vol = Volunteer(
            user=user,
            full_name=name,
            email=email,
            mobile_number=f"+1415555{1000 + i}",
            address=f"Street {i}, City Center, CA 94103",
            gender="Male" if i % 2 == 0 else "Female",
            date_of_birth=dob,
            skills=skills_map.get(interest, skills),
            interests=interest,
            availability=avail,
            join_date=date(2026, 1, 1) + timedelta(days=random.randint(1, 120)),
            participation_count=random.randint(1, 8)
        )
        db.session.add(user)
        db.session.add(vol)
        
    # 3. Seed 5 Events (varying dates and categories)
    events_seed = [
        Event(
            name="City Health & Medical Clinic",
            description="Free medical screening and prescription handouts for vulnerable families.",
            category="Medical Camp",
            date=date(2026, 7, 10),
            time=time(9, 0),
            venue="Downtown Community Hall",
            required_volunteers=4,
            status="Upcoming"
        ),
        Event(
            name="Feed the Homeless Kitchen",
            description="Preparing and packaging warm meals for community center delivery.",
            category="Food Drive",
            date=date(2026, 7, 18),
            time=time(8, 0),
            venue="St. Mary's Soup Kitchen",
            required_volunteers=5,
            status="Upcoming"
        ),
        Event(
            name="Tsunami Disaster Logistics Prep",
            description="Sorting first-aid supplies and blankets to box for emergency shipments.",
            category="Disaster Relief",
            date=date(2026, 7, 25),
            time=time(10, 0),
            venue="NGO Logistics Warehouse",
            required_volunteers=6,
            status="Upcoming"
        ),
        Event(
            name="Youth Reading & Mentorship Circle",
            description="Afternoon tutoring and library reading circles for grade-school pupils.",
            category="Education",
            date=date(2026, 6, 5),
            time=time(14, 30),
            venue="City Library Annex",
            required_volunteers=3,
            status="Completed"
        ),
        Event(
            name="Urban Reforestation Day",
            description="Planting local tree species along parkways and riverbanks.",
            category="Environment",
            date=date(2026, 5, 20),
            time=time(7, 30),
            venue="River Valley Trails",
            required_volunteers=8,
            status="Completed"
        )
    ]
    for ev in events_seed:
        db.session.add(ev)
    db.session.commit()
    
    # 4. Seed 10 Resources
    resources_seed = [
        Resource(name="First Aid Boxes", category="Medical Supplies", quantity_available=25),
        Resource(name="Paracetamol Tablets", category="Medical Supplies", quantity_available=500),
        Resource(name="Rice Bags (5kg)", category="Food", quantity_available=100),
        Resource(name="Cooking Cooking Oil (1L)", category="Food", quantity_available=80),
        Resource(name="Children's Storybooks", category="Books", quantity_available=150),
        Resource(name="Elementary Math Textbooks", category="Books", quantity_available=60),
        Resource(name="Woolen Blankets", category="Clothes", quantity_available=200),
        Resource(name="Winter Jackets", category="Clothes", quantity_available=75),
        Resource(name="Whiteboards", category="Equipment", quantity_available=5),
        Resource(name="Cardboard Packaging Boxes", category="Equipment", quantity_available=300)
    ]
    for res in resources_seed:
        db.session.add(res)
    db.session.commit()
    
    # Allocate some resources to completed events to verify maths
    past_event = Event.query.filter_by(name="Youth Reading & Mentorship Circle").first()
    if past_event:
        books_res = Resource.query.filter_by(name="Children's Storybooks").first()
        if books_res:
            alloc = ResourceAllocation(
                event_id=past_event.id,
                resource_id=books_res.id,
                quantity_allocated=20,
                quantity_used=18
            )
            db.session.add(alloc)
            books_res.quantity_allocated += 2
            books_res.quantity_used += 18
            
    db.session.commit()
    
    # 5. Seed 20 Donations
    donors = [
        ("Alice Cooper", "Card", 250.0, "Health Clinic"),
        ("Bruce Wayne", "Bank Transfer", 5000.0, "Logistics Warehouse"),
        ("Clark Kent", "Cash", 50.0, "General Fund"),
        ("Diana Prince", "Card", 300.0, "Youth Education"),
        ("Edward Elric", "Cheque", 1500.0, "Disaster Supplies"),
        ("Frank Castle", "UPI", 100.0, "Food drive"),
        ("Gwen Stacy", "Card", 75.0, "General Fund"),
        ("Harry Potter", "Cheque", 2000.0, "Educational Supplies"),
        ("Iris West", "Card", 120.0, "Medical Camp"),
        ("John Watson", "Bank Transfer", 450.0, "Medical Camp"),
        ("Katherine Pierce", "UPI", 500.0, "General Fund"),
        ("Lois Lane", "Card", 250.0, "Youth Education"),
        ("Matt Murdock", "Cash", 100.0, "General Fund"),
        ("Nathan Drake", "Bank Transfer", 1000.0, "Disaster Prep"),
        ("Oliver Queen", "Cheque", 3500.0, "Urban Forestry"),
        ("Peter Parker", "Cash", 20.0, "General Fund"),
        ("Quentin Beck", "UPI", 150.0, "General Fund"),
        ("Reed Richards", "Bank Transfer", 2500.0, "Medical Tech"),
        ("Steve Rogers", "Cash", 150.0, "General Fund"),
        ("Tony Stark", "Bank Transfer", 10000.0, "All Projects")
    ]
    
    for i, (name, method, amount, purpose) in enumerate(donors, 1):
        # Subtract some days to simulate last 3 months
        donation_date = date(2026, 6, 21) - timedelta(days=random.randint(1, 90))
        don = Donation(
            donor_name=name,
            phone_number=f"+1415555{9000 + i}",
            email=f"{name.lower().replace(' ', '')}@mail.com",
            amount=amount,
            donation_date=donation_date,
            payment_method=method,
            purpose=purpose
        )
        db.session.add(don)
        
    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        seed_database()
        
    print("Database tables initialized and Seed data generated successfully.")
    # Run the server
    app.run(debug=True, host='0.0.0.0', port=5000)

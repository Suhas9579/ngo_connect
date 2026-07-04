import unittest
import os
import sys

# Add project directory to sys.path
project_dir = r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform"
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from app import app, db, format_currency_inr, sync_resource_totals
from models import Resource, ResourceAllocation, Event, User, Volunteer, Donation, Attendance
from datetime import datetime

class TestNGOUpdates(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_indian_currency_formatting(self):
        self.assertEqual(format_currency_inr(5000), "₹5,000")
        self.assertEqual(format_currency_inr(10500), "₹10,500")
        self.assertEqual(format_currency_inr(125000), "₹1,25,000")
        self.assertEqual(format_currency_inr(10000000), "₹1,00,00,000")

    def test_resource_allocation_math_and_validation(self):
        # 1. Create Resource
        res = Resource(name="First Aid Kits", category="Medical Supplies", quantity_available=100, quantity_allocated=0, quantity_used=0)
        ev = Event(name="Health Camp", description="Desc", category="Medical Camp", date=datetime.utcnow().date(), time=datetime.utcnow().time(), venue="City Hall", required_volunteers=5)
        db.session.add(res)
        db.session.add(ev)
        db.session.commit()

        self.assertEqual(res.remaining_quantity, 100)

        # 2. Allocate 40 items
        alloc = ResourceAllocation(event_id=ev.id, resource_id=res.id, quantity_allocated=40, quantity_used=0, allocated_by="TestAdmin")
        db.session.add(alloc)
        db.session.flush()
        sync_resource_totals(res)
        db.session.commit()

        self.assertEqual(res.quantity_allocated, 40)
        self.assertEqual(res.quantity_used, 0)
        self.assertEqual(res.remaining_quantity, 60)

        # 3. Update usage to 15 items
        alloc.quantity_used = 15
        db.session.flush()
        sync_resource_totals(res)
        db.session.commit()

        self.assertEqual(res.quantity_allocated, 40)
        self.assertEqual(res.quantity_used, 15)
        self.assertEqual(res.remaining_quantity, 45)

        # 4. Check formula: Remaining = Available - Allocated - Used
        calculated_rem = res.quantity_available - res.quantity_allocated - res.quantity_used
        self.assertEqual(res.remaining_quantity, calculated_rem)

    def test_user_exact_example(self):
        # Before: Available = 150, Allocated = 0, Used = 0
        res = Resource(name="Storybooks", category="Books", quantity_available=150, quantity_allocated=0, quantity_used=0)
        ev = Event(name="Reading Camp", description="Desc", category="Education", date=datetime.utcnow().date(), time=datetime.utcnow().time(), venue="School", required_volunteers=3)
        db.session.add(res)
        db.session.add(ev)
        db.session.commit()

        self.assertEqual(res.quantity_available, 150)
        self.assertEqual(res.quantity_allocated, 0)
        self.assertEqual(res.quantity_used, 0)
        self.assertEqual(res.remaining_quantity, 150)

        # Allocate 20: Available = 150, Allocated = 20, Used = 0, Remaining = 130
        alloc = ResourceAllocation(event_id=ev.id, resource_id=res.id, quantity_allocated=20, quantity_used=0)
        db.session.add(alloc)
        res.quantity_allocated += 20
        db.session.commit()
        sync_resource_totals(res)
        db.session.commit()

        self.assertEqual(res.quantity_available, 150)
        self.assertEqual(res.quantity_allocated, 20)
        self.assertEqual(res.quantity_used, 0)
        self.assertEqual(res.remaining_quantity, 130)

        # Use 18: Available = 150, Allocated = 20, Used = 18, Remaining = 112
        alloc.quantity_used = 18
        res.quantity_used += 18
        db.session.commit()
        sync_resource_totals(res)
        db.session.commit()

        self.assertEqual(res.quantity_available, 150)
        self.assertEqual(res.quantity_allocated, 20)
        self.assertEqual(res.quantity_used, 18)
        self.assertEqual(res.remaining_quantity, 112)

    def test_transaction_rollback_on_failure(self):
        res = Resource(name="Blankets", category="Clothes", quantity_available=50)
        db.session.add(res)
        db.session.commit()

        try:
            db.session.begin_nested()
            res.quantity_available = -10 # invalid
            if res.quantity_available < 0:
                raise ValueError("Remaining quantity cannot be negative.")
            db.session.commit()
        except ValueError:
            db.session.rollback()

        # Refresh from DB
        db.session.refresh(res)
        self.assertEqual(res.quantity_available, 50)

    def test_public_checkin_flow_and_validations(self):
        from models import VolunteerApplication, Attendance
        # 1. Setup volunteer & event
        usr = User(email="bruce@wayne.com", role="volunteer")
        usr.set_password("pass123")
        db.session.add(usr)
        db.session.commit()
        
        vol = Volunteer(user_id=usr.id, full_name="Bruce Wayne", email="bruce@wayne.com", mobile_number="9876543210", gender="Male", date_of_birth=datetime.utcnow().date(), availability="All")
        ev = Event(name="Charity Gala", description="Fundraiser", category="Fundraising", date=datetime.utcnow().date(), time=datetime.utcnow().time(), venue="Wayne Manor", required_volunteers=5)
        db.session.add(vol)
        db.session.add(ev)
        db.session.commit()

        # 2. Test scan page GET loads successfully (GET is public, status code 200)
        client = app.test_client()
        resp = client.get(f"/attendance/scan/{ev.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Charity Gala", resp.data)

        # 3. Test POST mark attendance fails if volunteer is not registered (returns error)
        resp_post = client.post(f"/attendance/scan/{ev.id}", data={"volunteer_code": f"VOL-{vol.id}", "mobile_number": "9876543210"})
        self.assertEqual(resp_post.status_code, 200)
        self.assertIn(b"Volunteer is not registered for this event.", resp_post.data)

        # 4. Log in the volunteer user and apply to volunteer
        client.post('/login', data={'email': 'bruce@wayne.com', 'password': 'pass123'})
        resp_apply = client.post(f"/events/apply/{ev.id}", follow_redirects=True)
        self.assertEqual(resp_apply.status_code, 200)

        # 5. Check application was created with status 'Applied' and assigned_count updated
        db.session.expire_all()
        app_ticket = VolunteerApplication.query.filter_by(volunteer_id=vol.id, event_id=ev.id).first()
        self.assertIsNotNone(app_ticket)
        self.assertEqual(app_ticket.status, "Applied")
        self.assertEqual(ev.assigned_count, 1)

        # 6. Test scan page POST now succeeds
        resp_post_success = client.post(f"/attendance/scan/{ev.id}", data={"volunteer_code": f"VOL-{vol.id}", "mobile_number": "9876543210"})
        self.assertEqual(resp_post_success.status_code, 200)
        self.assertIn(b"Attendance Marked Successfully", resp_post_success.data)

        # 7. Check attendance count
        db.session.expire_all()
        att = Attendance.query.filter_by(volunteer_id=vol.id, event_id=ev.id).first()
        self.assertIsNotNone(att)
        self.assertEqual(att.status, "Present")

        # 8. Test duplicate submission (returns error)
        resp_post_dup = client.post(f"/attendance/scan/{ev.id}", data={"volunteer_code": f"VOL-{vol.id}", "mobile_number": "9876543210"})
        self.assertEqual(resp_post_dup.status_code, 200)
        self.assertIn(b"Attendance already marked.", resp_post_dup.data)

        # 8b. Test invalid volunteer ID
        resp_post_invalid_id = client.post(f"/attendance/scan/{ev.id}", data={"volunteer_code": "VOL-9999", "mobile_number": "9876543210"})
        self.assertEqual(resp_post_invalid_id.status_code, 200)
        self.assertIn(b"Volunteer not found.", resp_post_invalid_id.data)

        # 8c. Test mismatched mobile number
        resp_post_mismatch_mobile = client.post(f"/attendance/scan/{ev.id}", data={"volunteer_code": f"VOL-{vol.id}", "mobile_number": "9999999999"})
        self.assertEqual(resp_post_mismatch_mobile.status_code, 200)
        self.assertIn(b"Mobile number does not match.", resp_post_mismatch_mobile.data)

        # 8d. Test invalid mobile validations
        # Less than 10 digits
        resp_post_short_mobile = client.post(f"/attendance/scan/{ev.id}", data={"volunteer_code": f"VOL-{vol.id}", "mobile_number": "98765"})
        self.assertEqual(resp_post_short_mobile.status_code, 200)
        self.assertIn(b"Mobile number must contain exactly 10 digits.", resp_post_short_mobile.data)

        # More than 10 digits
        resp_post_long_mobile = client.post(f"/attendance/scan/{ev.id}", data={"volunteer_code": f"VOL-{vol.id}", "mobile_number": "98765432101"})
        self.assertEqual(resp_post_long_mobile.status_code, 200)
        self.assertIn(b"Mobile number cannot exceed 10 digits.", resp_post_long_mobile.data)

        # Non-numeric
        resp_post_char_mobile = client.post(f"/attendance/scan/{ev.id}", data={"volunteer_code": f"VOL-{vol.id}", "mobile_number": "98A6543210"})
        self.assertEqual(resp_post_char_mobile.status_code, 200)
        self.assertIn(b"Only numbers are allowed.", resp_post_char_mobile.data)

        # Invalid Indian prefix
        resp_post_bad_prefix = client.post(f"/attendance/scan/{ev.id}", data={"volunteer_code": f"VOL-{vol.id}", "mobile_number": "5678901234"})
        self.assertEqual(resp_post_bad_prefix.status_code, 200)
        self.assertIn(b"Enter a valid 10-digit Indian mobile number.", resp_post_bad_prefix.data)

        # 9. Test cancellation
        # Create a second event to test application and cancellation
        ev2 = Event(name="Clean Up Drive", description="Cleaning", category="Environment", date=datetime.utcnow().date(), time=datetime.utcnow().time(), venue="City Park", required_volunteers=5)
        db.session.add(ev2)
        db.session.commit()

        # Apply to ev2
        client.post(f"/events/apply/{ev2.id}")
        self.assertEqual(ev2.assigned_count, 1)

        # Cancel application
        client.post(f"/events/cancel/{ev2.id}")
        self.assertEqual(ev2.assigned_count, 0)

    def test_manager_attendance_tracking(self):
        # 1. Setup admin user
        admin_user = User(email="admin_test@ngo.com", role="admin")
        admin_user.set_password("adminpass")
        db.session.add(admin_user)
        db.session.commit()

        client = app.test_client()
        # Log in admin
        client.post('/login', data={'email': 'admin_test@ngo.com', 'password': 'adminpass'})

        # 2. Test Attendance Main Page GET
        resp_main = client.get('/attendance')
        self.assertEqual(resp_main.status_code, 200)

        # 2b. Test Volunteers Page GET
        resp_vols = client.get('/volunteers')
        self.assertEqual(resp_vols.status_code, 200)

        # 3. Test Attendance API Stats JSON
        resp_stats = client.get('/attendance/api/stats')
        self.assertEqual(resp_stats.status_code, 200)
        data = resp_stats.json
        self.assertTrue(data['success'])
        self.assertIn('registered', data)
        self.assertIn('checked_in', data)

        # 4. Test Attendance API Logs JSON
        resp_logs = client.get('/attendance/api/logs')
        self.assertEqual(resp_logs.status_code, 200)
        data_logs = resp_logs.json
        self.assertTrue(data_logs['success'])
        self.assertIn('logs', data_logs)

        # 5. Test Export CSV Report
        resp_export_csv = client.get('/attendance/report/export?report_type=monthly&format=csv')
        self.assertEqual(resp_export_csv.status_code, 200)
        self.assertEqual(resp_export_csv.mimetype, 'text/csv')
        self.assertIn(b"Volunteer Name", resp_export_csv.data)

        # 6. Test API Analytics JSON
        resp_analytics = client.get('/attendance/api/analytics')
        self.assertEqual(resp_analytics.status_code, 200)
        data_an = resp_analytics.json
        self.assertTrue(data_an['success'])
        self.assertIn('participation', data_an)

    def test_role_based_access_control(self):
        client = app.test_client()
        
        # Create a volunteer user for testing RBAC
        v_user = User.query.filter_by(email='vol_rbac@ngo.com').first()
        if not v_user:
            v_user = User(email='vol_rbac@ngo.com', role='volunteer')
            v_user.set_password('volpass')
            db.session.add(v_user)
            db.session.commit()
            
        # Log in as volunteer
        client.post('/login', data={'email': 'vol_rbac@ngo.com', 'password': 'volpass'})
        
        # Try to access manager route /volunteers
        resp = client.get('/volunteers')
        self.assertEqual(resp.status_code, 302) # Redirect to dashboard
        self.assertIn('/dashboard', resp.headers['Location'])
        
        # Try to access manager API stats
        resp_api = client.get('/attendance/api/stats')
        self.assertEqual(resp_api.status_code, 302) # Redirect to dashboard
        self.assertIn('/dashboard', resp_api.headers['Location'])

    def test_future_donation_date_validation(self):
        client = app.test_client()
        client.post('/login', data={'email': 'admin_test@ngo.com', 'password': 'adminpass'})
        
        import pytz
        from datetime import datetime, timedelta
        kolkata_tz = pytz.timezone('Asia/Kolkata')
        future_date = (datetime.now(kolkata_tz) + timedelta(days=5)).strftime('%Y-%m-%d')
        
        resp = client.post('/donations/add', data={
            'donor_name': 'Future Donor',
            'phone_number': '9876543210',
            'email': 'future@donor.com',
            'amount': 100.0,
            'donation_date': future_date,
            'payment_method': 'UPI',
            'purpose': 'Future camp'
        })
        self.assertEqual(resp.status_code, 302)
        fut_don = Donation.query.filter_by(donor_name='Future Donor').first()
        self.assertIsNone(fut_don)
        
        valid_don = Donation.query.filter_by(donor_name='Valid Donor').first()
        if not valid_don:
            valid_don = Donation(
                donor_name='Valid Donor',
                phone_number='9876543210',
                email='valid@donor.com',
                amount=50.0,
                donation_date=(datetime.now(kolkata_tz) - timedelta(days=1)).date(),
                payment_method='Cash',
                purpose='General'
            )
            db.session.add(valid_don)
            db.session.commit()
            
        resp_edit = client.post(f'/donations/edit/{valid_don.id}', data={
            'donor_name': 'Valid Donor',
            'phone_number': '9876543210',
            'email': 'valid@donor.com',
            'amount': 50.0,
            'donation_date': future_date,
            'payment_method': 'Cash',
            'purpose': 'General'
        })
        self.assertEqual(resp_edit.status_code, 302)
        db.session.refresh(valid_don)
        self.assertNotEqual(valid_don.donation_date.strftime('%Y-%m-%d'), future_date)

if __name__ == '__main__':
    unittest.main()

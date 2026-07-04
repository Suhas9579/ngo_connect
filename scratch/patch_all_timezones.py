# patch_all_timezones.py
import os

def patch_file(filepath, target, replacement):
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found")
        return False
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    if target in content:
        content = content.replace(target, replacement, 1)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Success: Patched {os.path.basename(filepath)}")
        return True
    else:
        print(f"Warning: Target not found in {os.path.basename(filepath)}")
        return False

# 1. Patch templates/attendance.html
attendance_target = """                                        <div class="list-group-item p-3 border-0 border-bottom">

                                            <p class="mb-0 small text-muted text-truncate">{{ log.event.name }}</p>"""
attendance_replacement = """                                        <div class="list-group-item p-3 border-0 border-bottom">
                                            <div class="d-flex w-100 justify-content-between align-items-center mb-1">
                                                <span class="fw-bold text-dark">{{ log.volunteer.full_name }}</span>
                                                <small class="text-teal fw-semibold">{{ log.timestamp | ist_time }}</small>
                                            </div>
                                            <p class="mb-0 small text-muted text-truncate">{{ log.event.name }}</p>"""
patch_file(r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\templates\attendance.html", attendance_target, attendance_replacement)

# 2. Patch templates/base.html
base_target = "{{ notif.created_at.strftime('%Y-%m-%d %H:%M') }}"
base_replacement = "{{ notif.created_at | ist }}"
patch_file(r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\templates\base.html", base_target, base_replacement)

# 3. Patch templates/certificates.html
cert_target = "{{ cert.issue_date.strftime('%Y-%m-%d') }}"
cert_replacement = "{{ cert.issue_date | ist('%d %b %Y') }}"
patch_file(r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\templates\certificates.html", cert_target, cert_replacement)

# 4. Patch app.py (api stats loop)
app_stats_target = """    recent_records = Attendance.query.order_by(Attendance.timestamp.desc()).limit(5).all()
    recent_list = []

        
    five_secs_ago = datetime.utcnow() - timedelta(seconds=5)"""
app_stats_replacement = """    recent_records = Attendance.query.order_by(Attendance.timestamp.desc()).limit(5).all()
    recent_list = []
    for r in recent_records:
        recent_list.append({
            'volunteer_name': r.volunteer.full_name,
            'time': format_ist(r.timestamp, '%I:%M %p IST'),
            'event_name': r.event.name
        })
        
    five_secs_ago = datetime.utcnow() - timedelta(seconds=5)"""
patch_file(r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\app.py", app_stats_target, app_stats_replacement)

# 5. Patch app.py (api logs check-in formatting)
app_logs_target = """            'event_date': l.event.date.strftime('%Y-%m-%d'),
            'check_in_time': l.timestamp.strftime('%I:%M %p'),
            'status': l.status,
            'ip_address': l.ip_address or '127.0.0.1',
            'device_info': l.device_info or 'Desktop',
            'created_at': l.created_at.strftime('%Y-%m-%d %H:%M') if l.created_at else l.timestamp.strftime('%Y-%m-%d %H:%M')"""
app_logs_replacement = """            'event_date': l.event.date.strftime('%Y-%m-%d'),
            'check_in_time': format_ist(l.timestamp, '%I:%M %p IST'),
            'status': l.status,
            'ip_address': l.ip_address or '127.0.0.1',
            'device_info': l.device_info or 'Desktop',
            'created_at': format_ist(l.created_at) if l.created_at else format_ist(l.timestamp)"""
patch_file(r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\app.py", app_logs_target, app_logs_replacement)

# 6. Patch app.py (csv export formatting)
app_csv_target = """            writer.writerow([
                l.volunteer.full_name,
                f"VOL-{l.volunteer.id:04d}",
                l.event.name,
                l.event.date.strftime('%Y-%m-%d'),
                l.timestamp.strftime('%I:%M %p'),
                l.status,
                l.ip_address or '127.0.0.1',
                l.device_info or 'Desktop',
                l.created_at.strftime('%Y-%m-%d %H:%M:%S') if l.created_at else ''
            ])"""
app_csv_replacement = """            writer.writerow([
                l.volunteer.full_name,
                f"VOL-{l.volunteer.id:04d}",
                l.event.name,
                l.event.date.strftime('%Y-%m-%d'),
                format_ist(l.timestamp, '%I:%M %p IST'),
                l.status,
                l.ip_address or '127.0.0.1',
                l.device_info or 'Desktop',
                format_ist(l.created_at) if l.created_at else ''
            ])"""
patch_file(r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\app.py", app_csv_target, app_csv_replacement)

# 7. Patch app.py (pdf rows data formatting)
app_pdf_target = """            rows_data.append([
                l.volunteer.full_name,
                f"VOL-{l.volunteer.id:04d}",
                l.event.name,
                l.event.date.strftime('%Y-%m-%d'),
                l.timestamp.strftime('%I:%M %p'),
                l.status,
                l.ip_address or '127.0.0.1',
                l.device_info or 'Desktop'
            ])"""
app_pdf_replacement = """            rows_data.append([
                l.volunteer.full_name,
                f"VOL-{l.volunteer.id:04d}",
                l.event.name,
                l.event.date.strftime('%Y-%m-%d'),
                format_ist(l.timestamp, '%I:%M %p IST'),
                l.status,
                l.ip_address or '127.0.0.1',
                l.device_info or 'Desktop'
            ])"""
patch_file(r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\app.py", app_pdf_target, app_pdf_replacement)

# 8. Patch app.py (pdf export helper formatting)
app_pdf_export_target = """                l.event.date.strftime('%Y-%m-%d'),
                l.timestamp.strftime('%I:%M %p'),"""
app_pdf_export_replacement = """                l.event.date.strftime('%Y-%m-%d'),
                format_ist(l.timestamp, '%I:%M %p IST'),"""
patch_file(r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\app.py", app_pdf_export_target, app_pdf_export_replacement)

# 9. Patch app.py (activity report logs generator)
app_activity_target = """                a.event.date.strftime('%Y-%m-%d'),
                a.status,
                a.marked_by,
                a.timestamp.strftime('%H:%M:%S')"""
app_activity_replacement = """                a.event.date.strftime('%Y-%m-%d'),
                a.status,
                a.marked_by,
                format_ist(a.timestamp, '%I:%M %p IST')"""
patch_file(r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\app.py", app_activity_target, app_activity_replacement)

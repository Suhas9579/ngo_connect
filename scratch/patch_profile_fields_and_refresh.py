# patch_profile_fields_and_refresh.py
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

# 1. Patch forms.py (add email field to VolunteerProfileForm)
forms_target = """class VolunteerProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    mobile_number = StringField('Mobile Number', validators=[DataRequired(), validate_indian_mobile])"""

forms_replacement = """class VolunteerProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email Address', validators=[DataRequired(), Email(), Length(max=120)])
    mobile_number = StringField('Mobile Number', validators=[DataRequired(), validate_indian_mobile])"""

for p in [r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\forms.py", r"C:\Users\User\OneDrive\Desktop\ngo_platform\forms.py"]:
    patch_file(p, forms_target, forms_replacement)


# 2. Patch templates/volunteers.html
# Add email field to admin edit modal
admin_edit_target = """                        <div class="row g-3">
                            <div class="col-md-6">
                                <label class="form-label fw-semibold small">Full Name</label>
                                <input type="text" class="form-control" name="full_name" value="{{ vol.full_name }}" required>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label fw-semibold small">Mobile Number</label>"""

admin_edit_replacement = """                        <div class="row g-3">
                            <div class="col-md-4">
                                <label class="form-label fw-semibold small">Full Name</label>
                                <input type="text" class="form-control" name="full_name" value="{{ vol.full_name }}" required>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label fw-semibold small">Email Address</label>
                                <input type="email" class="form-control" name="email" value="{{ vol.email }}" required>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label fw-semibold small">Mobile Number</label>"""

# Add email field to volunteer profile form layout
profile_form_target = """                    <div class="row g-3">
                        <div class="col-md-6">
                            <label for="full_name" class="form-label fw-semibold small">Full Name</label>
                            {{ profile_form.full_name(class="form-control", id="full_name") }}
                        </div>
                        <div class="col-md-6">
                            <label for="mobile_number" class="form-label fw-semibold small">Mobile Number</label>
                            {{ profile_form.mobile_number(class="form-control", id="mobile_number", type="tel", maxlength="10", minlength="10", inputmode="numeric", pattern="[6-9][0-9]{9}", oninput="this.value = this.value.replace(/[^0-9]/g, '').substring(0, 10);") }}
                        </div>"""

profile_form_replacement = """                    <div class="row g-3">
                        <div class="col-md-4">
                            <label for="full_name" class="form-label fw-semibold small">Full Name</label>
                            {{ profile_form.full_name(class="form-control", id="full_name") }}
                        </div>
                        <div class="col-md-4">
                            <label for="email" class="form-label fw-semibold small">Email Address</label>
                            {{ profile_form.email(class="form-control", id="email") }}
                        </div>
                        <div class="col-md-4">
                            <label for="mobile_number" class="form-label fw-semibold small">Mobile Number</label>
                            {{ profile_form.mobile_number(class="form-control", id="mobile_number", type="tel", maxlength="10", minlength="10", inputmode="numeric", pattern="[6-9][0-9]{9}", oninput="this.value = this.value.replace(/[^0-9]/g, '').substring(0, 10);") }}
                        </div>"""

for p in [r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\templates\volunteers.html", r"C:\Users\User\OneDrive\Desktop\ngo_platform\templates\volunteers.html"]:
    patch_file(p, admin_edit_target, admin_edit_replacement)
    patch_file(p, profile_form_target, profile_form_replacement)


# 3. Patch app.py (refresh logic & email synchronization)
volunteer_profile_target = """    if profile_form.validate_on_submit():
        profile_form.populate_obj(vol)
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('volunteer_profile'))"""

volunteer_profile_replacement = """    if profile_form.validate_on_submit():
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
        return redirect(url_for('volunteer_profile'))"""

edit_volunteer_target = """    vol.full_name = request.form.get('full_name')
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
    flash(f"Volunteer profile updated successfully.", "success")
    return redirect(url_for('volunteers'))"""

edit_volunteer_replacement = """    new_email = request.form.get('email', '').strip()
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
    return redirect(url_for('volunteers'))"""

edit_event_target = """    db.session.commit()
    flash("Event details modified successfully.", "success")
    return redirect(url_for('event_details', id=event.id))"""

edit_event_replacement = """    db.session.commit()
    db.session.refresh(event)
    flash("Event details modified successfully.", "success")
    return redirect(url_for('event_details', id=event.id))"""

edit_resource_target = """        db.session.commit()
        
        msg = "Resource inventory details updated successfully."
        if is_ajax:"""

edit_resource_replacement = """        db.session.commit()
        db.session.refresh(res)
        
        msg = "Resource inventory details updated successfully."
        if is_ajax:"""

edit_donation_target = """    db.session.commit()
    flash("Donation record updated successfully.", "success")
    return redirect(url_for('donations'))"""

edit_donation_replacement = """    db.session.commit()
    db.session.refresh(don)
    flash("Donation record updated successfully.", "success")
    return redirect(url_for('donations'))"""


for p in [r"C:\Users\User\.gemini\antigravity\scratch\ngo_platform\app.py", r"C:\Users\User\OneDrive\Desktop\ngo_platform\app.py"]:
    patch_file(p, volunteer_profile_target, volunteer_profile_replacement)
    patch_file(p, edit_volunteer_target, edit_volunteer_replacement)
    patch_file(p, edit_event_target, edit_event_replacement)
    patch_file(p, edit_resource_target, edit_resource_replacement)
    patch_file(p, edit_donation_target, edit_donation_replacement)

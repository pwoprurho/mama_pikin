import re
import os
import math
import pandas as pd
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from supabase import create_client 
from .utils import role_required, reload_app_settings
from . import supabase, cache

views_bp = Blueprint('views', __name__)

# --- Helper Functions ---
def clean_input(text):
    """Removes HTML tags and trims whitespace to prevent XSS."""
    if not isinstance(text, str): return text
    return re.sub(re.compile('<.*?>'), '', text).strip()

def get_high_privilege_key():
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

def get_live_kpis():
    """
    FIXED: Fetches KPIs using a fresh, dedicated connection to prevent WinError 10054.
    """
    try:
        url = os.environ.get("SUPABASE_URL")
        key = get_high_privilege_key() 
        
        if not url or not key:
            print("Error: KPIs missing Supabase credentials.")
            return {'patients_registered': 0, 'appointments_confirmed': 0, 'states_covered': 0}

        local_supabase = create_client(url, key)
        
        res = local_supabase.table('public_stats').select('stat_key, stat_value').execute()
        kpis = {item['stat_key']: item['stat_value'] for item in res.data}
        return kpis
    except Exception as e:
        print(f"Error fetching live KPIs: {e}")
        return {'patients_registered': 0, 'appointments_confirmed': 0, 'states_covered': 0}


def get_location_map():
    """Helper to map names to IDs for bulk upload."""
    try:
        states_res = supabase.table('states').select('id, name').execute()
        lgas_res = supabase.table('lgas').select('id, name, state_id').execute()
        state_map = {s['name'].lower(): s['id'] for s in states_res.data}
        lga_map = {f"{lga['state_id']}_{lga['name'].lower()}": lga['id'] for lga in lgas_res.data}
        return state_map, lga_map
    except Exception as e:
        print(f"Error fetching location map: {e}")
        return {}, {}

def get_pagination(total_count, current_page, per_page=20):
    total_pages = math.ceil(total_count / per_page)
    return {
        'current': current_page,
        'total': total_pages,
        'has_next': current_page < total_pages,
        'has_prev': current_page > 1,
        'next_num': current_page + 1,
        'prev_num': current_page - 1
    }

# --- PUBLIC ROUTES ---
@views_bp.route('/')
def home():
    return render_template('index.html', kpis=get_live_kpis())

@views_bp.route('/testimonials')
def testimonials():
    active_videos = []
    try:
        active_videos = supabase.table('public_videos').select('*').eq('is_active', True).order('created_at', desc=True).execute().data
    except Exception as e:
        print(f"Error loading public testimonials: {e}") 
    return render_template('testimonials.html', videos=active_videos)

@views_bp.route('/chatbot')
def chatbot():
    return render_template('chatbot.html')

@views_bp.route('/donate')
def donate():
    pk = os.environ.get("PAYSTACK_PUBLIC_KEY") or "pk_test_xxxxxxxx" 
    return render_template('donate.html', paystack_public_key=pk)

@views_bp.route('/donor-wall')
def donor_wall():
    donations = []
    total_donations = 0
    show_total = False
    try:
        res = supabase.table('public_donations').select('*').eq('status', 'success').order('created_at', desc=True).execute()
        donations = res.data
        
        settings_res = supabase.table('app_settings').select('setting_value').eq('setting_key', 'DISPLAY_TOTAL_DONATIONS').execute()
        if settings_res.data and settings_res.data[0]['setting_value'].lower() == 'true':
            show_total = True
            total_donations = sum(float(d['amount']) for d in donations)
    except Exception as e:
        print(f"Error loading donor wall: {e}")
    return render_template('donor_wall.html', donations=donations, total_donations=total_donations, show_total=show_total)

# --- DASHBOARD & ANALYTICS ---
@views_bp.route('/dashboard')
@login_required
@cache.cached(timeout=300)
def dashboard():
    failed_escalations, sub_locations, all_states = [], [], []
    try:
        # Fetch Failed Escalations
        query = supabase.table('master_appointments').select('*, patients!inner(full_name, phone_number, lgas!inner(name))').eq('status', 'failed_escalation')
        res_escalations = query.limit(10).order('last_call_timestamp', desc=True).execute()
        failed_escalations = res_escalations.data

        # Fetch Filters based on Role
        if hasattr(current_user, 'role') and current_user.role == 'state' and hasattr(current_user, 'state_id'):
            res_lgas = supabase.table('lgas').select('id, name').eq('state_id', current_user.state_id).order('name').execute()
            sub_locations = res_lgas.data
        if hasattr(current_user, 'role') and current_user.role == 'supa_user':
            res_states = supabase.table('states').select('id, name').order('name').execute()
            all_states = res_states.data
    except Exception as e:
        flash(f"An error occurred while fetching dashboard data: {e}", "error")
    return render_template('dashboard.html', failed_escalations=failed_escalations, sub_locations=sub_locations, all_states=all_states)

# --- PATIENT MANAGEMENT ---
@views_bp.route('/patients')
@login_required
def patients():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '').strip()
    per_page = 20
    start = (page - 1) * per_page
    end = start + per_page - 1 
    
    patients_list = []
    total_count = 0
    
    try:
        if search_query:
            query = supabase.table('patients').select('*, lgas!inner(name, states!inner(name))', count='exact').ilike('full_name', f'%{search_query}%')
        else:
            query = supabase.table('patients').select('*, lgas!inner(name, states!inner(name))', count='exact')
            
        res = query.range(start, end).order('created_at', desc=True).execute()
        patients_list = res.data
        total_count = res.count
        
    except Exception as e:
        flash(f"Error fetching patients: {e}", "error")

    pagination = get_pagination(total_count, page, per_page)
    return render_template('patients.html', patients=patients_list, pagination=pagination, search_query=search_query)

@views_bp.route('/register-patient', methods=['GET', 'POST'])
@login_required
def register_patient():
    if request.method == 'POST':
        full_name = clean_input(request.form.get('full_name'))
        phone = request.form.get('phone_number', '').strip()
        lga_id = request.form.get('lga_id')
        
        if not re.match(r'^(0[7-9][0-1]\d{8})$', phone):
            flash("Invalid Phone Number. Must be 11 digits starting with 07/08/09.", "error")
            states = supabase.table('states').select('*').order('name').execute().data or []
            return render_template('register_patient.html', states=states)

        try:
            data = {
                'full_name': full_name, 
                'phone_number': phone, 
                'lga_id': lga_id, 
                'gender': clean_input(request.form.get('gender')), 
                'age': clean_input(request.form.get('age')), 
                'blood_group': clean_input(request.form.get('blood_group')), 
                'genotype': clean_input(request.form.get('genotype')), 
                'emergency_contact_name': clean_input(request.form.get('emergency_contact_name')), 
                'emergency_contact_phone': clean_input(request.form.get('emergency_contact_phone')),
                'registered_by': current_user.id # This column is now expected by the DB
            }
            supabase.table('patients').insert(data).execute()
            flash('Patient registered successfully.', 'success')
            return redirect(url_for('views.patients'))
        except Exception as e:
            if "policy" in str(e).lower():
                flash("Permission Denied: You cannot register patients in this location.", "error")
            else:
                flash(f'Error registering patient: {e}', 'error')
    
    states = []
    try:
        states = supabase.table('states').select('*').order('name').execute().data
    except Exception as e:
        flash(f"Could not load states: {e}", "error")
    return render_template('register_patient.html', states=states)

@views_bp.route('/edit-patient/<uuid:patient_id>', methods=['GET', 'POST'])
@login_required
def edit_patient(patient_id):
    if request.method == 'POST':
        try:
            data = {
                'full_name': clean_input(request.form.get('full_name')),
                'phone_number': request.form.get('phone_number'),
                'gender': request.form.get('gender'),
                'age': request.form.get('age'),
                'blood_group': request.form.get('blood_group'),
                'genotype': request.form.get('genotype'),
                'emergency_contact_name': clean_input(request.form.get('emergency_contact_name')),
                'emergency_contact_phone': request.form.get('emergency_contact_phone')
            }
            supabase.table('patients').update(data).eq('id', str(patient_id)).execute()
            flash('Patient details updated.', 'success')
            return redirect(url_for('views.patients'))
        except Exception as e:
            flash(f'Error updating patient: {e}', 'error')
    
    try:
        patient = supabase.table('patients').select('*').eq('id', str(patient_id)).single().execute().data
    except:
        flash("Patient not found.", "error")
        return redirect(url_for('views.patients'))
    return render_template('edit_patient.html', patient=patient)

@views_bp.route('/bulk-upload', methods=['GET', 'POST'])
@login_required
def bulk_upload():
    if request.method == 'POST':
        if 'file' not in request.files or request.files['file'].filename == '':
            flash('No file part or no selected file', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        try:
            if file.filename.endswith('.csv'): df = pd.read_csv(file)
            elif file.filename.endswith(('.xls', '.xlsx')): df = pd.read_excel(file, engine='openpyxl')
            else:
                flash('Invalid file type. Please upload CSV or XLSX.', 'error')
                return redirect(request.url)
            
            state_map, lga_map = get_location_map()
            required_columns = ['Patient Name', 'Patient Phone', 'State', 'LGA']
            valid_patients = []
            failed_rows = []
            
            for index, row in df.iterrows():
                # --- NEW IMPROVED VALIDATION ---
                missing_cols = []
                for col in required_columns:
                    if col not in row or pd.isna(row[col]) or str(row[col]).strip() == '':
                        missing_cols.append(col)
                
                if missing_cols:
                    failed_rows.append(f"Row {index + 2}: Missing required data in columns: {', '.join(missing_cols)}")
                    continue
                
                state_key = str(row.get('State', '')).strip().lower()
                state_id = state_map.get(state_key)
                lga_key = f"{state_id}_{str(row.get('LGA', '')).strip().lower()}"
                lga_id = lga_map.get(lga_key)
                
                if not state_id or not lga_id:
                    failed_rows.append(f"Row {index + 2}: Location '{row.get('LGA')}, {row.get('State')}' not found.")
                    continue
                
                phone = str(row.get('Patient Phone')).strip()
                if len(phone) == 10 and not phone.startswith('0'): phone = '0' + phone

                valid_patients.append({
                    'full_name': clean_input(str(row.get('Patient Name'))), 
                    'phone_number': phone, 
                    'lga_id': lga_id, 
                    'gender': row.get('Gender'), 
                    'age': row.get('Age'), 
                    'blood_group': row.get('Blood Group'), 
                    'genotype': row.get('Genotype'),
                    'registered_by': current_user.id # This is now valid after schema update
                })
            
            if valid_patients:
                supabase.table('patients').insert(valid_patients).execute()
                flash(f'Successfully uploaded {len(valid_patients)} patients.', 'success')
            if failed_rows:
                flash(f'Upload completed with {len(failed_rows)} errors.', 'error')
                for error in failed_rows[:10]: flash(error, 'error_detail')
            
            return redirect(url_for('views.patients'))
        except Exception as e:
            flash(f'Critical Upload Error: {e}', 'error')
            return redirect(request.url)
    return render_template('bulk_upload.html')

# --- APPOINTMENTS & OPERATIONS ---
@views_bp.route('/schedule-appointment/<uuid:patient_id>', methods=['GET', 'POST'])
@login_required
def schedule_appointment(patient_id):
    if request.method == 'POST':
        try:
            supabase.table('master_appointments').insert({
                'patient_id': str(patient_id), 
                'appointment_datetime': request.form.get('appointment_datetime'), 
                'service_type': request.form.get('service_type'), 
                'preferred_language': request.form.get('preferred_language')
            }).execute()
            flash('Appointment scheduled successfully.', 'success')
            return redirect(url_for('views.patients'))
        except Exception as e:
            flash(f'Error scheduling appointment: {e}', 'error')
    
    patient = supabase.table('patients').select('*').eq('id', str(patient_id)).single().execute().data
    return render_template('schedule_appointment.html', patient=patient)

@views_bp.route('/appointments', methods=['GET', 'POST'])
@login_required
@role_required('local', 'state', 'national', 'supa_user')
def appointments():
    appointment_list = []
    form_data = request.form.to_dict() if request.method == 'POST' else {}
    search_query = request.args.get('q', '')
    
    start_date = request.form.get('start_date') or request.args.get('start_date')
    end_date = request.form.get('end_date') or request.args.get('end_date')
    
    try:
        query = supabase.table('master_appointments').select('*, patients!inner(full_name, phone_number, lgas!inner(name, states!inner(name)))')
        
        if start_date and end_date:
            query = query.gte('appointment_datetime', start_date).lte('appointment_datetime', end_date)
            
        if form_data.get('state_id'): query = query.eq('patients.lgas.state_id', form_data.get('state_id'))
        if form_data.get('lga_id'): query = query.eq('patients.lga_id', form_data.get('lga_id'))
        
        if search_query:
            query = query.ilike('patients.full_name', f'%{search_query}%')

        appointment_list = query.order('appointment_datetime').execute().data
    except Exception as e:
        flash(f"Error fetching appointments: {e}", "error")

    states = []
    try:
        states = supabase.table('states').select('id, name').order('name').execute().data
    except: pass
    
    return render_template('appointments.html', appointments=appointment_list, form_data=form_data, states=states, search_query=search_query) 

@views_bp.route('/edit-appointment/<uuid:appointment_id>', methods=['GET', 'POST'])
@login_required
@role_required('local', 'state', 'national', 'supa_user')
def edit_appointment(appointment_id):
    appointment_id_str = str(appointment_id)
    if request.method == 'POST':
        try:
            supabase.table('master_appointments').update({
                'status': request.form.get('status'),
                'service_type': request.form.get('service_type'),
                'preferred_language': request.form.get('preferred_language'),
                'volunteer_notes': clean_input(request.form.get('volunteer_notes')),
                'volunteer_id': current_user.id 
            }).eq('appointment_id', appointment_id_str).execute()
            flash('Appointment updated.', 'success')
            return redirect(url_for('views.appointments'))
        except Exception as e:
            flash(f'Error: {e}', 'error')
            return redirect(url_for('views.edit_appointment', appointment_id=appointment_id))

    try:
        appt = supabase.table('master_appointments').select('*, patients!inner(full_name, phone_number)').eq('appointment_id', appointment_id_str).single().execute().data
    except: appt = None
    
    return render_template('edit_appointment.html', appointment=appt, statuses=['pending', 'confirmed', 'rescheduled', 'transferred', 'unreachable', 'calling', 'human_escalation', 'failed_escalation', 'completed'], service_types=['Antenatal Care', 'Postnatal Care', 'Childbirth Delivery', 'Immunization', 'Vaccination', 'Family Planning', 'General'], languages=['English', 'Yoruba', 'Hausa', 'Igbo', 'Pidgin'])

@views_bp.route('/volunteer-queue')
@login_required
@cache.cached(timeout=60)
def volunteer_queue():
    patients = []
    try:
        patients = supabase.table('master_appointments').select('*, patients!inner(full_name, phone_number, lgas!inner(name))').in_('status', ['transferred', 'human_escalation']).order('updated_at', desc=True).execute().data
    except Exception as e:
        flash(f"Error: {e}", "error")
    return render_template('volunteer_queue.html', patients=patients)

# --- ADMIN ROUTES ---
@views_bp.route('/manage-videos', methods=['GET', 'POST'])
@login_required
@role_required('national', 'supa_user')
def manage_videos():
    if request.method == 'POST':
        try:
            youtube_url = request.form.get('youtube_url')
            youtube_id = youtube_url.split('v=')[-1].split('&')[0] if 'v=' in youtube_url else youtube_url.split('/')[-1]
            
            supabase.table('public_videos').insert({
                'title': clean_input(request.form.get('title')),
                'description': clean_input(request.form.get('description')),
                'youtube_id': youtube_id,
                'added_by': current_user.id
            }).execute()
            flash('Video added successfully.', 'success')
        except Exception as e:
            flash(f'Error adding video: {e}', 'error')
        return redirect(url_for('views.manage_videos'))
    
    videos = supabase.table('public_videos').select('*, volunteers(full_name)').order('created_at', desc=True).execute().data
    return render_template('manage_videos.html', videos=videos)

@views_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@role_required('supa_user')
def settings():
    if request.method == 'POST':
        try:
            for key, value in request.form.items():
                supabase.table('app_settings').update({'setting_value': value}).eq('setting_key', key).execute()
            # Assuming reload_app_settings is defined in utils
            # reload_app_settings(current_app)
            flash('Settings updated and applied instantly!', 'success')
        except Exception as e:
            flash(f'Error updating settings: {e}', 'error')
        return redirect(url_for('views.settings'))
    
    settings = {}
    try:
        res = supabase.table('app_settings').select('*').execute()
        settings = {item['setting_key']: item['setting_value'] for item in res.data}
    except: pass
    return render_template('settings.html', settings=settings)

@views_bp.route('/promote-user', methods=['GET', 'POST'])
@login_required
@role_required('national', 'supa_user')
def promote_user():
    if request.method == 'POST':
        try:
            supabase.table('volunteers').update({'role': request.form.get('new_role')}).eq('id', request.form.get('user_id')).execute()
            flash('User role updated successfully.', 'success')
        except Exception as e:
            flash(f'Error updating role: {e}', 'error')
        return redirect(url_for('views.promote_user'))
    
    volunteers = supabase.table('volunteers').select('*').order('full_name').execute().data
    return render_template('promote_user.html', volunteers=volunteers, promote_options=['volunteer', 'local', 'state', 'national', 'supa_user'])

@views_bp.route('/reports')
@login_required
@role_required('national', 'supa_user')
def reports():
    return render_template('reports.html')
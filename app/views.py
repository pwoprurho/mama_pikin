import pandas as pd
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from .utils import role_required
from . import supabase, cache

views_bp = Blueprint('views', __name__)

# --- Helper function for bulk upload location mapping ---
def get_location_map():
    """Fetches all states and LGAs and creates a mapping for efficient lookups."""
    try:
        states_res = supabase.table('states').select('id, name').execute()
        lgas_res = supabase.table('lgas').select('id, name, state_id').execute()
        state_map = {s['name'].lower(): s['id'] for s in states_res.data}
        lga_map = {f"{lga['state_id']}_{lga['name'].lower()}": lga['id'] for lga in lgas_res.data}
        return state_map, lga_map
    except Exception as e:
        print(f"Error fetching location map: {e}")
        return {}, {}

@views_bp.route('/')
def home():
    """Renders the public homepage."""
    return render_template('index.html')

@views_bp.route('/dashboard')
@login_required
@cache.cached(timeout=300)
def dashboard():
    """Renders the main dashboard for logged-in users."""
    failed_escalations, sub_locations, all_states = [], [], []
    try:
        # A Supabase RPC function is recommended here for production performance
        query = supabase.table('master_appointments').select('*, patients!inner(full_name, phone_number)').eq('status', 'failed_escalation')
        res_escalations = query.limit(10).order('last_call_timestamp', desc=True).execute()
        failed_escalations = res_escalations.data
        if current_user.role == 'state' and hasattr(current_user, 'state_id'):
            res_lgas = supabase.table('lgas').select('id, name').eq('state_id', current_user.state_id).order('name').execute()
            sub_locations = res_lgas.data
        if current_user.role == 'supa_user':
            res_states = supabase.table('states').select('id, name').order('name').execute()
            all_states = res_states.data
    except Exception as e:
        flash(f"An error occurred while fetching dashboard data: {e}", "error")
    return render_template('dashboard.html', failed_escalations=failed_escalations, sub_locations=sub_locations, all_states=all_states)

@views_bp.route('/patients')
@login_required
@cache.cached(timeout=300)
def patients():
    """Displays a searchable list of all registered patients."""
    try:
        res = supabase.table('patients').select('*, lgas!inner(name, states!inner(name))').limit(50).execute()
        patients = res.data
    except Exception as e:
        patients = []
        flash(f"Error fetching patients: {e}", "error")
    return render_template('patients.html', patients=patients)

@views_bp.route('/register-patient', methods=['GET', 'POST'])
@login_required
def register_patient():
    """Handles SINGLE new patient registration."""
    if request.method == 'POST':
        try:
            supabase.table('patients').insert({'full_name': request.form.get('full_name'), 'phone_number': request.form.get('phone_number'), 'lga_id': request.form.get('lga_id'), 'gender': request.form.get('gender'), 'age': request.form.get('age'), 'blood_group': request.form.get('blood_group'), 'genotype': request.form.get('genotype'), 'emergency_contact_name': request.form.get('emergency_contact_name'), 'emergency_contact_phone': request.form.get('emergency_contact_phone')}).execute()
            flash('Patient registered successfully.', 'success')
            return redirect(url_for('views.patients'))
        except Exception as e:
            flash(f'Error registering patient: {e}', 'error')
    states = []
    try:
        states = supabase.table('states').select('*').order('name').execute().data
    except Exception as e:
        flash(f"Could not load states: {e}", "error")
    return render_template('register_patient.html', states=states)

@views_bp.route('/bulk-upload', methods=['GET', 'POST'])
@login_required
def bulk_upload():
    """Handles production-level bulk patient uploads via CSV/XLSX."""
    if request.method == 'POST':
        if 'file' not in request.files or request.files['file'].filename == '':
            flash('No file part or no selected file', 'error')
            return redirect(request.url)
        file = request.files['file']
        try:
            if file.filename.endswith('.csv'): df = pd.read_csv(file)
            elif file.filename.endswith(('.xls', '.xlsx')): df = pd.read_excel(file, engine='openpyxl')
            else:
                flash('Invalid file type. Please upload a CSV or XLSX file.', 'error')
                return redirect(request.url)
            state_map, lga_map = get_location_map()
            required_columns, valid_patients, failed_rows = ['Patient Name', 'Patient Phone', 'State', 'LGA'], [], []
            for index, row in df.iterrows():
                if not all(col in row and pd.notna(row[col]) for col in required_columns):
                    failed_rows.append(f"Row {index + 2}: Missing required data.")
                    continue
                state_id = state_map.get(str(row.get('State', '')).strip().lower())
                lga_id = lga_map.get(f"{state_id}_{str(row.get('LGA', '')).strip().lower()}")
                if not state_id or not lga_id:
                    failed_rows.append(f"Row {index + 2}: Location '{row.get('LGA')}, {row.get('State')}' not found.")
                    continue
                valid_patients.append({'full_name': str(row.get('Patient Name')).strip(), 'phone_number': str(row.get('Patient Phone')).strip(), 'lga_id': lga_id, 'gender': row.get('Gender'), 'age': row.get('Age'), 'blood_group': row.get('Blood Group'), 'genotype': row.get('Genotype')})
            if valid_patients:
                supabase.table('patients').insert(valid_patients).execute()
                flash(f'Successfully uploaded {len(valid_patients)} patients.', 'success')
            if failed_rows:
                flash(f'Upload completed with {len(failed_rows)} errors.', 'error')
                for error in failed_rows[:5]: flash(error, 'error_detail')
            return redirect(url_for('views.patients'))
        except Exception as e:
            flash(f'A critical error occurred: {e}', 'error')
            return redirect(request.url)
    return render_template('bulk_upload.html')

@views_bp.route('/schedule-appointment/<uuid:patient_id>', methods=['GET', 'POST'])
@login_required
def schedule_appointment(patient_id):
    """Handles scheduling an appointment for an existing patient."""
    if request.method == 'POST':
        try:
            supabase.table('master_appointments').insert({'patient_id': str(patient_id), 'appointment_datetime': request.form.get('appointment_datetime'), 'service_type': request.form.get('service_type'), 'preferred_language': request.form.get('preferred_language')}).execute()
            flash('Appointment scheduled successfully.', 'success')
            return redirect(url_for('views.patients'))
        except Exception as e:
            flash(f'Error scheduling appointment: {e}', 'error')
    patient = supabase.table('patients').select('*').eq('id', str(patient_id)).single().execute().data
    return render_template('schedule_appointment.html', patient=patient)



# In app/views.py

@views_bp.route('/appointments', methods=['GET', 'POST'])
@login_required
@role_required('local', 'state', 'national', 'supa_user')
def appointments():
    """Renders a page to view appointments filtered by date."""
    appointment_list = []
    # --- CORRECTED LOGIC ---
    # Define form_data based on the request type
    if request.method == 'POST':
        form_data = request.form
        start_date = form_data.get('start_date')
        end_date = form_data.get('end_date')
    else: # For a GET request
        form_data = {}
        start_date, end_date = None, None

    if start_date and end_date:
        try:
            query = supabase.table('master_appointments').select('*, patients!inner(full_name, phone_number)')
            query = query.gte('appointment_datetime', start_date)
            query = query.lte('appointment_datetime', end_date)
            
            res = query.order('appointment_datetime').execute()
            appointment_list = res.data
        except Exception as e:
            flash(f"An error occurred while fetching appointments: {e}", "error")

    states = []
    try:
        states = supabase.table('states').select('*').order('name').execute().data
    except Exception as e:
        flash(f"Could not load states: {e}", "error")

    # Always pass form_data to the template
    return render_template('appointments.html', 
                           appointments=appointment_list, 
                           states=states,
                           form_data=form_data)

@views_bp.route('/volunteer-queue')
@login_required
@cache.cached(timeout=60)
def volunteer_queue():
    """Displays the queue of cases needing human intervention."""
    patients = []
    try:
        query = supabase.table('master_appointments').select('*, patients!inner(*)').in_('status', ['human_escalation', 'transferred'])
        res = query.order('updated_at', desc=True).execute()
        patients = res.data
    except Exception as e:
        flash(f"Error fetching volunteer queue: {e}", "error")
    return render_template('volunteer_queue.html', patients=patients)

@views_bp.route('/chatbot')
def chatbot():
    return render_template('chatbot.html')

@views_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@role_required('supa_user')
def settings():
    if request.method == 'POST':
        try:
            for key, value in request.form.items():
                supabase.table('app_settings').update({'setting_value': value}).eq('setting_key', key).execute()
            flash('Settings updated successfully.', 'success')
        except Exception as e:
            flash(f'Error updating settings: {e}', 'error')
        return redirect(url_for('views.settings'))
    settings = {}
    try:
        res = supabase.table('app_settings').select('*').execute()
        settings = {item['setting_key']: item['setting_value'] for item in res.data}
    except Exception as e:
        flash(f"Error fetching settings: {e}", "error")
    return render_template('settings.html', settings=settings)

@views_bp.route('/promote-user', methods=['GET', 'POST'])
@login_required
@role_required('national', 'supa_user')
def promote_user():
    if request.method == 'POST':
        user_id, new_role = request.form.get('user_id'), request.form.get('new_role')
        try:
            supabase.table('volunteers').update({'role': new_role}).eq('id', user_id).execute()
            flash('User role updated successfully.', 'success')
        except Exception as e:
            flash(f'Error updating role: {e}', 'error')
        return redirect(url_for('views.promote_user'))
    volunteers = []
    try:
        res = supabase.table('volunteers').select('*').order('full_name').execute()
        volunteers = res.data
    except Exception as e:
        flash(f"Error fetching volunteers: {e}", "error")
    promote_options = ['volunteer', 'local', 'state', 'national', 'supa_user']
    return render_template('promote_user.html', volunteers=volunteers, promote_options=promote_options)

@views_bp.route('/reports')
@login_required
@role_required('national', 'supa_user')
def reports():
    return render_template('reports.html')
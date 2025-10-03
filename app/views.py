import pandas as pd
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from .utils import role_required
from . import supabase, cache

views_bp = Blueprint('views', __name__)

def get_live_kpis():
    """Fetches the current KPI values directly from the public_stats table."""
    try:
        res = supabase.table('public_stats').select('stat_key, stat_value').execute()
        kpis = {item['stat_key']: item['stat_value'] for item in res.data}
        return kpis
    except Exception as e:
        print(f"Error fetching live KPIs: {e}")
        # Return zeros on failure
        return {'patients_registered': 0, 'appointments_confirmed': 0, 'states_covered': 0}

def get_location_map():
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
    # Fetch live KPI data and pass it to the template
    live_kpis = get_live_kpis()
    return render_template('index.html', kpis=live_kpis)

@views_bp.route('/dashboard')
@login_required
@cache.cached(timeout=300)
def dashboard():
    failed_escalations, sub_locations, all_states = [], [], []
    try:
        # Fetch FAILED ESCALATIONS for the dashboard table (Queue View component)
        query = supabase.table('master_appointments').select('*, patients!inner(full_name, phone_number, lgas!inner(name))').eq('status', 'failed_escalation')
        # Limiting to 10 for dashboard snapshot
        res_escalations = query.limit(10).order('last_call_timestamp', desc=True).execute()
        failed_escalations = res_escalations.data

        if hasattr(current_user, 'role') and current_user.role == 'state' and hasattr(current_user, 'state_id'):
            res_lgas = supabase.table('lgas').select('id, name').eq('state_id', current_user.state_id).order('name').execute()
            sub_locations = res_lgas.data
        if hasattr(current_user, 'role') and current_user.role == 'supa_user':
            res_states = supabase.table('states').select('id, name').order('name').execute()
            all_states = res_states.data
    except Exception as e:
        flash(f"An error occurred while fetching dashboard data: {e}", "error")
    return render_template('dashboard.html', failed_escalations=failed_escalations, sub_locations=sub_locations, all_states=all_states)

@views_bp.route('/patients')
@login_required
@cache.cached(timeout=300)
def patients():
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
    if request.method == 'POST':
        try:
            supabase.table('master_appointments').insert({'patient_id': str(patient_id), 'appointment_datetime': request.form.get('appointment_datetime'), 'service_type': request.form.get('service_type'), 'preferred_language': request.form.get('preferred_language')}).execute()
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
    # Initialize variables for template and logic
    appointment_list = []
    
    # 1. Capture form data or use defaults for GET request
    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        form_data = request.form.to_dict()
    else:
        # For a GET request, initialize empty data to prevent UndefinedError
        start_date, end_date = None, None
        form_data = {}

    states = []
    try:
        # 2. Fetch states for the filter dropdown
        states_res = supabase.table('states').select('id, name').order('name').execute()
        states = states_res.data
    except Exception as e:
        flash(f"Could not load states for filters: {e}", "error")

    # 3. Only run the appointment query if the form was submitted with dates
    if request.method == 'POST' and start_date and end_date:
        try:
            query = (
                supabase.table('master_appointments')
                .select('*, patients!inner(full_name, phone_number, lgas!inner(name, states!inner(name)))')
                .gte('appointment_datetime', start_date)
                .lte('appointment_datetime', end_date)
            )
            
            # Add state/LGA filtering
            if form_data.get('state_id'):
                query = query.eq('patients.lgas.state_id', form_data.get('state_id'))
            if form_data.get('lga_id'):
                query = query.eq('patients.lga_id', form_data.get('lga_id'))

            res = query.order('appointment_datetime').execute()
            appointment_list = res.data
        except Exception as e:
            flash(f"An error occurred while fetching appointments: {e}", "error")
            
    # 4. Pass all necessary variables to the template
    return render_template('appointments.html', 
                           appointments=appointment_list, 
                           form_data=form_data, 
                           states=states) 

@views_bp.route('/edit-appointment/<uuid:appointment_id>', methods=['GET', 'POST'])
@login_required
@role_required('local', 'state', 'national', 'supa_user')
def edit_appointment(appointment_id):
    appointment_id_str = str(appointment_id)
    
    statuses = ['pending', 'confirmed', 'rescheduled', 'transferred', 'unreachable', 'calling', 'human_escalation', 'failed_escalation', 'completed']
    service_types = ['Antenatal Care', 'Postnatal Care', 'Childbirth Delivery', 'Immunization', 'Vaccination', 'Family Planning', 'General']
    languages = ['English', 'Yoruba', 'Hausa', 'Igbo', 'Pidgin']

    if request.method == 'POST':
        try:
            # Gather status and optional notes
            new_status = request.form.get('status')
            volunteer_notes = request.form.get('volunteer_notes')
            
            update_data = {
                'status': new_status,
                'service_type': request.form.get('service_type'),
                'preferred_language': request.form.get('preferred_language'),
                'volunteer_notes': volunteer_notes,
                'volunteer_id': current_user.id # Log which volunteer made the last update
            }
            
            # Update the appointment in Supabase
            supabase.table('master_appointments').update(update_data).eq('appointment_id', appointment_id_str).execute()

            flash('Appointment updated successfully.', 'success')
            return redirect(url_for('views.appointments'))
        except Exception as e:
            flash(f'Error updating appointment: {e}', 'error')
            return redirect(url_for('views.edit_appointment', appointment_id=appointment_id))

    # GET request: Fetch the current appointment data
    try:
        # Note: We must fetch patient data to display patient name/info
        appt_res = supabase.table('master_appointments').select('*, patients!inner(full_name, phone_number)').eq('appointment_id', appointment_id_str).single().execute()
        appointment = appt_res.data
        
        if not appointment:
            flash("Appointment not found.", "error")
            return redirect(url_for('views.appointments'))

    except Exception as e:
        flash(f"Error fetching appointment details: {e}", "error")
        return redirect(url_for('views.appointments'))
        
    return render_template('edit_appointment.html', 
                           appointment=appointment, 
                           statuses=statuses, 
                           service_types=service_types,
                           languages=languages)

@views_bp.route('/volunteer-queue')
@login_required
@cache.cached(timeout=60)
def volunteer_queue():
    patients = []
    try:
        # Queue should focus on active human intervention cases.
        query = supabase.table('master_appointments').select('*, patients!inner(full_name, phone_number, lgas!inner(name))').in_('status', ['transferred', 'human_escalation'])
        res = query.order('updated_at', desc=True).execute()
        patients = res.data
    except Exception as e:
        flash(f"Error fetching volunteer queue: {e}", "error")
    return render_template('volunteer_queue.html', patients=patients)

@views_bp.route('/chatbot')
def chatbot():
    return render_template('chatbot.html')

@views_bp.route('/manage-videos', methods=['GET', 'POST'])
@login_required
@role_required('national', 'supa_user')
def manage_videos():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        youtube_url = request.form.get('youtube_url')
        
        # Extract YouTube ID from URL
        youtube_id = None
        if 'youtube.com/watch?v=' in youtube_url:
            youtube_id = youtube_url.split('v=')[-1].split('&')[0]
        elif 'youtu.be/' in youtube_url:
            youtube_id = youtube_url.split('youtu.be/')[-1].split('?')[0]
        
        if not youtube_id:
            flash("Invalid YouTube URL provided. Ensure it is a full URL or shortened youtu.be link.", "error")
            return redirect(url_for('views.manage_videos'))

        try:
            supabase.table('public_videos').insert({
                'title': title,
                'description': description,
                'youtube_id': youtube_id,
                'added_by': current_user.id
            }).execute()
            flash('Video added successfully.', 'success')
            return redirect(url_for('views.manage_videos'))
        except Exception as e:
            flash(f'Error adding video: {e}', 'error')
    
    # GET request: Fetch all videos
    videos = []
    try:
        videos = supabase.table('public_videos').select('*, volunteers(full_name)').order('created_at', desc=True).execute().data
    except Exception as e:
        flash(f"Error fetching videos: {e}", "error")

    return render_template('manage_videos.html', videos=videos)

@views_bp.route('/testimonials')
def testimonials():
    active_videos = []
    try:
        # Only fetch active videos for the public page
        active_videos = supabase.table('public_videos').select('*').eq('is_active', True).order('created_at', desc=True).execute().data
    except Exception as e:
        # Don't flash errors to public users
        print(f"Error loading public testimonials: {e}") 
        
    return render_template('testimonials.html', videos=active_videos)

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
        settings = {item['setting_key']: item['stat_value'] if 'stat_value' in item else item['setting_value'] for item in res.data}
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
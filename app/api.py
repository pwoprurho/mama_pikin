import os
import requests
import pandas as pd
from io import StringIO
import google.generativeai as genai
from flask import Blueprint, jsonify, request, Response, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from .utils import role_required
from . import supabase

api_bp = Blueprint('api', __name__)
MODEL_NAME = "gemini-2.5-flash"

def perform_google_search(query):
    """Performs a Google search using Custom Search JSON API."""
    try:
        search_api_key = current_app.config.get("GOOGLE_SEARCH_API_KEY") or os.environ.get("GOOGLE_SEARCH_API_KEY")
        search_cx = current_app.config.get("GOOGLE_SEARCH_CX") or os.environ.get("GOOGLE_SEARCH_CX")
        
        if not search_api_key or not search_cx:
            return []
            
        url = f"https://www.googleapis.com/customsearch/v1?key={search_api_key}&cx={search_cx}&q={query}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get('items', [])
    except Exception as e:
        print(f"Google Search Error: {e}")
        return []

# --- PAYMENT VERIFICATION ---
@api_bp.route('/api/verify-donation', methods=['POST'])
def verify_donation():
    data = request.get_json()
    reference = data.get('reference')
    client_email = data.get('email')
    client_amount = data.get('amount')
    full_name = data.get('full_name')
    is_public = data.get('is_public', False)

    if not reference: return jsonify({'status': 'error', 'message': 'No reference'}), 400

    try:
        paystack_secret = current_app.config.get("PAYSTACK_SECRET_KEY") or os.environ.get("PAYSTACK_SECRET_KEY")
        if not paystack_secret: return jsonify({'status': 'error', 'message': 'Config Error'}), 500

        verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {'Authorization': f'Bearer {paystack_secret}'}
        
        response = requests.get(verify_url, headers=headers)
        res_data = response.json()

        if res_data['status'] and res_data['data']['status'] == 'success':
            donation_entry = {
                'payment_ref': reference,
                'amount': client_amount,
                'currency': 'NGN',
                'donor_email': client_email,
                'internal_name': full_name,
                'public_name': full_name if is_public else "Anonymous",
                'is_public': is_public,
                'status': 'success'
            }
            supabase.table('public_donations').insert(donation_entry).execute()
            return jsonify({'status': 'success', 'message': 'Verified'})
        else:
            return jsonify({'status': 'error', 'message': 'Verification failed'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- DASHBOARD & ANALYTICS ---
@api_bp.route('/api/public-stats')
def public_stats():
    try:
        res = supabase.table('public_stats').select('*').execute()
        stats = {item['stat_key']: item['stat_value'] for item in res.data} if res.data else {}
        return jsonify(stats)
    except: return jsonify({})

@api_bp.route('/dashboard-data')
@login_required
def dashboard_data():
    try:
        res = supabase.rpc('get_dashboard_stats').execute()
        data = res.data or {}
        
        def extract_chart_data(json_list, label_key='label', data_key='count'):
            if not json_list: return {'labels': [], 'data': []}
            return {
                'labels': [item[label_key] for item in json_list],
                'data': [item[data_key] for item in json_list]
            }

        return jsonify({
            'bar_chart': extract_chart_data(data.get('bar_chart', [])),
            'pie_chart': extract_chart_data(data.get('pie_chart', [])),
            'line_chart': extract_chart_data(data.get('line_chart', []), label_key='date')
        })

    except Exception as e:
        print(f"Dashboard Error: {e}")
        return jsonify({'error': str(e)}), 500

# --- REPORT GENERATION ---
@api_bp.route('/download-report', methods=['POST'])
@login_required
@role_required('national', 'supa_user')
def download_report():
    try:
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        service_type = request.form.get('service_type')
        status = request.form.get('status')
        
        query = supabase.table('master_appointments').select(
            'appointment_datetime, service_type, status, volunteer_notes, patients(full_name, phone_number, lgas(name, states(name)))'
        ).gte('appointment_datetime', start_date).lte('appointment_datetime', end_date)
        
        if service_type != 'all': query = query.eq('service_type', service_type)
        if status != 'all': query = query.eq('status', status)
            
        res = query.execute()
        data = res.data
        
        if not data:
            flash("No records found.", "error")
            return redirect(url_for('views.reports'))

        flattened_data = []
        for item in data:
            patient = item.get('patients') or {}
            lga = patient.get('lgas') or {}
            state = lga.get('states') or {}
            
            flattened_data.append({
                'Date': item['appointment_datetime'],
                'Patient Name': patient.get('full_name', 'N/A'),
                'Phone': patient.get('phone_number', 'N/A'),
                'State': state.get('name', 'N/A'),
                'LGA': lga.get('name', 'N/A'),
                'Service': item['service_type'],
                'Status': item['status'],
                'Notes': item['volunteer_notes']
            })
            
        df = pd.DataFrame(flattened_data)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        
        return Response(
            csv_buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=SafeMama_Report_{start_date}.csv"}
        )
    except Exception as e:
        flash(f"Error generating report: {e}", "error")
        return redirect(url_for('views.reports'))

# --- CHATBOT ---
@api_bp.route('/chatbot', methods=['POST'])
def handle_chatbot():
    data = request.get_json()
    user_question = data.get('message', '')
    if not user_question: return jsonify({'response': 'Please ask a question.'})

    try:
        api_key = current_app.config.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        
        intent = model.generate_content(f"Classify intent (greeting/health_question): {user_question}").text.lower()
        
        if 'greeting' in intent:
            return jsonify({'response': "Hello! How can I help you with your health questions today?", 'source': 'Conversational'})
        
        try:
            embedding = genai.embed_content(model="models/embedding-001", content=user_question, task_type="retrieval_query")['embedding']
            docs = supabase.rpc('match_documents', {'query_embedding': embedding, 'match_threshold': 0.6, 'match_count': 3}).execute().data
            if docs:
                context = "\n".join([d['content'] for d in docs])
                prompt = f"Context: {context}\n\nQuestion: {user_question}\nAnswer:"
                response = model.generate_content(prompt).text
                return jsonify({'response': response, 'source': 'Knowledge Base'})
        except: pass

        response = model.generate_content(f"Answer safely as a health assistant: {user_question}").text
        return jsonify({'response': response, 'source': 'AI Assistant'})

    except Exception as e:
        return jsonify({'response': 'System Error. Please try again.'})

@api_bp.route('/complete-case/<uuid:appointment_id>', methods=['POST'])
@login_required
def complete_case(appointment_id):
    try:
        supabase.table('master_appointments').update({
            'status': 'completed', 
            'volunteer_notes': request.form.get('notes'), 
            'volunteer_id': current_user.id
        }).eq('appointment_id', str(appointment_id)).execute()
        flash('Case marked as completed.', 'success')
    except Exception as e:
        flash(f'Error completing case: {e}', 'error')
    return redirect(url_for('views.volunteer_queue'))

@api_bp.route('/api/lgas/<uuid:state_id>')
def get_lgas_for_state(state_id):
    try:
        res = supabase.table('lgas').select('id, name').eq('state_id', str(state_id)).order('name').execute()
        return jsonify(res.data)
    except: return jsonify([])
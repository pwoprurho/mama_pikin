import os
import requests
import pandas as pd
from io import StringIO
import google.generativeai as genai
from flask import Blueprint, jsonify, request, Response, flash, redirect, url_for
from flask_login import login_required, current_user
from .utils import role_required
from . import supabase, cache

api_bp = Blueprint('api', __name__)

# ==========================================
# 1. HELPER FUNCTIONS
# ==========================================

def perform_google_search(query):
    """
    Performs a live Google search using the Custom Search JSON API.
    Requires GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX in environment variables.
    """
    try:
        search_api_key = os.environ.get("GOOGLE_SEARCH_API_KEY") 
        search_cx = os.environ.get("GOOGLE_SEARCH_CX") 
        
        if not search_api_key or not search_cx:
            # print("WARNING: Google Search credentials missing.")
            return []
            
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': search_api_key,
            'cx': search_cx,
            'q': query,
            'num': 3  # Fetch top 3 results
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json().get('items', [])
    except Exception as e:
        print(f"Google Search Error: {e}")
        return []

# ==========================================
# 2. DASHBOARD DATA (Restored for script.js Compatibility)
# ==========================================

@api_bp.route('/dashboard-data')
@login_required
@cache.cached(timeout=60, query_string=True)
def dashboard_data():
    """
    Fetches data for Dashboard Charts & Map.
    Returns simple JSON structure ({labels: [], data: []}) to match existing script.js.
    """
    try:
        # 1. Get Filters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # 2. Build Query
        # Fetching raw data to process in Python (Replaces missing SQL RPC)
        query = supabase.table('master_appointments').select('service_type, status, appointment_datetime')
        
        if start_date:
            query = query.gte('appointment_datetime', start_date)
        if end_date:
            query = query.lte('appointment_datetime', end_date)
            
        res = query.execute()
        appointments = res.data
        
        # 3. Initialize Response Structures (Empty defaults)
        bar_chart = {'labels': [], 'data': []}
        pie_chart = {'labels': [], 'data': []}
        line_chart = {'labels': [], 'data': []}
        map_data = {}

        if appointments:
            df = pd.DataFrame(appointments)

            # --- A. Bar Chart (Service Type Volume) ---
            if 'service_type' in df.columns:
                service_counts = df['service_type'].value_counts()
                bar_chart = {
                    'labels': service_counts.index.tolist(),
                    'data': service_counts.values.tolist() # Simple list for script.js
                }

            # --- B. Pie Chart (Call Outcomes/Status) ---
            if 'status' in df.columns:
                status_counts = df['status'].value_counts()
                pie_chart = {
                    'labels': [s.capitalize() for s in status_counts.index.tolist()],
                    'data': status_counts.values.tolist() # Simple list for script.js
                }

            # --- C. Line Chart (Traffic Trends - Daily) ---
            if 'appointment_datetime' in df.columns:
                df['date'] = pd.to_datetime(df['appointment_datetime']).dt.date
                # Group by date and count
                daily_counts = df['date'].value_counts().sort_index()
                # If filtered, show range. If not, show last 7 days for readability.
                if not start_date and not end_date:
                    daily_counts = daily_counts.tail(7)
                
                line_chart = {
                    'labels': [str(d) for d in daily_counts.index],
                    'data': daily_counts.values.tolist()
                }

        # --- 4. Map Data (Patients by State) ---
        # Fetch separately to ensure map is populated even if appointments are empty
        try:
            map_query = supabase.table('patients').select('lgas!inner(states!inner(name))').execute()
            if map_query.data:
                df_map = pd.DataFrame(map_query.data)
                if not df_map.empty:
                    # Flatten nested JSON: lgas -> states -> name
                    df_map['state'] = df_map['lgas'].apply(lambda x: x['states']['name'] if x and 'states' in x else 'Unknown')
                    # Convert to dictionary { 'Lagos': 10, 'Kano': 5 }
                    map_data = df_map['state'].value_counts().to_dict()
        except Exception as e:
            print(f"Map Data Error: {e}")

        # Return the structure exactly as script.js expects
        return jsonify({
            'bar_chart': bar_chart,
            'pie_chart': pie_chart,
            'line_chart': line_chart,
            'map_data': map_data
        })

    except Exception as e:
        print(f"Dashboard API Error: {e}")
        # Return empty valid structure on error so frontend doesn't crash
        return jsonify({
            'bar_chart': {'labels': [], 'data': []},
            'pie_chart': {'labels': [], 'data': []},
            'line_chart': {'labels': [], 'data': []},
            'map_data': {}
        })

@api_bp.route('/histogram-data')
@login_required
def histogram_data():
    """
    Fetches specific data for the 'Service Type' Histogram with filters.
    Used by updateHistogram() in script.js.
    """
    try:
        # Get query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        service_filter = request.args.get('service_type')
        status_filter = request.args.get('status')
        lga_filter = request.args.get('lga_id')
        state_filter = request.args.get('state_id')

        # Build Query with joins
        query = supabase.table('master_appointments').select(
            'service_type, appointment_datetime, status, patients!inner(lga_id, lgas!inner(state_id))'
        )

        # Apply Filters
        if start_date: query = query.gte('appointment_datetime', start_date)
        if end_date: query = query.lte('appointment_datetime', end_date)
        if service_filter and service_filter != 'all': query = query.eq('service_type', service_filter)
        if status_filter and status_filter != 'all': query = query.eq('status', status_filter)
        if lga_filter and lga_filter != 'all': query = query.eq('patients.lga_id', lga_filter)
        if state_filter and state_filter != 'all': query = query.eq('patients.lgas.state_id', state_filter)

        res = query.execute()
        
        if not res.data:
            return jsonify({'labels': [], 'data': []})

        df = pd.DataFrame(res.data)
        if 'service_type' in df.columns:
            counts = df['service_type'].value_counts()
            return jsonify({
                'labels': counts.index.tolist(),
                'data': counts.values.tolist()
            })
            
        return jsonify({'labels': [], 'data': []})

    except Exception as e:
        print(f"Histogram Error: {e}")
        return jsonify({'labels': [], 'data': []})

# ==========================================
# 3. PUBLIC STATS (KPIs)
# ==========================================

@api_bp.route('/api/public-stats')
def public_stats():
    """Fetches live KPI stats for the public homepage."""
    try:
        res = supabase.table('public_stats').select('*').execute()
        stats = {item['stat_key']: item['stat_value'] for item in res.data} if res.data else {}
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# 4. CHATBOT (RAG + SEARCH)
# ==========================================

@api_bp.route('/chatbot', methods=['POST'])
def handle_chatbot():
    """
    Chatbot endpoint handling RAG (Retrieval Augmented Generation) and Web Search.
    """
    data = request.get_json()
    user_question = data.get('message', '')
    chat_history = data.get('history', [])

    if not user_question: return jsonify({'response': 'Please ask a question.'})

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # 1. Check Intent
        intent_prompt = f"Is '{user_question}' a greeting? Yes/No"
        intent_check = model.generate_content(intent_prompt).text.lower()
        if 'yes' in intent_check:
            return jsonify({'response': "Hello! I am Safemama AI. How can I help you today?", 'source': 'Conversational'})

        # 2. RAG Search (Internal Documents)
        # Generate embedding for the question
        embedding_resp = genai.embed_content(
            model="models/embedding-001", 
            content=user_question, 
            task_type="retrieval_query"
        )
        
        # Search Supabase 'documents' table via RPC
        rpc_params = {
            'query_embedding': embedding_resp['embedding'], 
            'match_threshold': 0.60, 
            'match_count': 3
        }
        relevant_docs = supabase.rpc('match_documents', rpc_params).execute().data
        
        context = ""
        source = "Safemama Knowledge Base"
        
        if relevant_docs:
            context = "\n".join([d['content'] for d in relevant_docs])
            # Use the most relevant source for citation
            if 'metadata' in relevant_docs[0] and 'source' in relevant_docs[0]['metadata']:
                source = relevant_docs[0]['metadata']['source']
        else:
            # 3. Fallback: Google Search (External)
            print("RAG found nothing. Falling back to Google Search.")
            search_results = perform_google_search(user_question)
            if search_results:
                context = "\n".join([f"{item['title']}: {item['snippet']}" for item in search_results])
                source = "Google Search"
            else:
                source = "General AI Knowledge"

        # 4. Generate Final Answer
        final_prompt = f"""
        You are a helpful health assistant for maternal care in Nigeria.
        Use the following Context to answer the User Question.
        
        Context:
        {context}
        
        User Question: {user_question}
        
        Answer (keep it safe, concise, and empathetic):
        """
        
        final_response = model.generate_content(final_prompt)
        return jsonify({'response': final_response.text, 'source': source})

    except Exception as e:
        print(f"Chatbot Error: {e}")
        return jsonify({'response': 'I am having trouble connecting. Please try again.'})

# ==========================================
# 5. REPORTING & UTILS
# ==========================================

@api_bp.route('/download-report', methods=['POST'])
@login_required
@role_required('national', 'supa_user')
def download_report():
    """Generates CSV report with joined patient/location data."""
    try:
        # Complex join to get readable names instead of IDs
        res = supabase.table('master_appointments').select(
            'appointment_datetime, service_type, status, volunteer_notes, '
            'patients(full_name, phone_number, gender, age, emergency_contact_name, '
            'lgas(name, states(name)))'
        ).execute()
        
        if not res.data: 
            flash("No data available to export.", "error")
            return redirect(url_for('views.dashboard'))

        flat_data = []
        for row in res.data:
            pt = row.get('patients') or {}
            loc = pt.get('lgas') or {}
            state = loc.get('states') or {}
            
            flat_data.append({
                'Date': row.get('appointment_datetime'),
                'Service': row.get('service_type'),
                'Status': row.get('status'),
                'Patient Name': pt.get('full_name', 'N/A'),
                'Phone': pt.get('phone_number', 'N/A'),
                'State': state.get('name', 'N/A'),
                'LGA': loc.get('name', 'N/A'),
                'Emergency Contact': pt.get('emergency_contact_name', '')
            })

        df = pd.DataFrame(flat_data)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        
        return Response(
            csv_buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=safemama_report.csv"}
        )

    except Exception as e:
        print(f"Export Error: {e}")
        flash("Export failed.", "error")
        return redirect(url_for('views.dashboard'))

@api_bp.route('/complete-case/<uuid:appointment_id>', methods=['POST'])
@login_required
def complete_case(appointment_id):
    """Marks a case as completed via the modal."""
    try:
        notes = request.form.get('notes')
        supabase.table('master_appointments').update({
            'status': 'completed', 
            'volunteer_notes': notes,
            'volunteer_id': current_user.id,
            'updated_at': 'now()'
        }).eq('appointment_id', str(appointment_id)).execute()
        flash('Case marked as completed.', 'success')
    except Exception as e:
        flash(f'Error completing case: {e}', 'error')
    
    return redirect(url_for('views.volunteer_queue'))

@api_bp.route('/api/lgas/<uuid:state_id>')
@cache.cached(timeout=86400) # Cache static LGA data for 24 hours
def get_lgas_for_state(state_id):
    """Fetches LGAs for a selected state."""
    try:
        res = supabase.table('lgas').select('id, name').eq('state_id', str(state_id)).order('name').execute()
        return jsonify(res.data)
    except Exception as e:
        return jsonify([])
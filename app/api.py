import os
import pandas as pd
import requests
import google.generativeai as genai
from io import StringIO
from flask import Blueprint, jsonify, request, Response, flash, redirect, url_for
from flask_login import login_required, current_user
from .utils import role_required
from . import supabase

api_bp = Blueprint('api', __name__)

# --- Helper: Basic Google Search ---
def perform_google_search(query):
    """Performs a Google search using the Custom Search JSON API."""
    try:
        search_api_key = os.environ.get("GOOGLE_SEARCH_API_KEY") 
        search_cx = os.environ.get("GOOGLE_SEARCH_CX") 
        if not search_api_key or not search_cx:
            print("WARNING: Google Search keys are missing in .env")
            return []
            
        url = f"https://www.googleapis.com/customsearch/v1?key={search_api_key}&cx={search_cx}&q={query}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get('items', [])
    except Exception as e:
        print(f"Google Search Error: {e}")
        return []

# --- Helper: Web Search Synthesis ---
def perform_web_search_rag(query, model, is_emergency=False):
    print(f"INFO: Performing Web Search Fallback for: {query}")
    search_results = perform_google_search(query)
    
    if not search_results:
        return jsonify({
            'response': "I'm having trouble connecting to the internet, but please go to a hospital immediately if this is an emergency.", 
            'source': 'System'
        })

    context_text = ""
    for item in search_results[:4]: 
        context_text += f"Source: {item.get('title')}\nSnippet: {item.get('snippet')}\n\n"
    
    if is_emergency:
        tone_instruction = """
        URGENT: MEDICAL EMERGENCY DETECTED.
        ROLE: Experienced, calm paramedic. 
        TONE: Direct, reassuring, and concise.
        INSTRUCTIONS:
        1. Tell them to get to a hospital.
        2. Give 3-4 bullet points of IMMEDIATE actions.
        3. Keep it under 100 words.
        """
        warning_prefix = "⚠️ **Please go to the nearest hospital immediately.**\n\n"
    else:
        tone_instruction = """
        ROLE: SafemamaPikin, a friendly health assistant.
        TONE: Conversational and easy to understand.
        INSTRUCTIONS: Summarize the answer safely and concisely.
        """
        warning_prefix = ""

    prompt = f"""
    {tone_instruction}
    
    --- WEB CONTEXT ---
    {context_text}
    
    --- USER QUESTION ---
    {query}
    
    Answer:
    """
    
    try:
        final_response = model.generate_content(prompt)
        full_response = warning_prefix + final_response.text
        return jsonify({'response': full_response, 'source': 'Web Search (Google)'})
    except Exception as e:
        print(f"Web Synthesis Error: {e}")
        return jsonify({'response': "I am unable to process the web results at this time.", 'source': 'System Error'})


# --- Helper: Contextualizer (Chatbot Context) ---
def contextualize_question(history, current_msg, model):
    """Rewrites the user's question to include context from the history."""
    if not history:
        return current_msg
    
    # Format last 3 turns of history
    history_text = ""
    for msg in history[-3:]: 
        role = msg.get('role', 'User')
        content = msg.get('content', '')
        history_text += f"{role}: {content}\n"
    
    prompt = f"""
    Given the chat history and the latest user input, rephrase the input into a standalone question that includes the necessary context.
    If the input is just a greeting (e.g., "Hello"), return it exactly as is.
    
    Chat History:
    {history_text}
    
    User Input: "{current_msg}"
    
    Standalone Version:
    """
    try:
        refined = model.generate_content(prompt).text.strip()
        print(f"DEBUG: Contextualized '{current_msg}' -> '{refined}'")
        return refined
    except Exception as e:
        print(f"Contextualization Failed: {e}")
        return current_msg


# --- Main Chatbot Route ---
@api_bp.route('/chatbot', methods=['POST'])
def handle_chatbot():
    data = request.get_json()
    raw_user_question = data.get('message', '')
    chat_history = data.get('history', []) 

    if not raw_user_question: 
        return jsonify({'response': 'Please ask a question.'})

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')

        # 1. CONTEXTUALIZATION STEP
        user_question = contextualize_question(chat_history, raw_user_question, model)

        # 2. Intent Classification
        intent_prompt = f"""
        Classify the intent based on PRIORITY RULES.
        PRIORITY 1: EMERGENCY (Bleeding, severe pain, snake bites, etc.)
        PRIORITY 2: HEALTH_QUERY (Symptoms, medical questions, advice)
        PRIORITY 3: GREETING (ONLY pure greetings)
        
        Input: "{user_question}"
        Response (ONE WORD):
        """
        intent = model.generate_content(intent_prompt).text.strip().upper()
        
        print(f"INFO: Intent='{intent}' | Query='{user_question}'") 

        if 'GREETING' in intent:
            return jsonify({
                'response': "Hello! I am your SafemamaPikin Assistant. How can I help you with your health today?", 
                'source': 'Conversational'
            })

        if 'EMERGENCY' in intent:
            return perform_web_search_rag(user_question, model, is_emergency=True)

        # 3. RAG Search
        print("INFO: Attempting Internal Knowledge Search...")
        
        embedding_res = genai.embed_content(
            model="models/text-embedding-004", 
            content=user_question, 
            task_type="retrieval_query"
        )
        question_embedding = embedding_res['embedding']
        
        relevant_docs = supabase.rpc('match_documents', {
            'query_embedding': question_embedding, 
            'match_threshold': 0.60, 
            'match_count': 5
        }).execute().data

        # 4. Verification ("The Judge")
        if relevant_docs:
            doc_context = "\n\n".join([f"[Doc {i+1}]: {d['content']}" for i, d in enumerate(relevant_docs)])
            
            verification_prompt = f"""
            You are a strict Medical Evaluator.
            User Question: "{user_question}"
            Retrieved Documents: {doc_context}
            TASK: 1. Do these documents answer the question? 2. If YES: Write "SUFFICIENT" followed by the answer. 3. If NO: Write "INSUFFICIENT".
            """
            
            verification_response = model.generate_content(verification_prompt).text.strip()
            
            if "INSUFFICIENT" in verification_response:
                print("INFO: Docs irrelevant. Falling back to Web.")
                return perform_web_search_rag(user_question, model)
            else:
                final_answer = verification_response.replace("SUFFICIENT", "").strip()
                source = relevant_docs[0].get('metadata', {}).get('source', 'Internal Knowledge Base')
                return jsonify({'response': final_answer, 'source': source})

        else:
            print("INFO: No docs found. Falling back to Web.")
            return perform_web_search_rag(user_question, model)

    except Exception as e:
        print(f"RAG Chatbot Error: {e}")
        return jsonify({'response': 'I encountered a system error. Please try again later.'})


# --- Dashboard Data Route (FIXED FOR FILTERS) ---
@api_bp.route('/dashboard-data')
@login_required
def dashboard_data():
    """Provides live, filtered data for the dashboard charts."""
    
    # 1. Collect filter parameters from the URL query string
    start_date = request.args.get('date-start')
    end_date = request.args.get('date-end')
    service_type = request.args.get('service-type-filter')
    state_id = request.args.get('state-filter')
    lga_id = request.args.get('lga-filter')

    # 2. Prepare arguments for the RPC call
    rpc_args = {
        'p_start_date': start_date,
        'p_end_date': end_date,
        'p_service_type': service_type if service_type != 'all' else None,
        'p_state_id': state_id if state_id != 'all' else None,
        'p_lga_id': lga_id if lga_id != 'all' else None,
    }

    try:
        # Calls the filtered RPC function
        res = supabase.rpc('get_dashboard_stats_filtered', rpc_args).execute()
        
        if res.data:
            data = res.data[0] if isinstance(res.data, list) and res.data else res.data
            return jsonify(data)
        else:
            return jsonify({
                'bar_chart': {'labels': [], 'data': []},
                'pie_chart': {'labels': [], 'data': []},
                'line_chart': {'labels': [], 'data': []}
            }), 200
    except Exception as e:
        print(f"Error fetching filtered dashboard data: {e}")
        return jsonify({
            'error': str(e),
            'bar_chart': {'labels': [], 'data': []},
            'pie_chart': {'labels': [], 'data': []},
            'line_chart': {'labels': [], 'data': []}
        }), 500

# --- Other API Routes ---

@api_bp.route('/api/public-stats')
def public_stats():
    try:
        res = supabase.table('public_stats').select('*').execute()
        stats = {item['stat_key']: item['stat_value'] for item in res.data} if res.data else {}
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/download-report', methods=['POST'])
@login_required
@role_required('national', 'supa_user')
def download_report():
    report_data = [{'patient_name': 'Aisha Bello', 'appointment_datetime': '2025-09-10T10:00:00', 'status': 'confirmed'}]
    df = pd.DataFrame(report_data)
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    return Response(
        csv_buffer.getvalue(), 
        mimetype="text/csv", 
        headers={"Content-disposition": "attachment; filename=safemama_report.csv"}
    )

@api_bp.route('/complete-case/<uuid:appointment_id>', methods=['POST'])
@login_required
def complete_case(appointment_id):
    notes = request.form.get('notes')
    try:
        supabase.table('master_appointments').update({
            'status': 'completed', 
            'volunteer_notes': notes, 
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500
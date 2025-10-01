import os
import pandas as pd
from io import StringIO
import google.generativeai as genai
from flask import Blueprint, jsonify, request, Response, flash, redirect, url_for
from flask_login import login_required, current_user
from .utils import role_required
from . import supabase
import requests
# NOTE: Removed 'cache' import if it existed, as we are removing the cache decorator

api_bp = Blueprint('api', __name__)

# --- Helper function for Google Search ---
def perform_google_search(query):
    """Performs a Google search and returns the top results."""
    try:
        # IMPORTANT: You must enable the "Custom Search API" in your Google Cloud project
        # and create a Custom Search Engine that searches the whole web.
        search_api_key = os.environ.get("GOOGLE_SEARCH_API_KEY") 
        search_cx = os.environ.get("GOOGLE_SEARCH_CX") 
        if not search_api_key or not search_cx:
            print("WARNING: GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_CX is not set. Search will fail.")
            return []
            
        url = f"https://www.googleapis.com/customsearch/v1?key={search_api_key}&cx={search_cx}&q={query}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get('items', [])
    except Exception as e:
        print(f"Google Search Error: {e}")
        return []

@api_bp.route('/api/public-stats')
# NOTE: The @cache.cached(timeout=300) decorator was REMOVED here to ensure fresh data.
def public_stats():
    """Provides the latest cached stats for the public homepage."""
    try:
        res = supabase.table('public_stats').select('*').execute()
        stats = {item['stat_key']: item['stat_value'] for item in res.data} if res.data else {}
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/dashboard-data')
@login_required
def dashboard_data():
    """Provides live data for the main dashboard charts by calling a database function."""
    try:
        # --- LIVE DATA IMPLEMENTATION ---
        # Call the RPC function to get all dashboard data in one efficient query
        res = supabase.rpc('get_dashboard_stats').execute()
        
        if res.data:
            return jsonify(res.data)
        else:
            # Provide empty but valid data if the function returns nothing
            return jsonify({
                'bar_chart': {'labels': [], 'data': []},
                'pie_chart': {'labels': [], 'data': []},
                'line_chart': {'labels': [], 'data': []}
            })

    except Exception as e:
        print(f"Error fetching dashboard data: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route('/histogram-data')
@login_required
def histogram_data():
    """Provides data for the filterable histogram on the dashboard."""
    # This is a placeholder; a production version would use a Supabase RPC function.
    data = {'labels': ['Antenatal', 'Vaccination', 'General'], 'data': [50, 80, 35]}
    return jsonify(data)

@api_bp.route('/chatbot', methods=['POST'])
def handle_chatbot():
    """Handles messages for the advanced, multi-tool health chatbot."""
    data = request.get_json()
    user_question = data.get('message', '')
    chat_history = data.get('history', [])

    if not user_question: return jsonify({'response': 'Please ask a question.'})

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Step 1: Classify the user's intent more granularly
        intent_prompt = f"""Classify the user's intent from the following input. Is it a 'greeting', 'direct_health_question', 'symptom_description', or 'first_aid_emergency'? Respond with only one of these options. Input: '{user_question}'"""
        intent_response = model.generate_content(intent_prompt)
        intent = intent_response.text.strip().lower().replace("'", "")

        # Step 2: Select the correct tool based on the intent
        if 'greeting' in intent:
            prompt = f"The user said: '{user_question}'. Respond with a friendly, brief greeting."
            final_response = model.generate_content(prompt)
            return jsonify({'response': final_response.text, 'source': 'Conversational'})

        elif 'symptom_description' in intent or 'first_aid_emergency' in intent:
            print("INFO: Performing live web search.")
            search_results = perform_google_search(user_question)
            if not search_results:
                return jsonify({'response': "I couldn't find any information online for that. Please describe it differently or consult a healthcare professional.", 'source': 'Web Search'})

            context = "Based on the following web search results, provide a helpful and safe answer to the user's question. Start with a strong warning that this is not a substitute for professional medical advice and to seek help immediately if it is an emergency.\n\n---WEB RESULTS---\n"
            for item in search_results[:3]:
                context += f"Title: {item.get('title')}\nSnippet: {item.get('snippet')}\n\n"
            
            prompt = f"{context}---USER'S SITUATION---\n{user_question}\n\n---ADVICE---\n"
            final_response = model.generate_content(prompt)
            return jsonify({'response': final_response.text, 'source': 'Web Search'})

        else: # Default to 'direct_health_question'
            print("INFO: Performing RAG search on internal documents.")
            history_context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history])
            standalone_question_prompt = f"Given the conversation: {history_context}\n\nRephrase this follow-up as a standalone question: {user_question}"
            standalone_question = model.generate_content(standalone_question_prompt).text.strip()

            question_embedding = genai.embed_content(model="models/embedding-001", content=standalone_question, task_type="retrieval_query")['embedding']
            relevant_docs = supabase.rpc('match_documents', {'query_embedding': question_embedding, 'match_threshold': 0.70, 'match_count': 5}).execute().data
            
            if not relevant_docs:
                return jsonify({'response': "I could not find information on that in my knowledge base. Please consult a healthcare professional.", 'source': 'N/A'})

            source_citation = relevant_docs[0].get('source', 'Internal Document')
            context = "Based ONLY on the provided text from trusted health guides, answer the user's question.\n\n---CONTEXT---\n"
            for doc in relevant_docs: context += doc['content'] + "\n\n"
            prompt = f"{context}---QUESTION---\n{user_question}\n\n---ANSWER---\n"
            final_response = model.generate_content(prompt)
            return jsonify({'response': final_response.text, 'source': source_citation})

    except Exception as e:
        print(f"RAG Chatbot Error: {e}")
        return jsonify({'response': 'Sorry, I encountered an error. Please try again.'})

@api_bp.route('/download-report', methods=['POST'])
@login_required
@role_required('national', 'supa_user')
def download_report():
    report_data = [{'patient_name': 'Aisha Bello', 'appointment_datetime': '2025-09-10T10:00:00', 'status': 'confirmed'}]
    df = pd.DataFrame(report_data)
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    return Response(csv_buffer.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=safemama_report.csv"})

@api_bp.route('/complete-case/<uuid:appointment_id>', methods=['POST'])
@login_required
def complete_case(appointment_id):
    notes = request.form.get('notes')
    try:
        supabase.table('master_appointments').update({'status': 'completed', 'volunteer_notes': notes, 'volunteer_id': current_user.id}).eq('appointment_id', str(appointment_id)).execute()
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
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

# --- Helper: Web Search Synthesis (The Fallback) ---
def perform_web_search_rag(query, model, is_emergency=False):
    """
    Performs a live Google Search and uses the LLM to synthesize 
    a natural, human-like answer.
    """
    print(f"INFO: Performing Web Search Fallback for: {query}")
    search_results = perform_google_search(query)
    
    if not search_results:
        return jsonify({
            'response': "I'm having trouble connecting to the internet, but please go to a hospital immediately if this is an emergency.", 
            'source': 'System'
        })

    # Prepare Context from Web Results (Top 4)
    context_text = ""
    for item in search_results[:4]: 
        context_text += f"Source: {item.get('title')}\nSnippet: {item.get('snippet')}\n\n"
    
    # --- CUSTOM INSTRUCTIONS FOR NATURAL TONE ---
    if is_emergency:
        # Emergency: Calm, Direct, Paramedic Style
        tone_instruction = """
        URGENT: MEDICAL EMERGENCY DETECTED.
        
        ROLE: You are an experienced, calm paramedic. 
        TONE: Direct, reassuring, and concise. Do NOT sound like a robot. 
        
        INSTRUCTIONS:
        1. Start with empathy but get straight to the point.
        2. Tell them to get to a hospital.
        3. Give 3-4 bullet points of IMMEDIATE actions (e.g., "Keep the limb still").
        4. Briefly list what NOT to do (e.g., "Do not cut the wound").
        5. Keep it under 100 words.
        """
        warning_prefix = "⚠️ **Please go to the nearest hospital immediately.**\n\n"
    else:
        # General Query: Friendly Health Assistant
        tone_instruction = """
        ROLE: You are SafemamaPikin, a friendly and knowledgeable health assistant.
        TONE: Conversational and easy to understand.
        
        INSTRUCTIONS:
        1. Summarize the answer based on the search results.
        2. Avoid complex medical jargon.
        3. Be concise (max 3-4 sentences).
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


# --- Main Chatbot Route ---
@api_bp.route('/chatbot', methods=['POST'])
def handle_chatbot():
    """
    Advanced RAG Chatbot with Strict Hierarchical Intent Classification.
    """
    data = request.get_json()
    user_question = data.get('message', '')

    if not user_question: 
        return jsonify({'response': 'Please ask a question.'})

    try:
        # 1. Initialize Gemini Model
        model = genai.GenerativeModel('gemini-2.5-flash')

        # 2. HIERARCHICAL Intent Classification (The Fix)
        # We enforce a strict priority list.
        intent_prompt = f"""
        Classify the user's intent based on the PRIORITY RULES below.
        
        PRIORITY 1 (Highest): EMERGENCY
        - Triggers: Bleeding, unconsciousness, severe pain, labor, snake bites, difficulty breathing, or "help".
        - Override: Even if they say "Hello", if they mention an emergency, it is EMERGENCY.
        
        PRIORITY 2: HEALTH_QUERY
        - Triggers: Describing a symptom ("I have a fever", "my head hurts"), asking a medical question, or seeking advice.
        - Override: Statements like "I feel sick" (without a question mark) ARE Health Queries.
        - Override: If they say "Hello, I have a headache", the health part wins. It is a HEALTH_QUERY.
        
        PRIORITY 3 (Lowest): GREETING
        - Triggers: Pure greetings ONLY with NO other content.
        - Examples: "Hello", "Hi", "Good morning", "Are you there?".
        
        User Input: "{user_question}"
        Response (ONE WORD ONLY: EMERGENCY, HEALTH_QUERY, or GREETING):
        """
        intent = model.generate_content(intent_prompt).text.strip().upper()
        
        print(f"INFO: Classified Intent as '{intent}'") 

        # --- PATH A: Greeting ---
        if 'GREETING' in intent:
            return jsonify({
                'response': "Hello! I am your SafemamaPikin Assistant. How can I help you with your health today?", 
                'source': 'Conversational'
            })

        # --- PATH B: Emergency (Skip DB, go straight to Web) ---
        if 'EMERGENCY' in intent:
            return perform_web_search_rag(user_question, model, is_emergency=True)

        # --- PATH C: RAG Search with Verification ---
        print("INFO: Attempting Internal Knowledge Search...")
        
        # 3. Generate Embedding
        embedding_res = genai.embed_content(
            model="models/text-embedding-004", 
            content=user_question, 
            task_type="retrieval_query"
        )
        question_embedding = embedding_res['embedding']
        
        # 4. Retrieve Documents (Get top 5)
        relevant_docs = supabase.rpc('match_documents', {
            'query_embedding': question_embedding, 
            'match_threshold': 0.60, 
            'match_count': 5
        }).execute().data

        # 5. The Verification Step ("The Judge")
        if relevant_docs:
            doc_context = "\n\n".join([f"[Doc {i+1}]: {d['content']}" for i, d in enumerate(relevant_docs)])
            
            verification_prompt = f"""
            You are a strict Medical Evaluator.
            
            User Question: "{user_question}"
            
            Retrieved Documents:
            {doc_context}
            
            TASK:
            1. Analyze the documents. Do they contain the SPECIFIC answer?
            2. If YES: Write "SUFFICIENT" followed by a concise answer derived ONLY from these docs.
            3. If NO (irrelevant topics): Write "INSUFFICIENT".
            """
            
            verification_response = model.generate_content(verification_prompt).text.strip()
            
            if "INSUFFICIENT" in verification_response:
                print("INFO: RAG Verification Failed. Falling back to Web Search.")
                return perform_web_search_rag(user_question, model)
            else:
                final_answer = verification_response.replace("SUFFICIENT", "").strip()
                source = relevant_docs[0].get('metadata', {}).get('source', 'Internal Knowledge Base')
                return jsonify({'response': final_answer, 'source': source})

        else:
            print("INFO: No internal documents found. Falling back to Web Search.")
            return perform_web_search_rag(user_question, model)

    except Exception as e:
        print(f"RAG Chatbot Error: {e}")
        return jsonify({'response': 'I encountered a system error. Please try again later.'})


# --- Other API Routes (Kept from original) ---

@api_bp.route('/api/public-stats')
def public_stats():
    try:
        res = supabase.table('public_stats').select('*').execute()
        stats = {item['stat_key']: item['stat_value'] for item in res.data} if res.data else {}
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/dashboard-data')
@login_required
def dashboard_data():
    try:
        res = supabase.rpc('get_dashboard_stats').execute()
        if res.data:
            return jsonify(res.data)
        else:
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
    data = {'labels': ['Antenatal', 'Vaccination', 'General'], 'data': [50, 80, 35]}
    return jsonify(data)

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
import os
import pandas as pd
from io import StringIO
import google.generativeai as genai
from flask import Blueprint, jsonify, request, Response, flash, redirect, url_for
from flask_login import login_required, current_user
from .utils import role_required
from . import supabase

api_bp = Blueprint('api', __name__)

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
    bar_chart_data = {'labels': ['AI', 'Human'], 'data': [120, 30]}
    pie_chart_data = {'labels': ['Confirmed', 'Rescheduled', 'Unreachable'], 'data': [75, 20, 5]}
    line_chart_data = {'labels': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], 'data': [10, 15, 12, 18, 25]}
    return jsonify({'bar_chart': bar_chart_data, 'pie_chart': pie_chart_data, 'line_chart': line_chart_data})

@api_bp.route('/histogram-data')
@login_required
def histogram_data():
    dummy_data = {'labels': ['Antenatal', 'Vaccination', 'General'], 'data': [50, 80, 35]}
    return jsonify(dummy_data)

@api_bp.route('/chatbot', methods=['POST'])
def handle_chatbot():
    data = request.get_json()
    user_question = data.get('message', '')
    if not user_question: return jsonify({'response': 'Please ask a question.'})
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        intent_prompt = f"Classify the input as 'health_question' or 'greeting'. Input: '{user_question}'"
        intent_response = model.generate_content(intent_prompt)
        intent = intent_response.text.strip().lower()
        if 'greeting' in intent:
            greeting_prompt = f"User said: '{user_question}'. Respond with a friendly, brief greeting."
            final_response = model.generate_content(greeting_prompt)
            return jsonify({'response': final_response.text})
        else:
            question_embedding = genai.embed_content(model="models/embedding-001", content=user_question, task_type="retrieval_query")['embedding']
            relevant_docs = supabase.rpc('match_documents', {'query_embedding': question_embedding, 'match_threshold': 0.70, 'match_count': 5}).execute().data
            if not relevant_docs:
                return jsonify({'response': "I could not find specific information on that topic in 'Where There Is No Doctor'. Please consult a healthcare professional."})
            context = "Based ONLY on the following information from 'Where There Is No Doctor', answer the user's question. If the info is not present, say you don't have information on that topic.\n\n---CONTEXT---\n"
            for doc in relevant_docs: context += doc['content'] + "\n\n"
            prompt = f"{context}---QUESTION---\n{user_question}\n\n---ANSWER---\n"
            final_response = model.generate_content(prompt)
            return jsonify({'response': final_response.text})
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
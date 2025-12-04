# --- __init__.py (Final Stable Version with Jinja Filters) ---

import os
import time
import threading
from datetime import datetime
from flask import Flask, g, render_template
from flask_login import LoginManager, current_user
from flask_bcrypt import Bcrypt
from flask_caching import Cache
from flask_assets import Environment, Bundle
from supabase import create_client, Client
from dotenv import load_dotenv
from .models import User
import google.generativeai as genai

# Initialize extensions
login_manager = LoginManager()
bcrypt = Bcrypt()
cache = Cache()
assets = Environment()
supabase: Client = None 

# Helper to get the correct high-privilege key
def get_high_privilege_key():
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

def update_public_stats(app):
    """Recalculates and updates the public_stats table periodically."""
    with app.app_context():
        print("Scheduler: Waiting 10s for server startup...")
        time.sleep(10)
        
        run_update(app)
        
        while True:
            time.sleep(3600) 
            run_update(app)

def run_update(app):
    """Creates a fresh connection and performs update with retries."""
    
    url = os.environ.get("SUPABASE_URL")
    key = get_high_privilege_key() 
    
    if not url or not key:
        print("KPI Scheduler: Missing Supabase credentials.")
        return

    max_retries = 3
    for attempt in range(max_retries):
        try:
            local_supabase = create_client(url, key)
            
            patients_res = local_supabase.table('patients').select('id', count='exact').execute()
            appointments_res = local_supabase.table('master_appointments').select('appointment_id', count='exact').eq('status', 'confirmed').execute()
            states_res = local_supabase.table('states').select('id', count='exact').execute()
            
            stats_to_update = [
                ('patients_registered', patients_res.count or 0),
                ('appointments_confirmed', appointments_res.count or 0),
                ('states_covered', states_res.count or 0)
            ]
            
            for k, v in stats_to_update:
                local_supabase.table('public_stats').update({'stat_value': v}).eq('stat_key', k).execute()
            
            print(f"KPIs updated: Patients={stats_to_update[0][1]}, Confirmed={stats_to_update[1][1]}, States={stats_to_update[2][1]}")
            return 

        except Exception as e:
            print(f"KPI Scheduler Warning (Attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(5)
    
    print("!!! ERROR in KPI Scheduler: Failed to update stats after multiple attempts. !!!")


def create_app():
    load_dotenv() 
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')

    # --- Configuration ---
    app.config['CACHE_TYPE'] = 'SimpleCache'
    cache.init_app(app)
    assets.init_app(app)
    
    # --- Jinja Filters (New Addition) ---
    def datetime_format(value, format='%Y-%m-%d %H:%M'):
        if not value: return ""
        if isinstance(value, str):
            try:
                # Handle ISO format strings from Supabase
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return value
        else:
            dt = value
        return dt.strftime(format)

    def format_currency(value, symbol=''):
        if value is None: return "0.00"
        return f"{value:,.2f}"

    app.jinja_env.filters['datetime_format'] = datetime_format
    app.jinja_env.filters['format_currency'] = format_currency
    
    # --- CONFIGURE GLOBAL CLIENT ---
    global supabase
    try:
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = get_high_privilege_key() 
        
        supabase = create_client(supabase_url, supabase_key)
        print("Supabase client initialized.")
        
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        print("Gemini configured successfully.")
    except Exception as e:
        print(f"!!! ERROR CONFIGURING SERVICES: {e} !!!")
        
    # START KPI SCHEDULER THREAD
    scheduler_thread = threading.Thread(target=update_public_stats, args=(app,))
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    # Initialize Flask extensions
    login_manager.init_app(app)
    bcrypt.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'error'
    
    @login_manager.user_loader
    def load_user(user_id):
        # FIX: Create a FRESH, high-privilege connection for the user loader
        try:
            url = os.environ.get("SUPABASE_URL")
            key = get_high_privilege_key() 
            local_supabase = create_client(url, key) 
            
            res = local_supabase.table('volunteers').select('*').eq('id', user_id).single().execute()
            if res.data:
                user_data = res.data
                return User(id=user_data['id'], full_name=user_data['full_name'], email=user_data['email'], role=user_data['role'])
        except Exception as e:
            print(f"User Loader Error: {e}") 
        return None

    # Register blueprints
    from .auth import auth_bp
    from .views import views_bp
    from .api import api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)

    @app.before_request
    def before_request():
        g.user = current_user

    # Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500
        
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('403.html'), 403

    return app
# --- __init__.py (Updated for Session Persistence) ---

import os
import time
import threading
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

# --- KPI Scheduler ---
def update_public_stats(app):
    with app.app_context():
        run_update(app)
        while True:
            time.sleep(3600) 
            run_update(app)

def run_update(app):
    global supabase
    try:
        # These queries require the Service Role Key to work reliably
        patients_res = supabase.table('patients').select('id', count='exact').execute()
        appointments_res = supabase.table('master_appointments').select('appointment_id', count='exact').eq('status', 'confirmed').execute()
        states_res = supabase.table('states').select('id', count='exact').execute()
        
        stats = [
            ('patients_registered', patients_res.count or 0),
            ('appointments_confirmed', appointments_res.count or 0),
            ('states_covered', states_res.count or 0)
        ]
        
        for key, value in stats:
            supabase.table('public_stats').upsert({'stat_key': key, 'stat_value': value}, on_conflict='stat_key').execute()
            
        print(f"KPIs updated: {stats}")
    except Exception as e:
        print(f"KPI Scheduler Error: {e}")

def create_app():
    load_dotenv() 
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_key_fallback')

    # --- Config ---
    app.config['CACHE_TYPE'] = 'SimpleCache'
    cache.init_app(app)
    assets.init_app(app)
    
    # --- Services ---
    global supabase
    try:
        url = os.environ.get("SUPABASE_URL")
        
        # [CRITICAL FIX] Prioritize the Service Role Key.
        # This gives the global client "Admin" privileges to read user profiles 
        # during the session check (load_user), preventing the login loop.
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
        
        if url and key:
            supabase = create_client(url, key)
            print("Supabase initialized (High Privilege Mode).")
        
        genai_key = os.environ.get("GEMINI_API_KEY")
        if genai_key:
            genai.configure(api_key=genai_key)
            print("Gemini initialized.")
    except Exception as e:
        print(f"Service Config Error: {e}")
        
    # --- Background Threads ---
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        kpi_thread = threading.Thread(target=update_public_stats, args=(app,))
        kpi_thread.daemon = True
        kpi_thread.start()
        
        from .scheduler import start_scheduler
        start_scheduler(app)
    
    # --- Auth ---
    login_manager.init_app(app)
    bcrypt.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'error'
    
    @login_manager.user_loader
    def load_user(user_id):
        if not supabase: return None
        try:
            # Since 'supabase' is now an Admin client, this bypasses the security
            # checks that were blocking the read, allowing the login to stick.
            res = supabase.table('volunteers').select('*').eq('id', user_id).single().execute()
            if res.data:
                d = res.data
                return User(id=d['id'], full_name=d['full_name'], email=d['email'], role=d['role'])
        except Exception as e:
            print(f"Load User Error: {e}")
        return None

    # --- Blueprints ---
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
    def page_not_found(e): return render_template('404.html'), 404
    @app.errorhandler(500)
    def server_error(e): return render_template('500.html'), 500
    @app.errorhandler(403)
    def forbidden(e): return render_template('403.html'), 403

    return app
import os
from flask import Flask, g, render_template
from flask_login import LoginManager, current_user
from flask_bcrypt import Bcrypt
from flask_caching import Cache
from flask_assets import Environment, Bundle
from supabase import create_client, Client
from dotenv import load_dotenv
from .models import User
import google.generativeai as genai

# Initialize extensions without the app object first
login_manager = LoginManager()
bcrypt = Bcrypt()
cache = Cache()
assets = Environment()
supabase: Client = None # Will be initialized inside create_app

def create_app():
    # Load environment variables at the very start
    load_dotenv() 
    
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')

    # --- Caching Configuration ---
    app.config['CACHE_TYPE'] = 'SimpleCache'
    cache.init_app(app)

    # --- Asset Bundling Configuration ---
    assets.init_app(app)
    js_bundle = Bundle('script.js', filters='jsmin', output='gen/packed.js')
    css_bundle = Bundle('style.css', filters='cssmin', output='gen/packed.css')
    assets.register('js_all', js_bundle)
    assets.register('css_all', css_bundle)

    # --- CONFIGURE SERVICES HERE ---
    global supabase
    try:
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_KEY")
        supabase = create_client(supabase_url, supabase_key)
        print("Supabase client initialized.")
        
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        print("Gemini configured successfully.")
    except Exception as e:
        print(f"!!! ERROR CONFIGURING SERVICES: {e} !!!")
    
    # Initialize Flask extensions with the app
    login_manager.init_app(app)
    bcrypt.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'error'
    
    @login_manager.user_loader
    def load_user(user_id):
        res = supabase.table('volunteers').select('*').eq('id', user_id).single().execute()
        if res.data:
            user_data = res.data
            return User(id=user_data['id'], full_name=user_data['full_name'], email=user_data['email'], role=user_data['role'])
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

    # --- Error Handlers ---
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
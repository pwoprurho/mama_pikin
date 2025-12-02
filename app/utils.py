import os
from functools import wraps
from flask import abort, current_app
from flask_login import current_user
from supabase import create_client

def role_required(*roles):
    """Decorator to restrict access based on user roles."""
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403) # Forbidden
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

def get_supabase_client():
    """
    Returns a fresh Supabase client using current app config.
    Useful if keys are rotated/updated at runtime.
    """
    # Fallback to env vars if config is empty during startup
    url = current_app.config.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = current_app.config.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    return create_client(url, key)

def reload_app_settings(app):
    """
    Fetches configuration from 'app_settings' table and updates 
    Flask app config and OS environment variables at runtime.
    """
    print("--- Attempting to Reload Real-Time Settings ---")
    try:
        # Use environment variables to establish the initial connection
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        client = create_client(url, key)
        
        response = client.table('app_settings').select('setting_key, setting_value').execute()
        
        if response.data:
            count = 0
            for setting in response.data:
                key = setting['setting_key']
                val = setting['setting_value']
                
                # Update Flask Config and OS Environ
                app.config[key] = val
                os.environ[key] = val
                count += 1
                
            print(f"Successfully reloaded {count} settings.")
            return True
        return False
    except Exception as e:
        print(f"CRITICAL ERROR reloading settings: {e}")
        return False
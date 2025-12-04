import os
from app import create_app

# Create the application instance
# This 'app' variable is what Gunicorn looks for by default
app = create_app()

if __name__ == '__main__':
    """
    This block only runs if you execute 'python run.py' directly.
    In production, this should NOT be used. Use Gunicorn instead.
    """
    # Fetch configuration from Environment Variables (safer than hardcoding)
    port = int(os.environ.get("PORT", 5000))
    
    # Ensure DEBUG is FALSE unless explicitly set to 'true' in environment
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    
    if not debug_mode:
        print("WARNING: You are running Flask with the built-in server in production mode.")
        print("For production, please use a WSGI server like Gunicorn.")
        print("Command: gunicorn run:app")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
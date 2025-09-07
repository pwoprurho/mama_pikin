from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from . import supabase
from .models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register_user():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check for password mismatch
        if password != request.form.get('confirm_password'):
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.register_user'))

        try:
            # Step 1: Sign up the user with Supabase Auth.
            # We pass full_name in the 'data' payload so the trigger can access it.
            auth_res = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": { "data": { "full_name": full_name } }
            })
            
            # The trigger will have already created the basic profile.
            # Step 2: Now, update that profile with the rest of the form data.
            supabase.table('volunteers').update({
                'phone_number': request.form.get('phone_number'),
                'spoken_languages': request.form.getlist('spoken_languages'),
                'state_id': request.form.get('state_id') or None,
                'lga_id': request.form.get('lga_id') or None
            }).eq('id', auth_res.user.id).execute()

            flash('Account created successfully! Please check your email to confirm.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            flash(f"Error creating account: {e}", 'error')
            return redirect(url_for('auth.register_user'))

    # GET request logic
    try:
        states = supabase.table('states').select('id, name').order('name').execute().data
    except Exception as e:
        states = []
        flash(f"Could not load locations: {e}", "error")
    languages = ['English', 'Yoruba', 'Hausa', 'Igbo', 'Pidgin']
    return render_template('register_user.html', languages=languages, states=states)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            # Use Supabase Auth to sign the user in
            auth_res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            
            # The user is authenticated with Supabase, now fetch their profile to log them into Flask-Login
            user_profile_res = supabase.table('volunteers').select('*').eq('id', auth_res.user.id).single().execute()
            if user_profile_res.data:
                user_data = user_profile_res.data
                user = User(
                    id=user_data['id'],
                    full_name=user_data['full_name'],
                    email=user_data['email'],
                    role=user_data['role']
                )
                login_user(user) # This handles the Flask session
                return redirect(url_for('views.dashboard'))
            else:
                flash("Login successful, but could not find user profile.", "error")
        except Exception as e:
            flash(f"Login failed: {e}", "error")
        
        return redirect(url_for('auth.login'))

    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Logs the current user out."""
    supabase.auth.sign_out() # Sign out from Supabase
    logout_user() # Sign out from Flask-Login
    return redirect(url_for('views.home'))
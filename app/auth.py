import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from supabase import create_client, Client
from . import supabase as global_supabase_admin  # Rename to clarify this is the ADMIN client
from .models import User

auth_bp = Blueprint('auth', __name__)

def get_auth_client():
    """Creates a temporary client for authentication to avoid tainting the global admin client."""
    url = os.environ.get("SUPABASE_URL")
    # Use the ANON key for login attempts, NOT the service role key
    key = os.environ.get("SUPABASE_KEY") 
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in environment.")
    return create_client(url, key)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register_user():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if password != request.form.get('confirm_password'):
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.register_user'))

        try:
            # Use a temporary client for the sign-up action
            temp_client = get_auth_client()
            auth_res = temp_client.auth.sign_up({
                "email": email,
                "password": password,
                "options": { "data": { "full_name": full_name } }
            })
            
            # Use the GLOBAL ADMIN client to update the profile (Bypasses RLS)
            if auth_res.user:
                global_supabase_admin.table('volunteers').update({
                    'phone_number': request.form.get('phone_number'),
                    'spoken_languages': request.form.getlist('spoken_languages'),
                    'state_id': request.form.get('state_id') or None,
                    'lga_id': request.form.get('lga_id') or None
                }).eq('id', auth_res.user.id).execute()

            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            flash(f"Error creating account: {e}", 'error')
            return redirect(url_for('auth.register_user'))

    # Load states using the admin client
    try:
        states = global_supabase_admin.table('states').select('id, name').order('name').execute().data
    except:
        states = []
    
    languages = ['English', 'Yoruba', 'Hausa', 'Igbo', 'Pidgin']
    return render_template('register_user.html', languages=languages, states=states)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            # 1. AUTHENTICATE with a TEMPORARY CLIENT
            # We create a new client just to check the password. 
            # This prevents the global admin client from becoming "logged in" as this user.
            temp_client = get_auth_client()
            auth_res = temp_client.auth.sign_in_with_password({"email": email, "password": password})
            
            # 2. FETCH PROFILE with GLOBAL ADMIN CLIENT
            # Since global_supabase_admin still has the Service Role Key, 
            # this query bypasses all RLS and recursion errors.
            user_profile_res = global_supabase_admin.table('volunteers').select('*').eq('id', auth_res.user.id).single().execute()
            
            if user_profile_res.data:
                user_data = user_profile_res.data
                user = User(
                    id=user_data['id'],
                    full_name=user_data['full_name'],
                    email=user_data['email'],
                    role=user_data['role']
                )
                login_user(user) # Logs the user into Flask
                return redirect(url_for('views.dashboard'))
            else:
                flash("Login successful, but user profile not found.", "error")

        except Exception as e:
            flash(f"Login failed: {e}", "error")
        
        return redirect(url_for('auth.login'))

    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    # We don't need to sign out the global client because we never signed it in!
    logout_user() # Clear Flask session
    return redirect(url_for('views.home'))
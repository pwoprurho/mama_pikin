import os
from supabase import create_client
from dotenv import load_dotenv

# 1. Load Environment Variables
load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") # Must use Service Role to bypass potential issues

if not url or not key:
    print("Error: Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
    exit()

# 2. Initialize High-Privilege Client
supabase = create_client(url, key)

# 3. Define the Admin User
ADMIN_EMAIL = "akporurho@proton.me"
ADMIN_PASSWORD = "Ejiro2828!" # <--- Use this EXACT password to login
ADMIN_NAME = "System Administrator"

def create_admin():
    print(f"--- Creating Admin User: {ADMIN_EMAIL} ---")
    
    try:
        # Step A: Create User in Supabase Auth
        # Note: If user exists, this might raise an error or return the existing user.
        try:
            user = supabase.auth.admin.create_user({
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
                "email_confirm": True,
                "user_metadata": {"full_name": ADMIN_NAME}
            })
            user_id = user.user.id
            print(f" -> Auth User Created/Found (ID: {user_id})")
        except Exception as e:
            # If creation fails (e.g., already exists), try to fetch the ID via a workaround or just print error
            print(f" -> Auth Warning: {e}")
            # If the user already exists, we can't easily get their ID via admin API without listing users.
            # Let's try to sign in to get the ID.
            signin = supabase.auth.sign_in_with_password({"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            user_id = signin.user.id
            print(f" -> Logged in to existing user (ID: {user_id})")

        # Step B: Ensure Profile Exists in 'volunteers' table
        # We upsert (insert or update) to ensure the role is 'supa_user'
        profile_data = {
            "id": user_id,
            "full_name": ADMIN_NAME,
            "email": ADMIN_EMAIL,
            "role": "supa_user",  # <--- Granting Super Admin privileges
            "spoken_languages": ["English", "Pidgin"],
            "password": "hashed_by_auth_service" # Placeholder, not used for login
        }
        
        supabase.table("volunteers").upsert(profile_data).execute()
        print(" -> Volunteer Profile Synced (Role: supa_user)")
        print("\nSUCCESS! You can now log in.")
        print(f"Email: {ADMIN_EMAIL}")
        print(f"Password: {ADMIN_PASSWORD}")

    except Exception as e:
        print(f"\nCRITICAL FAILURE: {e}")

if __name__ == "__main__":
    create_admin()
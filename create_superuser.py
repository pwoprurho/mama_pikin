import os
import argparse
from supabase import create_client, Client
from dotenv import load_dotenv

def create_superuser(full_name, email, password):
    """
    Creates a new user via Supabase Auth and then promotes them to 'supa_user'
    in the public volunteers table.
    """
    load_dotenv()
    
    # Initialize Supabase client
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    # IMPORTANT: Use the SERVICE_ROLE_KEY for admin actions
    supabase: Client = create_client(supabase_url, supabase_key)

    print(f"Attempting to create superuser: {email}")

    try:
        # Step 1: Create the user in Supabase's authentication system.
        # This will also trigger the 'handle_new_user' function in your DB 
        # to create a basic profile in the 'volunteers' table.
        auth_res = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": { "data": { "full_name": full_name } }
        })
        
        if not auth_res.user:
            raise Exception("User was not created in Supabase Auth.")
            
        user_id = auth_res.user.id
        print(f"Successfully created user in Supabase Auth with ID: {user_id}")

        # Step 2: Update the user's profile in the 'volunteers' table to grant the 'supa_user' role.
        print("Promoting user to 'supa_user'...")
        update_res = supabase.table('volunteers').update({
            'role': 'supa_user',
            'full_name': full_name # Ensure full_name is set correctly
        }).eq('id', user_id).execute()

        if not update_res.data:
             raise Exception("Failed to update user profile to supa_user.")

        print(f"Successfully created and promoted superuser '{full_name}'.")
        print("NOTE: You may need to confirm the user's email in your Supabase project dashboard if email confirmation is enabled.")

    except Exception as e:
        print(f"\nAn error occurred:")
        # The Supabase client often wraps the real error message
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Create a new Supa User for the SafemamaPikin application.")
    parser.add_argument('--name', required=True, help="Full name of the superuser, enclosed in quotes.")
    parser.add_argument('--email', required=True, help="Email address for the new superuser.")
    parser.add_argument('--password', required=True, help="A strong password for the new superuser.")
    
    args = parser.parse_args()
    
    create_superuser(args.name, args.email, args.password)
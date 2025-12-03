import threading
import time
from datetime import datetime, timedelta
# Import create_client here, but don't initialize a global client
from supabase import create_client
import os # Import os to get environment variables

def start_scheduler(app):
    """Starts the background thread."""
    thread = threading.Thread(target=run_schedule, args=(app,))
    thread.daemon = True
    thread.start()

def run_schedule(app):
    print("--- Background Scheduler Started ---")
    while True:
        with app.app_context():
            # Call the function that handles connection logic and retries
            check_upcoming_reminders()
        # Check every hour (3600 seconds)
        time.sleep(3600)

def check_upcoming_reminders(max_retries=3):
    """Finds confirmed appointments for tomorrow and flags them for a call, with retries."""
    
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        print("Scheduler: Missing Supabase credentials. Skipping reminders.")
        return

    for attempt in range(max_retries):
        try:
            # FIX: Create a dedicated connection for this task to avoid WinError 10054
            local_supabase = create_client(url, key)
            
            # Logic: Find appointments scheduled for 'Tomorrow'
            now = datetime.now()
            tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
            tomorrow_end = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59)

            # Fetch confirmed appointments
            # Use the local_supabase client here
            res = local_supabase.table('master_appointments')\
                .select('appointment_id, status, patients(full_name, phone_number)')\
                .eq('status', 'confirmed')\
                .gte('appointment_datetime', tomorrow_start.isoformat())\
                .lte('appointment_datetime', tomorrow_end.isoformat())\
                .execute()
            
            appointments = res.data or []
            
            if appointments:
                print(f"Scheduler: Found {len(appointments)} reminders to send.")
                for appt in appointments:
                    # Update status to 'calling' using the local client
                    local_supabase.table('master_appointments').update({
                        'status': 'calling',
                        'last_call_timestamp': datetime.now().isoformat()
                    }).eq('appointment_id', appt['appointment_id']).execute()
                    
                    print(f" -> Triggered reminder for {appt['patients']['full_name']}")
            else:
                print("Scheduler: No appointments pending reminders for tomorrow.")
            
            return # Success! Exit the function.

        except Exception as e:
            print(f"Scheduler Warning (Attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(5) # Wait 5 seconds before retrying
    
    print("!!! ERROR in Scheduler: Failed to check reminders after multiple attempts. !!!")

# Note: No 'supabase' import needed at the top of the file anymore.
# The previous global import caused the crash.
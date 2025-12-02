import threading
import time
from datetime import datetime, timedelta
from . import supabase

def start_scheduler(app):
    """Starts the background thread."""
    thread = threading.Thread(target=run_schedule, args=(app,))
    thread.daemon = True
    thread.start()

def run_schedule(app):
    print("--- Background Scheduler Started ---")
    while True:
        with app.app_context():
            check_upcoming_reminders()
        # Check every hour
        time.sleep(3600)

def check_upcoming_reminders():
    """Finds confirmed appointments for tomorrow and flags them for a call."""
    try:
        # Logic: Find appointments 24 hours from now (roughly)
        now = datetime.now()
        tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        tomorrow_end = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59)

        # Fetch confirmed appointments for tomorrow
        res = supabase.table('master_appointments')\
            .select('appointment_id, status, patients(full_name, phone_number)')\
            .eq('status', 'confirmed')\
            .gte('appointment_datetime', tomorrow_start.isoformat())\
            .lte('appointment_datetime', tomorrow_end.isoformat())\
            .execute()
        
        appointments = res.data or []
        
        if appointments:
            print(f"Scheduler: Found {len(appointments)} reminders to send.")
            for appt in appointments:
                # In a real app, this is where you'd trigger the Call API
                # For now, we update the status to 'calling' so volunteers see it happening
                supabase.table('master_appointments').update({
                    'status': 'calling',
                    'last_call_timestamp': datetime.now().isoformat()
                }).eq('appointment_id', appt['appointment_id']).execute()
                
                print(f" -> Triggered reminder for {appt['patients']['full_name']}")
    except Exception as e:
        print(f"Scheduler Error: {e}")
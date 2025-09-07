import os
import json
from supabase import create_client, Client
from dotenv import load_dotenv

def seed_locations():
    """
    Reads the location.json file and populates the states and lgas tables.
    """
    load_dotenv()
    
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    supabase: Client = create_client(supabase_url, supabase_key)

    print("Deleting existing location data to ensure a clean seed...")
    supabase.table('lgas').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
    supabase.table('states').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
    print("Existing data cleared.")

    with open('location.json', 'r') as f:
        data = json.load(f)

    for location in data['locations']:
        state_name = location['state'].title()
        # Use a set to automatically handle any duplicate LGAs in the JSON file
        lgas = {lga.strip().title() for lga in location['localGovt']}

        try:
            print(f"Processing State: {state_name}")
            state_res = supabase.table('states').insert({'name': state_name}).execute()
            state_id = state_res.data[0]['id']

            lgas_to_insert = [{'name': lga, 'state_id': state_id} for lga in lgas]
            
            if lgas_to_insert:
                supabase.table('lgas').insert(lgas_to_insert).execute()
                print(f"  -> Inserted {len(lgas_to_insert)} LGAs.")
        except Exception as e:
            print(f"Could not process {state_name}: {e}")

if __name__ == '__main__':
    seed_locations()
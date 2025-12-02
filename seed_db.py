import os
import google.generativeai as genai
from supabase import create_client
from dotenv import load_dotenv

# 1. Load Config
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("Error: Missing environment variables. Check .env file.")
    exit()

# 2. Initialize Clients
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# 3. Sample Health Data (Add more as needed)
health_docs = [
    {
        "content": "Antenatal care (ANC) is the care you get from health professionals during your pregnancy. It's sometimes called pregnancy care or maternity care. You should start ANC as soon as you know you're pregnant.",
        "metadata": {"source": "NHS Guide", "topic": "Antenatal"}
    },
    {
        "content": "Danger signs in pregnancy include: severe headache, blurred vision, convulsions (fits), severe abdominal pain, vaginal bleeding, and fever. If you experience any of these, go to the hospital immediately.",
        "metadata": {"source": "WHO Maternal Health", "topic": "Emergency"}
    },
    {
        "content": "Exclusive breastfeeding is recommended for the first 6 months of life. It provides all the nutrients a baby needs for growth and development.",
        "metadata": {"source": "UNICEF Nutrition", "topic": "Postnatal"}
    },
    {
        "content": "Childhood immunization schedule in Nigeria: BCG and OPV0 at birth; OPV1, Penta1, PCV1 at 6 weeks; OPV2, Penta2, PCV2 at 10 weeks; OPV3, Penta3, PCV3 at 14 weeks; Vitamin A and Measles at 9 months.",
        "metadata": {"source": "NPHCDA Schedule", "topic": "Immunization"}
    }
]

def seed_database():
    print("--- Starting Knowledge Base Seeding ---")
    for doc in health_docs:
        try:
            print(f"Embedding: {doc['metadata']['topic']}...")
            # Generate Embedding using Gemini
            result = genai.embed_content(
                model="models/embedding-001",
                content=doc['content'],
                task_type="retrieval_document",
                title=doc['metadata']['topic']
            )
            embedding = result['embedding']
            
            # Insert into Supabase
            data = {
                "content": doc['content'],
                "metadata": doc['metadata'],
                "embedding": embedding
            }
            supabase.table("documents").insert(data).execute()
            print(" -> Success")
            
        except Exception as e:
            print(f" -> Failed: {e}")

    print("--- Seeding Complete ---")

if __name__ == "__main__":
    seed_database()
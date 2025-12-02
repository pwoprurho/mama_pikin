import os
import glob
import time
import random
from pypdf import PdfReader
import google.generativeai as genai
from supabase import create_client
from dotenv import load_dotenv

# 1. Load Environment Variables
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("Error: Missing keys. Ensure SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and GEMINI_API_KEY are set.")
    exit()

# 2. Initialize Clients
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

def clean_text(text):
    """Basic text cleaning."""
    if not text: return ""
    return " ".join(text.split())

def embed_with_retry(content, title, max_retries=7):
    """
    Tries to generate an embedding. If it hits a Rate Limit (429),
    it waits exponentially longer (4s, 8s, 16s...) before retrying.
    """
    for attempt in range(max_retries):
        try:
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=content,
                task_type="retrieval_document",
                title=title
            )
            return result['embedding']
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                # Calculate wait time: 2^attempt + random jitter
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"   [Rate Limit Hit] Cooling down for {wait_time:.1f} seconds...", end="", flush=True)
                time.sleep(wait_time)
                print(" Retrying.")
            else:
                # If it's not a rate limit error (e.g., connection lost), print and give up on this chunk
                print(f"   [Error] Failed to embed: {e}")
                return None
    
    print("   [Failed] Exceeded max retries for this page.")
    return None

def process_pdfs():
    # Looks for PDFs in the knowledge_base folder
    pdf_files = glob.glob("knowledge_base/*.pdf")
    
    if not pdf_files:
        print("No PDF files found in 'knowledge_base/' folder.")
        return

    print(f"--- Found {len(pdf_files)} PDF(s). Starting Smart Processing... ---")

    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        print(f"\nProcessing File: {filename}")
        
        try:
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)
            
            for i, page in enumerate(reader.pages):
                page_num = i + 1
                raw_text = page.extract_text()
                content = clean_text(raw_text)

                if len(content) < 50:
                    print(f"  Skipping Page {page_num} (Text too short)")
                    continue

                print(f"  Embedding Page {page_num}/{total_pages}...", end="", flush=True)

                # Get Embedding with Retry Logic
                embedding = embed_with_retry(content, f"{filename} - Page {page_num}")
                
                if embedding:
                    # Insert into Supabase
                    data = {
                        "content": content,
                        "metadata": {
                            "source": filename,
                            "page": page_num,
                            "type": "pdf"
                        },
                        "embedding": embedding
                    }
                    try:
                        supabase.table("documents").insert(data).execute()
                        print(" Done.")
                    except Exception as db_err:
                        print(f" DB Error: {db_err}")

                # MANDATORY PAUSE: Even on success, wait 4 seconds to stay under ~15 RPM limit
                time.sleep(4) 

        except Exception as e:
            print(f"Failed to read PDF {filename}: {e}")

    print("\n--- Knowledge Base Update Complete ---")

if __name__ == "__main__":
    process_pdfs()
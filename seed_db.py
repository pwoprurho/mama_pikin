import os
import pdfplumber
import google.generativeai as genai
from supabase import create_client, Client
from dotenv import load_dotenv

# --- CONFIGURATION ---
PDF_PATH = r"C:\Users\Administrator\mama_pikin\14.DavidWerner-WhereThereIsNoDoctor.pdf"
CHUNK_SIZE = 500  # Number of characters per chunk
CHUNK_OVERLAP = 50 # Number of characters to overlap between chunks

def embed_book():
    load_dotenv()
    
    # Initialize clients
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    supabase: Client = create_client(supabase_url, supabase_key)
    
    print("Step 1: Reading and chunking the PDF...")
    # Read PDF and split into chunks
    full_text = ""
    with pdfplumber.open(PDF_PATH) as pdf:
        for page in pdf.pages:
            full_text += page.extract_text() + "\n"
    
    chunks = []
    start = 0
    while start < len(full_text):
        end = start + CHUNK_SIZE
        chunks.append(full_text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP

    print(f"PDF processed into {len(chunks)} chunks.")
    
    print("Step 2: Generating embeddings and storing in Supabase...")
    for i, chunk in enumerate(chunks):
        try:
            # Generate embedding for the chunk
            embedding_response = genai.embed_content(
                model="models/embedding-001",
                content=chunk,
                task_type="retrieval_document"
            )
            embedding = embedding_response['embedding']
            
            # Store the chunk and its embedding in the database
            supabase.table('documents').insert({
                'content': chunk,
                'embedding': embedding
            }).execute()
            
            print(f"  -> Stored chunk {i + 1}/{len(chunks)}")
        except Exception as e:
            print(f"Error on chunk {i + 1}: {e}")

    print("\nEmbedding process complete!")

if __name__ == '__main__':
    embed_book()
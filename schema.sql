-- 1. Enable Required Extensions (for AI/Vector Search)
CREATE EXTENSION IF NOT EXISTS vector;

-- ==========================================
-- 2. LOCATION TABLES
-- ==========================================
CREATE TABLE states ( 
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), 
    name TEXT NOT NULL UNIQUE 
);

CREATE TABLE lgas ( 
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), 
    name TEXT NOT NULL, 
    state_id UUID NOT NULL REFERENCES states(id) ON DELETE CASCADE, 
    UNIQUE(name, state_id) 
);

-- ==========================================
-- 3. USER MANAGEMENT (Volunteers)
-- ==========================================
CREATE TABLE volunteers ( 
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE, -- Links to Supabase Auth
    full_name TEXT NOT NULL, 
    email TEXT NOT NULL UNIQUE, 
    role TEXT CHECK (role IN ('volunteer', 'local', 'state', 'national', 'supa_user')) DEFAULT 'volunteer', 
    state_id UUID REFERENCES states(id), 
    lga_id UUID REFERENCES lgas(id), 
    spoken_languages TEXT[] DEFAULT '{"English"}', 
    phone_number TEXT, 
    created_at TIMESTAMPTZ DEFAULT now(), 
    updated_at TIMESTAMPTZ DEFAULT now() 
);

-- ==========================================
-- 4. PATIENT RECORDS
-- ==========================================
CREATE TABLE patients ( 
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), 
    full_name TEXT NOT NULL, 
    phone_number TEXT NOT NULL, -- Removed UNIQUE to allow re-registration if needed, or keep based on pref
    lga_id UUID REFERENCES lgas(id), 
    gender TEXT CHECK (gender IN ('Male', 'Female')), 
    age INT CHECK (age > 0), 
    blood_group TEXT CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')), 
    genotype TEXT CHECK (genotype IN ('AA', 'AS', 'SS', 'AC', 'SC')), 
    emergency_contact_name TEXT, 
    emergency_contact_phone TEXT, 
    spoken_languages TEXT[] DEFAULT '{}',
    registered_by UUID REFERENCES volunteers(id),
    created_at TIMESTAMPTZ DEFAULT now(), 
    updated_at TIMESTAMPTZ DEFAULT now() 
);
CREATE INDEX idx_patients_phone ON patients(phone_number);
CREATE INDEX idx_patients_lga ON patients(lga_id);

-- ==========================================
-- 5. APPOINTMENTS & OPERATIONS
-- ==========================================
CREATE TABLE master_appointments ( 
    appointment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), 
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE, 
    appointment_datetime TIMESTAMPTZ NOT NULL, 
    service_type TEXT, 
    preferred_language TEXT DEFAULT 'English', 
    status TEXT CHECK (status IN ('pending', 'confirmed', 'rescheduled', 'transferred', 'unreachable', 'calling', 'human_escalation', 'failed_escalation', 'completed')) DEFAULT 'pending', 
    handled_by_ai BOOLEAN DEFAULT TRUE, 
    volunteer_id UUID REFERENCES volunteers(id), 
    volunteer_notes TEXT, 
    patient_call_attempts INT DEFAULT 0, 
    last_call_timestamp TIMESTAMPTZ, 
    created_at TIMESTAMPTZ DEFAULT now(), 
    updated_at TIMESTAMPTZ DEFAULT now() 
);
CREATE INDEX idx_appt_date ON master_appointments(appointment_datetime);
CREATE INDEX idx_appt_status ON master_appointments(status);

-- ==========================================
-- 6. AI KNOWLEDGE BASE (Chatbot RAG)
-- ==========================================
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}', -- Stores source, topic, page number, etc.
    embedding vector(768)        -- Matches Gemini Embedding Dimension
);

-- Function to search documents (Used by api.py)
CREATE OR REPLACE FUNCTION match_documents (
  query_embedding vector(768),
  match_threshold float,
  match_count int
)
RETURNS TABLE (
  id UUID,
  content TEXT,
  metadata JSONB,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    documents.id,
    documents.content,
    documents.metadata,
    1 - (documents.embedding <=> query_embedding) AS similarity
  FROM documents
  WHERE 1 - (documents.embedding <=> query_embedding) > match_threshold
  ORDER BY documents.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- ==========================================
-- 7. PUBLIC CONTENT (Videos & Donations)
-- ==========================================
CREATE TABLE public_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT,
    youtube_id TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    added_by UUID REFERENCES volunteers(id),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE public_donations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    donor_name TEXT,
    amount NUMERIC NOT NULL, -- Stored in lowest currency unit (e.g., Kobo)
    message TEXT,
    status TEXT CHECK (status IN ('success', 'failed', 'pending')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE public_stats ( 
    stat_key TEXT PRIMARY KEY, 
    stat_value BIGINT NOT NULL 
);

CREATE TABLE app_settings ( 
    setting_key TEXT PRIMARY KEY, 
    setting_value TEXT NOT NULL 
);

-- ==========================================
-- 8. ROW LEVEL SECURITY (RLS) POLICIES
-- ==========================================

-- A. Enable RLS on sensitive tables
ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE master_appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE volunteers ENABLE ROW LEVEL SECURITY;

-- B. Volunteers Policies
-- Users can read their own profile
CREATE POLICY "Users can view own profile" ON volunteers
FOR SELECT USING (auth.uid() = id);

-- Supa Users can view all volunteers
CREATE POLICY "Supa Users view all" ON volunteers
FOR SELECT USING (
  exists (select 1 from volunteers where id = auth.uid() and role = 'supa_user')
);

-- C. Patients Policies
-- 1. National/Supa Users can see ALL patients
CREATE POLICY "National view all patients" ON patients
FOR SELECT USING (
  exists (select 1 from volunteers v where v.id = auth.uid() and v.role IN ('national', 'supa_user'))
);

-- 2. State Users can see patients in their STATE
CREATE POLICY "State view state patients" ON patients
FOR SELECT USING (
  exists (
    select 1 from volunteers v 
    join lgas l on patients.lga_id = l.id
    where v.id = auth.uid() and v.role = 'state' and v.state_id = l.state_id
  )
);

-- 3. Local/Volunteer Users can see/edit patients in their LGA
CREATE POLICY "Local view lga patients" ON patients
FOR SELECT USING (
  exists (
    select 1 from volunteers v 
    where v.id = auth.uid() and (v.role = 'local' OR v.role = 'volunteer') and v.lga_id = patients.lga_id
  )
);

-- 4. REGISTRATION RESTRICTION (Fixes the error in views.py)
-- Volunteers can only INSERT patients into their own LGA
CREATE POLICY "Register patients in own LGA" ON patients
FOR INSERT WITH CHECK (
  exists (
    select 1 from volunteers v 
    where v.id = auth.uid() and v.lga_id = patients.lga_id
  )
  OR
  exists (select 1 from volunteers v where v.id = auth.uid() and v.role IN ('national', 'supa_user'))
);

-- ==========================================
-- 9. INITIAL DATA
-- ==========================================
INSERT INTO app_settings (setting_key, setting_value) VALUES 
('GEMINI_API_KEY', ''),
('DISPLAY_TOTAL_DONATIONS', 'true');

INSERT INTO public_stats (stat_key, stat_value) VALUES 
('appointments_confirmed', 0),
('patients_registered', 0),
('states_covered', 0);
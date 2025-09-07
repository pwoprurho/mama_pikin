-- Location Tables
CREATE TABLE states ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(), name TEXT NOT NULL UNIQUE );
CREATE TABLE lgas ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(), name TEXT NOT NULL, state_id UUID NOT NULL REFERENCES states(id), UNIQUE(name, state_id) );
-- User/Volunteer Table
CREATE TABLE volunteers ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(), full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password TEXT NOT NULL, role TEXT CHECK (role IN ('volunteer', 'local', 'state', 'national', 'supa_user')) DEFAULT 'volunteer', state_id UUID REFERENCES states(id), lga_id UUID REFERENCES lgas(id), spoken_languages TEXT[] DEFAULT '{"English"}', phone_number TEXT, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now() );
CREATE UNIQUE INDEX idx_volunteers_email ON volunteers (email);
-- Patient Table
CREATE TABLE patients ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(), full_name TEXT NOT NULL, phone_number TEXT NOT NULL UNIQUE, lga_id UUID REFERENCES lgas(id), gender TEXT CHECK (gender IN ('Male', 'Female')), age INT CHECK (age > 0), blood_group TEXT CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')), genotype TEXT CHECK (genotype IN ('AA', 'AS', 'SS', 'AC', 'SC')), emergency_contact_name TEXT, emergency_contact_phone TEXT, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now() );
CREATE INDEX idx_patients_phone_number ON patients (phone_number);
-- Appointments Table
CREATE TABLE master_appointments ( appointment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), patient_id UUID NOT NULL REFERENCES patients(id), appointment_datetime TIMESTAMPTZ NOT NULL, service_type TEXT, preferred_language TEXT DEFAULT 'English', status TEXT CHECK (status IN ('pending', 'confirmed', 'rescheduled', 'transferred', 'unreachable', 'calling', 'human_escalation', 'failed_escalation', 'completed')) DEFAULT 'pending', handled_by_ai BOOLEAN DEFAULT TRUE, volunteer_id UUID REFERENCES volunteers(id), volunteer_notes TEXT, patient_call_attempts INT DEFAULT 0, last_call_timestamp TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now() );
CREATE INDEX idx_appointments_patient_id ON master_appointments (patient_id);
-- App Settings & Public Stats
CREATE TABLE app_settings ( setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL );
CREATE TABLE public_stats ( stat_key TEXT PRIMARY KEY, stat_value BIGINT NOT NULL );
-- Initial Data
INSERT INTO app_settings (setting_key, setting_value) VALUES ('GEMINI_API_KEY', '');
INSERT INTO public_stats (stat_key, stat_value) VALUES ('appointments_confirmed', 0),('patients_registered', 0),('states_covered', 0);
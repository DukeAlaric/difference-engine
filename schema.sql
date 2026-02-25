-- Difference Engine — Supabase Schema
-- Run this in Supabase SQL Editor (left sidebar → SQL Editor → New Query)

-- Users (simple, no auth — just a username)
CREATE TABLE users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Projects (one user can have multiple novels)
CREATE TABLE projects (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, name)
);

-- Bibles (one per project, stored as markdown text)
CREATE TABLE bibles (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE UNIQUE,
    content TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Baselines (one per project, stored as JSON)
CREATE TABLE baselines (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE UNIQUE,
    metrics JSONB NOT NULL DEFAULT '{}',
    corpus_word_count INTEGER DEFAULT 0,
    built_at TIMESTAMPTZ DEFAULT now()
);

-- Corpus files (user's uploaded writing samples)
CREATE TABLE corpus_files (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    word_count INTEGER DEFAULT 0,
    uploaded_at TIMESTAMPTZ DEFAULT now()
);

-- Chapters (produced output)
CREATE TABLE chapters (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    chapter_key TEXT NOT NULL,
    chapter_title TEXT,
    version INTEGER DEFAULT 1,
    content TEXT NOT NULL,
    word_count INTEGER DEFAULT 0,
    quality_score INTEGER,
    quality_report JSONB,
    voice_delta JSONB,
    hotspots JSONB,
    manifest JSONB,
    produced_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(project_id, chapter_key, version)
);

-- Simple cost tracking
CREATE TABLE api_usage (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    chapter_key TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    estimated_cost NUMERIC(10,4) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS and allow all (no auth, trusted users only)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE bibles ENABLE ROW LEVEL SECURITY;
ALTER TABLE baselines ENABLE ROW LEVEL SECURITY;
ALTER TABLE corpus_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE chapters ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all" ON users FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all" ON projects FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all" ON bibles FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all" ON baselines FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all" ON corpus_files FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all" ON chapters FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all" ON api_usage FOR ALL USING (true) WITH CHECK (true);

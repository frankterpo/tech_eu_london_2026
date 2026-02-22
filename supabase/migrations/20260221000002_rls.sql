-- Disable RLS for hackathon speed (or you can add proper policies later)
ALTER TABLE runs DISABLE ROW LEVEL SECURITY;
ALTER TABLE skills DISABLE ROW LEVEL SECURITY;

-- Allow all storage access for now
CREATE POLICY "Allow all" ON storage.objects FOR ALL USING (true) WITH CHECK (true);

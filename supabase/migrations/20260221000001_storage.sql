-- Create storage buckets
INSERT INTO storage.buckets (id, name, public) VALUES ('artifacts', 'artifacts', false) ON CONFLICT (id) DO NOTHING;
INSERT INTO storage.buckets (id, name, public) VALUES ('auth', 'auth', false) ON CONFLICT (id) DO NOTHING;

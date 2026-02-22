CREATE TABLE runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','success','failed','error')),
  skill_id TEXT,
  skill_version INTEGER,
  prompt TEXT,
  slots JSONB,
  artifacts JSONB DEFAULT '{}',
  error TEXT,
  eval_key TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE skills (
  id TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  spec JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (id, version)
);

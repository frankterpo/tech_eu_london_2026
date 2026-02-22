from agent.config import config

def test_config_dirs():
    assert config.ARTIFACT_DIR.name == "artifacts"
    assert config.RUNS_DIR.name == "runs"
    assert config.AUTH_DIR.name == "auth"

def test_config_env_vars():
    # These should be loaded from .env during tests if .env exists
    assert config.GEMINI_MODEL == "gemini-2.5-flash"
    assert config.ENVOICE_BASE_URL == "https://app.envoice.eu"

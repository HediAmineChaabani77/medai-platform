from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret: str = "dev-secret-change-me"
    audit_hmac_key: str = "dev-audit-key"
    jwt_secret: str = "dev-jwt-secret"
    jwt_exp_minutes: int = 480

    database_url: str = "postgresql+psycopg://medai:medai@postgres:5432/medai"

    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "medical_qa_only"

    ollama_host: str = "http://ollama:11434"
    llm_local_model: str = "llama3.1:8b-instruct"
    llm_embed_model: str = "nomic-embed-text"

    llm_cloud_provider: str = "openai"
    llm_cloud_model: str = "gpt-4o-mini"
    llm_cloud_base_url: str = "https://api.openai.com/v1"
    llm_cloud_api_key: str = ""

    connectivity_probe_url: str = "https://1.1.1.1"
    connectivity_probe_interval: int = 15

    router_local_queue_threshold: int = 5
    router_text_len_threshold: int = 8000

    force_local_only: bool = True

    # Admin auth / MFA
    admin_auth_required: bool = True
    admin_mfa_required: bool = True
    auth_dev_seed_admin: bool = True
    auth_admin_username: str = "admin"
    auth_admin_password: str = "admin123"
    # Deterministic dev TOTP secret (Base32). Replace in production.
    auth_admin_totp_secret: str = "JBSWY3DPEHPK3PXP"

    # DMP / DPI integration stubs (optional files outside the indexed dataset directory)
    dmp_data_path: str = "/tmp/medai_dmp/patients.json"
    dpi_archive_dir: str = "/tmp/medai_dpi_archive"


@lru_cache
def get_settings() -> Settings:
    return Settings()

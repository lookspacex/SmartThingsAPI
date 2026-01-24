from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    app_env: str = "dev"  # dev|prod

    # SmartThings
    # Optional: you may also provide token per-request via headers.
    smartthings_token: Optional[str] = None
    smartthings_base_url: str = "https://api.smartthings.com/v1"
    smartthings_timeout_s: float = 15.0

    # SaaS / DB
    database_url: str = "sqlite:///./smartthingsapi.db"
    api_key_pepper: str = "change-me"  # used to hash API keys at rest
    oauth_state_secret: str = "change-me-too"  # used to sign OAuth state

    # HTTP / CORS
    cors_allow_origins: str = "*"  # comma-separated or "*"

    # SmartThings OAuth (SaaS mode)
    smartthings_client_id: Optional[str] = None
    smartthings_client_secret: Optional[str] = None
    smartthings_redirect_uri: Optional[str] = None
    smartthings_oauth_authorize_url: str = "https://api.smartthings.com/oauth/authorize"
    smartthings_oauth_token_url: str = "https://api.smartthings.com/oauth/token"
    smartthings_oauth_scope: str = "r:devices:* x:devices:* r:locations:*"

    # Server
    app_name: str = "SmartThingsAPI"


settings = Settings()


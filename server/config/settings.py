"""Environment configuration.

Every field is required, so a missing variable
fails loudly at import time with a pydantic ValidationError naming it, rather
than silently running on a fallback value.

Variables belonging to later build steps are added by those steps, so the app
always boots against the environment it actually needs today.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str
    log_level: str
    database_url: str

    #: Echo every statement and its bound parameters to the log. Keep off
    #: outside local debugging: the users table holds email, display name
    #: and Google subject id, and data_points will hold measurements.
    sql_echo: bool

    # --- Google OAuth ---
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    # --- Secrets, hex encoded: openssl rand -hex 32 ---
    token_encryption_key: str
    session_secret: str

    # --- CORS: exact origins allowed to send credentialed requests ---
    # Comma separated. Never '*' -- browsers reject a wildcard when
    # credentials are included.
    cors_origins: str

    # --- Webhook subscriber ---
    # Subscriber management is a project-level API authorised by a service
    # account, not by the per-user OAuth tokens.
    gcp_project_number: str
    google_application_credentials: str
    subscriber_id: str
    #: Registered with Google and echoed back in the Authorization header of
    #: every notification.
    webhook_auth_secret: str
    #: Public HTTPS origin Google delivers to.
    webhook_public_url: str

    # --- Message queue ---
    nats_url: str

    # --- Orchestration ---
    #: Prefect's REST API, e.g. http://localhost:4200/api. The web process talks
    #: to it over HTTP rather than importing `prefect`, which would pull ~50
    #: packages it never serves a request with.
    prefect_api_url: str
    #: The fetcher deployment to start a run of. Created by
    #: `server.flows.fetch:deploy`, which prints the id.
    prefect_deployment_id: str

    # --- Session cookie ---
    session_ttl_minutes: int
    cookie_secure: bool
    frontend_url: str

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()

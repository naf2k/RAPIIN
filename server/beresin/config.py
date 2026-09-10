"""Central configuration loaded from environment / .env file."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    # Server
    beresin_db_path: str = "./data/beresin.db"
    beresin_database_url: str = ""
    beresin_redis_url: str = ""
    beresin_embedded_queue_worker: bool = False
    beresin_data_dir: str = "./data"
    beresin_secret_key: str = "dev-secret-change-me"
    beresin_host: str = "127.0.0.1"
    beresin_port: int = 8000
    beresin_env: str = "development"
    beresin_allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    beresin_secret_key_file: str = ""
    beresin_init_supervisor_password_file: str = ""
    beresin_monitoring_token: str = ""
    beresin_monitoring_token_file: str = ""
    beresin_allow_public_registration: bool = True
    # AI router (OpenAI-compatible). 9router is used as the V1 provider.
    ai_base_url: str = "http://localhost:20128/v1"
    ai_api_key: str = ""
    ai_api_key_file: str = ""
    ai_model: str = "ai-rapiin"
    ai_timeout_seconds: float = 120.0
    ai_max_iterations: int = 12
    ai_max_retries: int = 5

    # Operations Center. External integrations are opt-in and fail closed.
    ops_agents_enabled: bool = False
    ops_hermes_command: str = "hermes"
    ops_hermes_version: str = "v0.21.0"
    ops_hermes_commit: str = "95d42656021a22f20201c618a67da07a618d16f3"
    ops_agent_timeout_seconds: int = 180
    ops_agent_daily_run_limit: int = 100
    ops_agent_daily_cost_limit_usd: float = 10.0
    ops_agent_monthly_cost_limit_usd: float = 100.0
    ops_agent_max_concurrency: int = 1
    ops_agent_failure_threshold: int = 3
    ops_agent_circuit_cooldown_seconds: int = 900
    ops_retention_days: int = 90
    ops_telegram_bot_token: str = ""
    ops_telegram_bot_token_file: str = ""
    ops_telegram_chat_id: str = ""
    ops_public_base_url: str = "http://127.0.0.1:8000"
    ops_github_repo: str = "naf2k/BERESIN"
    ops_worktree_root: str = ""
    ops_deploy_command: str = ""
    ops_rollback_command: str = ""
    ops_health_url: str = "http://127.0.0.1:8000/ready"

    # Seeded accounts
    beresin_init_supervisor_email: str = "supervisor@beresin.example.com"
    beresin_init_supervisor_password: str = "Supervisor123!"

    @property
    def db_path(self) -> Path:
        path = Path(self.beresin_db_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path

    @property
    def data_dir(self) -> Path:
        path = Path(self.beresin_data_dir)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.beresin_allowed_origins.split(",") if origin.strip()]

    def validate_for_startup(self) -> None:
        for value_field, file_field in (
            ("beresin_secret_key", "beresin_secret_key_file"),
            ("beresin_init_supervisor_password", "beresin_init_supervisor_password_file"),
            ("beresin_monitoring_token", "beresin_monitoring_token_file"),
            ("ai_api_key", "ai_api_key_file"),
            ("ops_telegram_bot_token", "ops_telegram_bot_token_file"),
        ):
            secret_path = getattr(self, file_field)
            if secret_path:
                try:
                    resolved_secret = Path(secret_path)
                    if not resolved_secret.is_absolute():
                        resolved_secret = BASE_DIR / resolved_secret
                    setattr(self, value_field, resolved_secret.read_text(encoding="utf-8").strip())
                except OSError as exc:
                    raise RuntimeError(f"Secret file tidak dapat dibaca: {file_field}") from exc
        if self.beresin_env.lower() != "production":
            return
        errors = []
        if self.beresin_secret_key in {"dev-secret-change-me", "change-me-in-production", ""} or len(self.beresin_secret_key) < 32:
            errors.append("BERESIN_SECRET_KEY wajib unik dan minimal 32 karakter")
        if self.beresin_init_supervisor_email == "supervisor@beresin.example.com":
            errors.append("email supervisor production wajib diganti")
        if self.beresin_init_supervisor_password == "Supervisor123!" or len(self.beresin_init_supervisor_password) < 12:
            errors.append("password supervisor production wajib unik dan minimal 12 karakter")
        if any(origin.startswith("http://") and "localhost" not in origin and "127.0.0.1" not in origin for origin in self.allowed_origins):
            errors.append("origin production non-local wajib HTTPS")
        if not self.allowed_origins:
            errors.append("minimal satu origin production wajib dikonfigurasi")
        if len(self.beresin_monitoring_token) < 32:
            errors.append("BERESIN_MONITORING_TOKEN wajib minimal 32 karakter")
        if self.beresin_allow_public_registration:
            errors.append("BERESIN_ALLOW_PUBLIC_REGISTRATION wajib false di production")
        if self.ops_agent_max_concurrency < 1 or self.ops_agent_max_concurrency > 8:
            errors.append("OPS_AGENT_MAX_CONCURRENCY wajib antara 1 dan 8")
        if self.ops_agent_daily_run_limit < self.ops_agent_max_concurrency:
            errors.append("OPS_AGENT_DAILY_RUN_LIMIT tidak boleh lebih kecil dari concurrency")
        if self.ops_agent_daily_cost_limit_usd <= 0:
            errors.append("OPS_AGENT_DAILY_COST_LIMIT_USD wajib lebih besar dari nol")
        if self.ops_agent_monthly_cost_limit_usd < self.ops_agent_daily_cost_limit_usd:
            errors.append("OPS_AGENT_MONTHLY_COST_LIMIT_USD tidak boleh lebih kecil dari batas harian")
        if self.ops_agent_timeout_seconds < 30 or self.ops_agent_timeout_seconds > 900:
            errors.append("OPS_AGENT_TIMEOUT_SECONDS wajib antara 30 dan 900 detik")
        if self.ops_agent_failure_threshold < 1 or self.ops_agent_failure_threshold > 20:
            errors.append("OPS_AGENT_FAILURE_THRESHOLD wajib antara 1 dan 20")
        if self.ops_retention_days < 30:
            errors.append("OPS_RETENTION_DAYS minimal 30 hari")
        if self.ops_agents_enabled and not self.ops_hermes_commit:
            errors.append("OPS_HERMES_COMMIT wajib dipin saat Operations Agent aktif")
        if self.ops_telegram_bot_token and not self.ops_telegram_chat_id:
            errors.append("OPS_TELEGRAM_CHAT_ID wajib saat Telegram aktif")
        if self.ops_telegram_bot_token and not self.ops_public_base_url.startswith("https://"):
            errors.append("OPS_PUBLIC_BASE_URL wajib HTTPS saat Telegram aktif di production")
        if bool(self.beresin_database_url) != bool(self.beresin_redis_url):
            errors.append("BERESIN_DATABASE_URL dan BERESIN_REDIS_URL wajib diaktifkan bersama di production")
        if self.beresin_redis_url and self.beresin_embedded_queue_worker:
            errors.append("BERESIN_EMBEDDED_QUEUE_WORKER wajib false saat Redis digunakan di production")
        if errors:
            raise RuntimeError("Konfigurasi production tidak aman: " + "; ".join(errors))


settings = Settings()

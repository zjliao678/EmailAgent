from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # IMAP — QQ Mail
    imap_host: str = "imap.qq.com"
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""  # QQ auth code (授权码), not the login password

    # SMTP — QQ Mail
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""  # QQ auth code

    # Database
    database_url: str = "sqlite:///./email_agent.db"

    # Task queue
    redis_url: str = "redis://localhost:6379/0"

    # LLM — DeepSeek (OpenAI-compatible API)
    deepseek_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-flash"
    llm_temperature: float = 0.0

    # Security
    attachment_max_bytes: int = 10 * 1024 * 1024  # 10 MB


@lru_cache
def get_settings() -> Settings:
    return Settings()

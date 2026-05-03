from fastapi.openapi.models import APIKey
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_ENV: str = "local"
    DATABASE_URL: str
    VERSION: str = "1.0.0"

    REDIS_URL: str | None = None
    JWT_SECRET: str = "change-me"
    JWT_ALG: str = "HS256"
    JWT_EXPIRES_MIN: int = 120
    JWT_ISSUER: str = "fin-api"

    EMAIL_FROM: str

    FRONTEND_URL: str = "http://localhost:3000"
    API_BASE_URL: str = "http://localhost:8000"
    GEMINI_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    SENTRY_DSN: str | None = None
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    RESEND_API_KEY: str | None = None


settings = Settings()

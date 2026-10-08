from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://northstar:northstar@localhost:5433/northstar"
    token_secret: str = "local-dev-token-secret-at-least-32-chars"
    console_origin: str = "http://localhost:3000"
    request_limit: int = 60
    daily_token_budget: int = 20_000

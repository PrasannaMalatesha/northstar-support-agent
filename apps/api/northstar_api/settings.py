from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://northstar:northstar@localhost:5433/northstar"
    token_secret: str = "local-dev-token-secret-at-least-32-chars"
    console_origin: str = "http://localhost:3000"
    request_limit: int = 60
    daily_token_budget: int = 20_000
    # Agent turns a day for each chat customer, and for all chat customers together (issue #134).
    chat_turns_per_customer: int = 10
    chat_turns_per_day: int = 500
    # Seconds per agent turn. Optional model steps are skipped when too little time is left (R36).
    turn_deadline_seconds: float = 45
    # Agent turns in a row that end in a clarification, an abstain, or a failed lookup before the
    # customer chat offers a person (R35).
    failed_turns_before_offer: int = Field(default=3, ge=1)
    # Live chat with a specialist (issue #138). Off by default: no live chat route or control,
    # and the chat behaves as before.
    live_agents_enabled: bool = False
    # Quiet customer in a live chat (issue #142): minutes after the specialist's last message with no
    # answer before "Are you still there?", before the live chat is idle and the slot is free, and
    # before it closes.
    quiet_nudge_minutes: float = Field(default=2, gt=0)
    quiet_idle_minutes: float = Field(default=3, gt=0)
    quiet_close_minutes: float = Field(default=15, gt=0)
    # Google single sign-on is on when this is set (issue #78). The same variable the console reads.
    google_client_id: str = Field(default="", validation_alias=AliasChoices("AUTH_GOOGLE_ID", "google_client_id"))

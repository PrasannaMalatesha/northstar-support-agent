from northstar import defaults
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://northstar:northstar@localhost:5433/northstar"
    token_secret: str = "local-dev-token-secret-at-least-32-chars"
    console_origin: str = "http://localhost:3000"
    request_limit: int = defaults.REQUEST_LIMIT
    daily_token_budget: int = defaults.DAILY_TOKEN_BUDGET
    # Agent turns a day for each chat customer, and for all chat customers together (issue #134).
    chat_turns_per_customer: int = defaults.CHAT_TURNS_PER_CUSTOMER
    chat_turns_per_day: int = defaults.CHAT_TURNS_PER_DAY
    # Seconds per agent turn. Optional model steps are skipped when too little time is left (R36).
    turn_deadline_seconds: float = defaults.TURN_DEADLINE_SECONDS
    # Agent turns in a row that end in a clarification, an abstain, or a failed lookup before the
    # customer chat follows up with a person (R35).
    failed_turns_before_follow_up: int = Field(default=defaults.FAILED_TURNS_BEFORE_FOLLOW_UP, ge=1)
    # Live chat with a specialist (issue #138). Off by default: no live chat route or control,
    # and the chat behaves as before.
    live_chat_enabled: bool = defaults.LIVE_CHAT_ENABLED
    # Live chats a specialist holds at once: the capacity a specialist starts with when they first set
    # Available (user story 61). A specialist's own capacity is kept after that.
    live_chats_per_specialist: int = Field(default=defaults.LIVE_CHATS_PER_SPECIALIST, ge=1)
    # Live chat offers (issue #139): seconds to accept an offer, offers before the customer may leave a
    # message instead, missed offers in a row before a specialist is set to Away, and how recently a
    # desk must have checked in for its specialist to get offers.
    offer_accept_seconds: float = Field(default=defaults.OFFER_ACCEPT_SECONDS, gt=0)
    offers_before_leave_message: int = Field(default=defaults.OFFERS_BEFORE_LEAVE_MESSAGE, ge=1)
    missed_offers_before_away: int = Field(default=defaults.MISSED_OFFERS_BEFORE_AWAY, ge=1)
    desk_check_in_seconds: float = Field(default=defaults.DESK_CHECK_IN_SECONDS, gt=0)
    # The line (issue #140, R40, R41). A waiting customer whose chat has not refreshed this long
    # leaves the line. Over the longest estimate, or with no specialist available, the customer is
    # offered to leave a message instead. The estimate uses the live chats of the last days, and
    # says "a few minutes" with fewer than this many.
    line_gone_minutes: float = defaults.LINE_GONE_MINUTES
    longest_wait_minutes: float = defaults.LONGEST_WAIT_MINUTES
    wait_history_days: int = defaults.WAIT_HISTORY_DAYS
    wait_history_chats: int = defaults.WAIT_HISTORY_CHATS
    # Quiet customer in a live chat (issue #142): minutes after the specialist's last message with no
    # answer before "Are you still there?", before the live chat is idle and the slot is free, and
    # before it closes.
    quiet_nudge_minutes: float = Field(default=defaults.QUIET_NUDGE_MINUTES, gt=0)
    quiet_idle_minutes: float = Field(default=defaults.QUIET_IDLE_MINUTES, gt=0)
    quiet_close_minutes: float = Field(default=defaults.QUIET_CLOSE_MINUTES, gt=0)
    # A customer in a live chat who has waited this long for the specialist's reply is flagged to leads
    # (issue #144, R49). The live chat is not reassigned.
    quiet_specialist_minutes: float = Field(default=defaults.QUIET_SPECIALIST_MINUTES, gt=0)
    # Google single sign-on is on when this is set (issue #78). The same variable the console reads.
    google_client_id: str = Field(default="", validation_alias=AliasChoices("AUTH_GOOGLE_ID", "google_client_id"))

"""Staff login, refresh, logout, and the current staff member."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Protocol

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from northstar.clock import Clock

ACCESS_MINUTES = 15
REFRESH_DAYS = 14
LOCKOUT_FAILURES = 5
LOCKOUT_MINUTES = 15
ISSUER = "northstar-api"
AUDIENCE = "northstar-console"
# Google single sign-on (issue #78). The API checks Google's signature itself; the role comes from staff_users.
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_KEYS_URL = "https://www.googleapis.com/oauth2/v3/certs"
# A customer chat token is a different audience, so it can never pass as a staff token (issue #79).
CHAT_AUDIENCE = "northstar-chat"
CHAT_MINUTES = 30

_hasher = PasswordHasher()


class LoginInvalid(Exception):
    """Email or password does not match a staff account."""


class LoginLocked(Exception):
    """Too many recent failures. The login stays closed until the window passes."""


class TokenInvalid(Exception):
    """The access or refresh token cannot be used."""


@dataclass(frozen=True)
class Staff:
    id: uuid.UUID
    email: str
    name: str
    role: str
    session_version: int
    password_hash: str
    disabled: bool


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    staff_id: uuid.UUID
    name: str
    role: str


class IdentityStore(Protocol):
    def get_by_email(self, email: str) -> Staff | None: ...

    def get_by_id(self, staff_id: uuid.UUID) -> Staff | None: ...

    def recent_failure_count(self, email: str, since: datetime) -> int: ...

    def record_attempt(self, email: str, success: bool, attempted_at: datetime) -> None: ...

    def save_refresh(
        self, staff_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None: ...

    def revoke_refresh(self, token_hash: str, revoked_at: datetime) -> uuid.UUID | None: ...

    def refresh_is_active(self, token_hash: str, now: datetime) -> uuid.UUID | None: ...

    def bump_session(self, staff_id: uuid.UUID) -> None: ...

    def audit(self, staff_id: uuid.UUID | None, event: str, at: datetime) -> None: ...


class Identity:
    def __init__(self, store: IdentityStore, clock: Clock, token_secret: str) -> None:
        self._store = store
        self._clock = clock
        self._secret = token_secret

    def audit(self, staff_id: uuid.UUID | None, event: str, at: datetime) -> None:
        self._store.audit(staff_id, event, at)

    def login(self, email: str, password: str) -> TokenPair:
        normalized = email.strip().lower()
        now = self._clock.now()
        if self._is_locked(normalized, now):
            self._store.audit(None, "login_locked", now)
            raise LoginLocked()

        staff = self._store.get_by_email(normalized)
        if staff is None or staff.disabled or not _password_ok(staff.password_hash, password):
            self._store.record_attempt(normalized, False, now)
            self._store.audit(None if staff is None else staff.id, "login_failure", now)
            if self._is_locked(normalized, now):
                raise LoginLocked()
            raise LoginInvalid()

        self._store.record_attempt(normalized, True, now)
        self._store.audit(staff.id, "login_success", now)
        return self._issue(staff, now)

    def refresh(self, refresh_token: str) -> TokenPair:
        now = self._clock.now()
        staff_id = self._store.revoke_refresh(_hash(refresh_token), now)
        if staff_id is None:
            raise TokenInvalid()
        staff = self._store.get_by_id(staff_id)
        if staff is None or staff.disabled:
            raise TokenInvalid()
        return self._issue(staff, now)

    def logout(self, refresh_token: str) -> None:
        now = self._clock.now()
        staff_id = self._store.revoke_refresh(_hash(refresh_token), now)
        if staff_id is None:
            raise TokenInvalid()
        self._store.bump_session(staff_id)
        self._store.audit(staff_id, "logout", now)

    def current_staff(self, access_token: str) -> Staff:
        try:
            payload = jwt.decode(
                access_token,
                self._secret,
                algorithms=["HS256"],
                issuer=ISSUER,
                audience=AUDIENCE,
                options={"verify_exp": False, "verify_iat": False},
            )
        except jwt.PyJWTError as exc:
            raise TokenInvalid() from exc
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        if self._clock.now() >= expires_at:
            raise TokenInvalid()
        staff = self._store.get_by_id(uuid.UUID(payload["sub"]))
        if staff is None or staff.disabled:
            raise TokenInvalid()
        if int(payload.get("sv", -1)) != staff.session_version:
            raise TokenInvalid()
        return staff

    def sso_login(self, id_token: str, client_id: str) -> TokenPair:
        """Staff tokens for a Google ID token, or LoginInvalid.

        Signature, audience, issuer, expiry, and a verified email are all checked here. The browser's
        word is never taken, and the identity provider never sets the role: the staff record does.
        """
        now = self._clock.now()
        try:
            claims = jwt.decode(
                id_token,
                _google_key(id_token),
                algorithms=["RS256"],
                audience=client_id,
                issuer=GOOGLE_ISSUERS,
                leeway=60,
            )
        except Exception as exc:
            self._store.audit(None, "sso_login_failure", now)
            raise LoginInvalid() from exc
        email = str(claims.get("email") or "").strip().lower()
        staff = self._store.get_by_email(email) if claims.get("email_verified") is True and email else None
        if staff is None or staff.disabled:
            self._store.audit(None if staff is None else staff.id, "sso_login_failure", now)
            raise LoginInvalid()
        self._store.audit(staff.id, "sso_login_success", now)
        return self._issue(staff, now)

    def start_chat(self, email: str, order_id: str, find_customer) -> str:
        """A chat token for the customer who owns this order and email, or LoginInvalid.

        Failures count toward the same lockout as staff logins, keyed by the email.
        """
        key = f"chat:{email.strip().lower()}"
        now = self._clock.now()
        if self._is_locked(key, now):
            self._store.audit(None, "chat_locked", now)
            raise LoginLocked()
        customer_id = find_customer(order_id, email)
        self._store.record_attempt(key, customer_id is not None, now)
        if customer_id is None:
            self._store.audit(None, "chat_failure", now)
            raise LoginInvalid()
        self._store.audit(None, "chat_start", now)
        return self.chat_token(customer_id)

    def chat_token(self, customer_id: uuid.UUID) -> str:
        """A chat token for this customer, valid for CHAT_MINUTES. Also the renewal during a live chat (R47)."""
        now = self._clock.now()
        return jwt.encode(
            {
                "sub": str(customer_id),
                "iss": ISSUER,
                "aud": CHAT_AUDIENCE,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=CHAT_MINUTES)).timestamp()),
            },
            self._secret,
            algorithm="HS256",
        )

    def chat_customer(self, token: str) -> uuid.UUID:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                issuer=ISSUER,
                audience=CHAT_AUDIENCE,
                options={"verify_exp": False, "verify_iat": False},
            )
        except jwt.PyJWTError as exc:
            raise TokenInvalid() from exc
        if self._clock.now() >= datetime.fromtimestamp(payload["exp"], tz=timezone.utc):
            raise TokenInvalid()
        return uuid.UUID(payload["sub"])

    def _is_locked(self, email: str, now: datetime) -> bool:
        since = now - timedelta(minutes=LOCKOUT_MINUTES)
        return self._store.recent_failure_count(email, since) >= LOCKOUT_FAILURES

    def _issue(self, staff: Staff, now: datetime) -> TokenPair:
        expires = now + timedelta(minutes=ACCESS_MINUTES)
        access = jwt.encode(
            {
                "sub": str(staff.id),
                "sv": staff.session_version,
                "iss": ISSUER,
                "aud": AUDIENCE,
                "iat": int(now.timestamp()),
                "exp": int(expires.timestamp()),
            },
            self._secret,
            algorithm="HS256",
        )
        refresh = secrets.token_urlsafe(32)
        self._store.save_refresh(
            staff.id,
            _hash(refresh),
            now + timedelta(days=REFRESH_DAYS),
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=ACCESS_MINUTES * 60,
            staff_id=staff.id,
            name=staff.name,
            role=staff.role,
        )


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def _password_ok(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def staff_id_for(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"northstar-staff:{email.strip().lower()}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@lru_cache(maxsize=1)
def _google_keys() -> jwt.PyJWKClient:
    # Google's published signing keys, fetched and cached by PyJWT.
    return jwt.PyJWKClient(GOOGLE_KEYS_URL, cache_keys=True)


def _google_key(id_token: str):
    return _google_keys().get_signing_key_from_jwt(id_token).key

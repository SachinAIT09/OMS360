"""Authentication (signed bearer tokens) and role-based permissions."""
import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import DB_PATH, get_session
from .models import RevokedToken, User, utcnow

ROLES = {
    "executive": "Executive",
    "ops_manager": "Operations Manager",
    "dispatcher": "Dispatcher",
    "comms": "Communications Lead",
    "admin": "Administrator",
}

# permission → roles that hold it
PERMISSIONS = {
    "events.manage": {"ops_manager", "admin"},
    "predictions.run": {"ops_manager", "executive", "admin"},
    "recommendations.decide": {"executive", "ops_manager", "admin"},
    "outages.manage": {"dispatcher", "ops_manager", "admin"},
    "crews.manage": {"dispatcher", "ops_manager", "admin"},
    "mutual_aid.manage": {"ops_manager", "admin"},
    "etr.publish": {"executive", "ops_manager", "admin"},
    "messages.create": {"comms", "ops_manager", "admin"},
    "messages.approve": {"executive", "comms", "ops_manager", "admin"},
    "tasks.manage": {"ops_manager", "dispatcher", "admin"},
    "admin": {"admin"},
}

TOKEN_TTL = timedelta(hours=12)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"pbkdf2${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, _ = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def permissions_for(role: str) -> list[str]:
    return sorted(p for p, roles in PERMISSIONS.items() if role in roles)


def _load_secret() -> bytes:
    """OMS360_SECRET in production (Render generates one), so tokens outlive restarts that wipe the database.
    Locally, a random secret kept next to the database."""
    if env := os.environ.get("OMS360_SECRET"):
        return env.encode()
    path = DB_PATH.parent / ".token_secret"
    try:
        return path.read_bytes()
    except OSError:
        key = secrets.token_hex(32).encode()
        try:
            path.write_bytes(key)
        except OSError:
            pass
        return key


SECRET = _load_secret()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _sign(payload: str) -> str:
    return _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())


def issue_token(s: Session, user: User) -> str:
    """`<payload>.<sig>` where payload is email|expiry|token id. Holds the email, not the user id, because a
    free-tier restart reseeds the database and ids may change."""
    exp = int((utcnow() + TOKEN_TTL).timestamp())
    payload = _b64(f"{user.email}|{exp}|{secrets.token_hex(8)}".encode())
    user.last_login_at = utcnow()
    s.commit()
    return f"{payload}.{_sign(payload)}"


def parse_token(token: str | None) -> tuple[str, datetime, str] | None:
    """(email, expires_at, jti) for a genuine, unexpired token."""
    if not token or token.count(".") != 1:
        return None
    payload, sig = token.split(".")
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        email, exp, jti = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().split("|")
        expires = datetime.fromtimestamp(int(exp), timezone.utc)
    except ValueError:
        return None
    return (email, expires, jti) if expires > utcnow() else None


def revoke_token(s: Session, token: str | None) -> None:
    parsed = parse_token(token)
    if parsed and not s.get(RevokedToken, parsed[2]):
        s.execute(delete(RevokedToken).where(RevokedToken.expires_at < utcnow()))
        s.add(RevokedToken(jti=parsed[2], expires_at=parsed[1]))
        s.commit()


def user_from_token(s: Session, token: str | None) -> User | None:
    parsed = parse_token(token)
    if not parsed or s.get(RevokedToken, parsed[2]):
        return None
    user = s.scalars(select(User).where(User.email == parsed[0])).first()
    return user if user and user.active else None


def _bearer(request: Request) -> str | None:
    h = request.headers.get("Authorization", "")
    return h[7:] if h.lower().startswith("bearer ") else None


def current_user(request: Request, s: Session = Depends(get_session)) -> User:
    user = user_from_token(s, _bearer(request))
    if not user:
        raise HTTPException(401, "Not signed in")
    return user


def current_user_query(token: str = Query(""), s: Session = Depends(get_session)) -> User:
    """For EventSource, which cannot send headers."""
    user = user_from_token(s, token)
    if not user:
        raise HTTPException(401, "Not signed in")
    return user


def require(permission: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in PERMISSIONS[permission]:
            raise HTTPException(403, f"Your role ({ROLES[user.role]}) can't do this.")
        return user
    return dep

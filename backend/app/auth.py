"""Authentication (bearer tokens) and role-based permissions."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .db import get_session
from .models import AuthToken, User, utcnow

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


def issue_token(s: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    s.add(AuthToken(token=token, user_id=user.id, expires_at=utcnow() + TOKEN_TTL))
    user.last_login_at = utcnow()
    s.commit()
    return token


def user_from_token(s: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = s.get(AuthToken, token)
    if not row or row.expires_at < utcnow() or not row.user.active:
        return None
    return row.user


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

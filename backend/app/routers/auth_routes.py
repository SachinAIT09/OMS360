from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import bus, serial
from ..auth import ROLES, current_user, issue_token, verify_password
from ..db import get_session
from ..models import AuthToken, User

router = APIRouter(prefix="/auth", tags=["auth"])


class Login(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: Login, s: Session = Depends(get_session)):
    u = s.scalars(select(User).where(User.email == body.email.strip().lower())).first()
    if not u or not u.active or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    token = issue_token(s, u)
    bus.audit(s, u.name, "auth.login", "user", u.id, notify=False)
    s.commit()
    return {"token": token, "user": serial.user(u)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return serial.user(user)


@router.post("/logout")
def logout(request: Request, user: User = Depends(current_user), s: Session = Depends(get_session)):
    token = request.headers.get("Authorization", "")[7:]
    row = s.get(AuthToken, token)
    if row:
        s.delete(row)
        s.commit()
    return {"ok": True}


@router.get("/sandbox-accounts")
def sandbox_accounts(s: Session = Depends(get_session)):
    """Shown on the sign-in page of a sandbox installation."""
    return [{"email": u.email, "name": u.name, "role": ROLES[u.role], "title": u.title}
            for u in s.scalars(select(User).where(User.active.is_(True)).order_by(User.id)).all()]

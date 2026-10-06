"""FastAPI authentication dependencies: bearer tokens and tenant membership."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from freellmpool.api.db import (
    SESSION_TTL_HOURS,
    AuthSession,
    OrganizationMembership,
    User,
    get_db,
)
from freellmpool.api.security import (
    PBKDF2_ITERATIONS,
    hash_session_token,
    new_session_token,
    verify_password,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def _unauthenticated(detail: str = "could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the active user for valid credentials, else ``None``."""
    user = db.scalar(select(User).where(User.email == email.strip().casefold()))
    if user is None or not user.is_active:
        # Verify against a dummy hash with the same iteration count so missing
        # users are not distinguishable from wrong passwords by response timing.
        verify_password(password, f"pbkdf2_sha256${PBKDF2_ITERATIONS}$AAAA$AAAA")
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(
    db: Session = Depends(get_db),  # noqa: B008
    token: str = Depends(oauth2_scheme),  # noqa: B008
) -> User:
    """Resolve the authenticated user from an opaque bearer token."""
    stored = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_session_token(token))
    )
    if stored is None:
        raise _unauthenticated()
    expires = stored.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires <= datetime.now(UTC):
        raise _unauthenticated("session expired")
    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise _unauthenticated()
    return user


def issue_session(db: Session, user: User) -> tuple[AuthSession, str]:
    """Persist a new session row; returns the row and the plaintext bearer token.

    Only the SHA-256 digest of the token is stored, so a database leak does
    not yield usable credentials. Issuing a session also purges this user's
    already-expired sessions so stale rows cannot accumulate forever.
    """
    now = datetime.now(UTC)
    db.execute(
        delete(AuthSession).where(
            AuthSession.user_id == user.id,
            AuthSession.expires_at <= now,
        )
    )
    token = new_session_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=now + timedelta(hours=SESSION_TTL_HOURS),
    )
    db.add(session)
    return session, token


def is_member(db: Session, user_id: int, organization_id: int) -> bool:
    """Server-side tenant check: does this user belong to this organization?"""
    return member_role(db, user_id, organization_id) is not None


def member_role(db: Session, user_id: int, organization_id: int) -> str | None:
    """Return the user's role in the organization, or ``None`` if not a member."""
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == organization_id,
        )
    )
    return None if membership is None else membership.role


def require_role(
    db: Session, user: User, organization_id: int, *allowed_roles: str
) -> str:
    """Enforce a privileged role inside an organization.

    Non-members receive the same 404 as a nonexistent organization so
    membership is not disclosed. Members without an allowed role receive
    403: they already know the organization exists.
    """
    role = member_role(db, user.id, organization_id)
    if role is None:
        raise HTTPException(status_code=404, detail="organization not found")
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="insufficient role")
    return role

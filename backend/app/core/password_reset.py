import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import PasswordResetToken, RefreshSession, User


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_password_reset_token(db: Session, user: User) -> str:
    settings = get_settings()
    raw_token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_token_hash(raw_token),
            expires_at=now + timedelta(minutes=settings.password_reset_expire_minutes),
        )
    )
    db.commit()
    return raw_token


def send_password_reset_email(email: str, token: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured. Please try again later.",
        )

    reset_url = f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={quote(token)}"
    message = EmailMessage()
    message["Subject"] = "Reset your Home Energy Intelligence password"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        "A password reset was requested for your HEI account. "
        f"This link expires in {settings.password_reset_expire_minutes} minutes.\n\n"
        f"{reset_url}\n\nIf you did not request this, you can ignore this email. "
        "Your password will not change unless the link is used."
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.ehlo()
            if settings.smtp_use_starttls:
                smtp.starttls()
                smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to send password reset email. Please try again later.",
        ) from exc


def reset_password(db: Session, raw_token: str, new_password: str) -> None:
    now = datetime.now(timezone.utc)
    digest = _token_hash(raw_token)
    result = db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == digest,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid or expired password reset link")

    token = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == digest))
    user = db.scalar(select(User).where(User.id == token.user_id)) if token is not None else None
    if user is None or not user.is_active or not user.email_verified:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid or expired password reset link")

    user.password_hash = hash_password(new_password)
    user.token_version += 1
    db.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    db.commit()

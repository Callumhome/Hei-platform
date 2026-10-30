import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote

from fastapi import HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import EmailVerificationToken, User


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_verification_token(db: Session, user: User) -> str:
    settings = get_settings()
    raw_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.email_verification_expire_hours)
    db.execute(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user.id, EmailVerificationToken.used_at.is_(None))
        .values(used_at=datetime.now(timezone.utc))
    )
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=_token_hash(raw_token),
            expires_at=expires_at,
        )
    )
    db.commit()
    return raw_token


def send_verification_email(email: str, token: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured. Please try again later.",
        )

    verify_url = f"{settings.frontend_base_url.rstrip('/')}/verify-email?token={quote(token)}"
    message = EmailMessage()
    message["Subject"] = "Verify your Home Energy Intelligence account"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        "Please verify your HEI account using the link below. "
        "This link expires in "
        f"{settings.email_verification_expire_hours} hours.\n\n{verify_url}\n\n"
        "If you did not create this account, you can ignore this email."
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
            detail="Unable to send verification email. Please request another email.",
        ) from exc


def verify_email_token(db: Session, raw_token: str) -> User:
    token = db.scalar(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.token_hash == _token_hash(raw_token))
    )
    if token is None or token.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    now = datetime.now(timezone.utc)
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    user = db.scalar(select(User).where(User.id == token.user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    token.used_at = now
    user.email_verified = True
    db.commit()
    db.refresh(user)
    return user

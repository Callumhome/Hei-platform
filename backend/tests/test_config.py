import pytest
from pydantic import ValidationError

from app.core.config import DEVELOPMENT_SECRET_KEY, Settings


def test_development_secret_is_long_enough_for_hs256():
    settings = Settings()
    assert len(settings.secret_key.encode("utf-8")) >= 32


def test_production_rejects_development_secret():
    with pytest.raises(ValidationError):
        Settings(app_env="production")


def test_production_accepts_unique_strong_secret():
    settings = Settings(
        app_env="production",
        secret_key="a-production-secret-key-with-more-than-32-bytes",
    )
    assert settings.secret_key != DEVELOPMENT_SECRET_KEY

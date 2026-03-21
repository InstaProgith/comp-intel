from __future__ import annotations

import os
import secrets
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

TRUE_VALUES = {"1", "true", "yes", "on"}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def current_environment() -> str:
    return (
        os.environ.get("APP_ENV")
        or os.environ.get("FLASK_ENV")
        or ""
    ).strip().lower()


def is_testing_mode() -> bool:
    return env_flag("APP_TESTING") or env_flag("TESTING")


def is_debug_mode() -> bool:
    return env_flag("FLASK_DEBUG") or current_environment() in {"development", "dev", "local"}


def is_production_like_mode() -> bool:
    if current_environment() == "production":
        return True
    if is_testing_mode() or is_debug_mode():
        return False
    return bool(
        os.environ.get("PORT")
        or os.environ.get("GUNICORN_CMD_ARGS")
        or "gunicorn" in os.environ.get("SERVER_SOFTWARE", "").lower()
    )


def _read_text_file(path: Path) -> str | None:
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def resolve_flask_secret_key() -> str:
    configured_secret = os.environ.get("FLASK_SECRET_KEY")
    if configured_secret:
        return configured_secret

    if is_production_like_mode():
        raise RuntimeError(
            "FLASK_SECRET_KEY is required in production-like environments. "
            "Set APP_ENV=production and provide FLASK_SECRET_KEY before starting the app."
        )

    warnings.warn(
        "FLASK_SECRET_KEY not set. Using an ephemeral development secret for this process only.",
        RuntimeWarning,
    )
    return secrets.token_urlsafe(32)


def resolve_access_password() -> str:
    configured_password = os.environ.get("APP_ACCESS_PASSWORD")
    if configured_password:
        return configured_password

    local_password = _read_text_file(BASE_DIR / "access_password.txt")
    if local_password:
        return local_password

    if is_production_like_mode():
        raise RuntimeError(
            "APP_ACCESS_PASSWORD is required in production-like environments unless a local "
            "access_password.txt is provisioned outside git."
        )

    warnings.warn(
        "APP_ACCESS_PASSWORD not set and access_password.txt not found. "
        "Using the development placeholder password CHANGE_ME_DEV.",
        RuntimeWarning,
    )
    return "CHANGE_ME_DEV"

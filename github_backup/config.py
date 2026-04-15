from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONCURRENCY = 4
DEFAULT_FAILURE_DELAY_SECONDS = 300
DEFAULT_SCHEDULE_SECONDS = 86400


class ConfigError(ValueError):
    """Raised when configuration is invalid."""


@dataclass(slots=True)
class AppConfig:
    token: str
    directory: Path
    owners: frozenset[str] | None
    extra_orgs: frozenset[str]
    concurrency: int
    schedule_seconds: int
    failure_delay_seconds: int


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Config file does not exist: {path}")

    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ConfigError("Config file must contain a JSON object")
    return payload


def _read_positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, str):
        value = value.strip()
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field_name} must be an integer") from exc

    if parsed <= 0:
        raise ConfigError(f"{field_name} must be greater than zero")
    return parsed


def _read_name_list(value: object, *, field_name: str) -> frozenset[str] | None:
    if value in (None, "", []):
        return None

    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        items = [str(item).strip() for item in value]
    else:
        raise ConfigError(f"{field_name} must be a list of strings or a comma-separated string")

    names = frozenset(item for item in items if item)
    return names or None


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path)
    payload = _read_json(path)

    token = os.environ.get("TOKEN") or os.environ.get("GITHUB_TOKEN") or payload.get("token", "")
    token = str(token).strip()
    if not token:
        raise ConfigError("GitHub token is required via config or TOKEN/GITHUB_TOKEN")

    directory_value = os.environ.get("BACKUP_DIRECTORY") or payload.get("directory", "")
    directory = Path(str(directory_value)).expanduser()
    if not str(directory).strip():
        raise ConfigError("Backup directory is required via config or BACKUP_DIRECTORY")

    owners = _read_name_list(os.environ.get("OWNERS") or payload.get("owners"), field_name="owners")
    extra_orgs = (
        _read_name_list(
            os.environ.get("EXTRA_ORGS") or payload.get("extra_orgs"),
            field_name="extra_orgs",
        )
        or frozenset()
    )

    concurrency = _read_positive_int(
        os.environ.get("CONCURRENCY", payload.get("concurrency", DEFAULT_CONCURRENCY)),
        field_name="concurrency",
    )
    schedule_seconds = _read_positive_int(
        os.environ.get("SCHEDULE", payload.get("schedule_seconds", DEFAULT_SCHEDULE_SECONDS)),
        field_name="schedule_seconds",
    )
    failure_delay_seconds = _read_positive_int(
        os.environ.get(
            "FAILURE_DELAY_SECONDS",
            payload.get("failure_delay_seconds", DEFAULT_FAILURE_DELAY_SECONDS),
        ),
        field_name="failure_delay_seconds",
    )

    return AppConfig(
        token=token,
        directory=directory,
        owners=owners,
        extra_orgs=extra_orgs,
        concurrency=concurrency,
        schedule_seconds=schedule_seconds,
        failure_delay_seconds=failure_delay_seconds,
    )

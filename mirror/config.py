"""Settings loaded from the environment / .env file. Nothing secret is hardcoded."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
MIN_TOKEN_LEN = 16


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    token: str
    port: int
    monitor: int
    fps: int
    jpeg_quality: int
    scale: float
    max_clients: int


def _num(name, default, cast, lo, hi):
    raw = os.environ.get(name, "").strip()
    try:
        value = cast(raw) if raw else default
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}")
    if not lo <= value <= hi:
        raise ConfigError(f"{name} must be between {lo} and {hi}, got {value}")
    return value


def load() -> Config:
    load_dotenv(ROOT / ".env")
    token = os.environ.get("SM_TOKEN", "").strip()
    if len(token) < MIN_TOKEN_LEN:
        raise ConfigError(
            f"SM_TOKEN is missing or shorter than {MIN_TOKEN_LEN} characters. "
            "Copy .env.example to .env and set it (see README)."
        )
    return Config(
        token=token,
        port=_num("SM_PORT", 8787, int, 1024, 65535),
        monitor=_num("SM_MONITOR", 1, int, 0, 32),
        fps=_num("SM_FPS", 15, int, 1, 60),
        jpeg_quality=_num("SM_JPEG_QUALITY", 60, int, 10, 95),
        scale=_num("SM_SCALE", 0.5, float, 0.1, 1.0),
        max_clients=_num("SM_MAX_CLIENTS", 3, int, 1, 16),
    )

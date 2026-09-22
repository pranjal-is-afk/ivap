"""Central configuration for IBVAP (loaded from environment / .env)."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings

# Repo root = three levels above this file (backend/app/core/config.py)
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "IBVAP API"
    version: str = "0.1.0"

    # Security
    jwt_secret: str = "change-me-ibvap-local-dev-secret-9f3a1c"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: float = 12.0
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Database
    database_url: str = "postgresql+psycopg2://ibvap:ibvap_dev_2026@localhost:5433/ibvap"

    # Server
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Paths (relative to repo root; resolved at runtime)
    evidence_dir: str = "evidence"
    assets_dir: str = "assets"

    # Demo helpers
    demo_video_dir: str = "assets/videos"

    model_config = {"env_file": str(REPO_ROOT / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def evidence_path(self) -> Path:
        p = Path(self.evidence_dir)
        return p if p.is_absolute() else (REPO_ROOT / p)

    @property
    def assets_path(self) -> Path:
        p = Path(self.assets_dir)
        return p if p.is_absolute() else (REPO_ROOT / p)

    @property
    def demo_video_path(self) -> Path:
        return self.assets_path / "videos"


settings = Settings()

# Fail fast (but only at import) if an env var is obviously nonsense.
if settings.jwt_expire_hours <= 0:
    raise ValueError("JWT_EXPIRE_HOURS must be positive")

os.environ.setdefault("UVICORN_NO_SERVER_HEADER", "1")

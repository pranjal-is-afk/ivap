"""Database engine, session factory, and schema initialization."""
from __future__ import annotations

import logging
from collections import Counter, deque
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import REPO_ROOT, settings

log = logging.getLogger("ibvap.db")

# Reconnect robustness for laptop sleep/resume and portable-postgres restarts
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DbHealth:
    """Ring-buffer tracker so the UI can show real DB status, not a guess."""

    def __init__(self, window: int = 20) -> None:
        self._window: deque[bool] = deque(maxlen=window)
        self._fail_streak = 0

    def check(self) -> bool:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            ok = True
        except OperationalError as exc:  # connection refused / pg down
            log.warning("DB health check failed: %s", exc.__class__.__name__)
            ok = False
        except Exception:  # pragma: no cover - unexpected
            log.exception("DB health check unexpected error")
            ok = False
        self.record(ok)
        return ok

    def record(self, ok: bool) -> None:
        self._window.append(ok)
        self._fail_streak = 0 if ok else self._fail_streak + 1

    @property
    def status(self) -> str:
        if not self._window:
            return "unknown"
        c = Counter(self._window)
        if self._fail_streak >= 3:
            return "down"
        if all(self._window):
            return "up"
        if c[True] > 0:
            return "degraded"
        return "down"


db_health = DbHealth()


def init_db() -> None:
    """Import models and create tables. Idempotent."""
    from app.db import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)

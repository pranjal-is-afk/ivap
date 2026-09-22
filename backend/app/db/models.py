"""ORM models for IBVAP — the single source of truth for the schema."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    admin = "admin"
    operator = "operator"
    viewer = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role", native_enum=False), nullable=False, default=Role.viewer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    secret: Mapped["UserSecret | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserSecret(Base):
    """Password hashes live in a separate table (defense in depth)."""

    __tablename__ = "user_secrets"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="secret")


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(512), nullable=False)  # rtsp://... or local file path or device index
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fps_target: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    zones: Mapped[list["Zone"]] = relationship(back_populates="camera", cascade="all, delete-orphan")


class Zone(Base):
    """Polygonal virtual fence, normalized to [0..1] frame coordinates so it
    survives resolution changes. Stored as a plain list of {x,y} dicts."""

    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(32), nullable=False, default="restricted")  # restricted|loiter|entry
    polygon: Mapped[list] = mapped_column(JSON, nullable=False)  # [{x:0..1,y:0..1}, ...]
    min_dwell_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    camera: Mapped[Camera] = relationship(back_populates="zones")


class Track(Base):
    """One row per object track (per camera)."""

    __tablename__ = "tracks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    track_key: Mapped[int] = mapped_column(BigInteger, nullable=False)  # ByteTrack id
    label: Mapped[str] = mapped_column(String(32), nullable=False)  # person|car|...
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    frames_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = ({"sqlite_autoincrement": True},)


class EventKind(str, enum.Enum):
    zone_intrusion = "zone_intrusion"
    loitering = "loitering"
    dwell = "dwell"
    plate_read = "plate_read"
    face_detected = "face_detected"
    night_movement = "night_movement"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    track_id: Mapped[str | None] = mapped_column(ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[EventKind] = mapped_column(Enum(EventKind, name="event_kind", native_enum=False), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # score, bbox, polygon, label...
    frame_snapshot: Mapped[str | None] = mapped_column(String(512), nullable=True)  # evidence-relative path

    camera: Mapped[Camera] = relationship()


class AlertStatus(str, enum.Enum):
    new = "new"
    acknowledged = "acknowledged"
    dismissed = "dismissed"


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")  # low|medium|high|critical
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus, name="alert_status", native_enum=False), nullable=False, default=AlertStatus.new)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped[Event] = relationship()
    ack_user: Mapped["User | None"] = relationship(foreign_keys=[acknowledged_by])


class Plate(Base):
    __tablename__ = "plates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    track_id: Mapped[str | None] = mapped_column(ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True)
    text: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    is_valid_format: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ocr_raw: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    snapshot: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Face(Base):
    __tablename__ = "faces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    track_id: Mapped[str | None] = mapped_column(ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    matched_watchlist_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # hook: watchlist table (not populated)
    snapshot: Mapped[str | None] = mapped_column(String(512), nullable=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class AuditChain(Base):
    """Append-only hash chain over alert lifecycle actions.

    Each row commits to the previous hash, so any tampering with acknowledged
    statuses breaks verification — an honest, auditable stand-in for the
    blockchain story, clearly labelled as such in the UI.
    """

    __tablename__ = "audit_chain"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    alert_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

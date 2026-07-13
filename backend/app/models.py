from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    next_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    follow_up_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tailoring_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tailored_resume_exists: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class IngestFeedConfig(Base):
    __tablename__ = "ingest_feed_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    source_site: Mapped[str] = mapped_column(String(64), nullable=False)
    search_url: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_keywords: Mapped[str] = mapped_column(Text, nullable=False, default="")
    exclude_keywords: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location_hint: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    radius_miles: Mapped[int | None] = mapped_column(nullable=True)
    schedule_days: Mapped[str] = mapped_column(String(64), nullable=False, default="mon,thu")
    schedule_hour_local: Mapped[int] = mapped_column(nullable=False, default=7)
    max_pages_per_run: Mapped[int] = mapped_column(nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    requested_feed_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    feeds_total: Mapped[int] = mapped_column(nullable=False, default=0)
    feeds_completed: Mapped[int] = mapped_column(nullable=False, default=0)
    pages_collected: Mapped[int] = mapped_column(nullable=False, default=0)
    artifacts_processed: Mapped[int] = mapped_column(nullable=False, default=0)
    jobs_inserted: Mapped[int] = mapped_column(nullable=False, default=0)
    jobs_updated: Mapped[int] = mapped_column(nullable=False, default=0)
    jobs_skipped: Mapped[int] = mapped_column(nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
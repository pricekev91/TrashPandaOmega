from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Lock, Thread

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from backend.app.admin import build_cleared_ingest_state, validate_delete_all_jobs_confirmation
from backend.app.config import get_settings
from backend.app.database import Base, SessionLocal, engine, ensure_job_schema, get_db
from backend.app.ingest_automation import run_ingest_automation
from backend.app.ingest_state import build_ingest_state_response
from backend.app.models import IngestFeedConfig, IngestRun, Job
from backend.app.schemas import (
    BatchJobUpdateRequest,
    BatchJobUpdateResponse,
    DashboardSummaryResponse,
    DeleteAllJobsRequest,
    DeleteAllJobsResponse,
    FeedConfigCreateRequest,
    FeedConfigResponse,
    FeedConfigUpdateRequest,
    HealthResponse,
    IngestStateResponse,
    IngestRunResponse,
    JobResponse,
    JobUpdateRequest,
    MasterResumeResponse,
    MasterResumeUpdateRequest,
    RunNowRequest,
    RunNowResponse,
    ScoreExplanationResponse,
)


settings = get_settings()
VALID_STATUSES = {"queued", "shortlisted", "applied", "archived", "not_interested", "discovered"}
VALID_NEXT_ACTIONS = {"apply_now", "resume_tailoring", "research", "follow_up", "archive"}
FOLLOW_UP_INTERVAL_DAYS = 7
SUPPORTED_FEED_SITES = {"google_jobs", "linkedin", "indeed", "flexjobs", "glassdoor", "ziprecruiter", "other"}
RUN_LOCK = Lock()
ACTIVE_RUN_ID: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_job_schema()
    yield


app = FastAPI(title="TrashPanda API", version="0.1.0", lifespan=lifespan)
MASTER_RESUME_PATH = Path(settings.data_dir) / "master-resume.md"
ARTIFACTS_ROOT = Path(settings.artifacts_dir)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_status(value: str | None) -> str | None:
    if value is None:
        return None
    if value == "discovered":
        return "queued"
    return value


def build_score_explanation(job: Job) -> ScoreExplanationResponse:
    text_blob = " ".join(part for part in (job.title, job.summary, job.company) if part).lower()
    keywords = [
        "platform",
        "infrastructure",
        "site reliability",
        "sre",
        "devops",
        "kubernetes",
        "terraform",
        "cloud",
        "automation",
        "linux",
        "python",
        "backend",
    ]
    overlap_hits = sum(1 for keyword in keywords if keyword in text_blob)
    skill_match = min(100, 38 + overlap_hits * 11 + int(job.score // 8))
    tech_stack_overlap = min(100, 20 + overlap_hits * 14)
    resume_keyword_alignment = min(100, 32 + overlap_hits * 10)

    title_blob = (job.title or "").lower()
    if any(level in title_blob for level in ("senior", "staff", "principal", "lead")):
        seniority_match = "stretch"
    elif any(level in title_blob for level in ("mid", "ii", "iii")):
        seniority_match = "aligned"
    elif any(level in title_blob for level in ("intern", "new grad", "entry", "junior")):
        seniority_match = "light"
    else:
        seniority_match = "aligned"

    stability_score = 72
    if "unknown company" in (job.company or "").lower():
        stability_score = 34
    elif "ycombinator" in (job.source_url or "").lower():
        stability_score = 78

    return ScoreExplanationResponse(
        skill_match_percent=skill_match,
        seniority_match=seniority_match,
        tech_stack_overlap=tech_stack_overlap,
        resume_keyword_alignment=resume_keyword_alignment,
        company_stability_score=stability_score,
    )


def compute_lifecycle_state(job: Job, current_time: datetime, in_flight_window_days: int = 45) -> str:
    status = normalize_status(job.status) or "queued"
    if status in {"queued", "shortlisted", "archived", "not_interested"}:
        return status

    applied_at = as_utc(job.applied_at)
    if applied_at is None:
        return status

    age = current_time - applied_at
    if age <= timedelta(days=2):
        return "applied"
    if age <= timedelta(days=in_flight_window_days):
        return "in_flight"
    return "ghosted"


def derive_next_action(job: Job, current_time: datetime, lifecycle_state: str | None = None) -> str:
    if job.next_action in VALID_NEXT_ACTIONS:
        return job.next_action

    lifecycle = lifecycle_state or compute_lifecycle_state(job, current_time)
    title_blob = (job.title or "").lower()
    summary_blob = (job.summary or "").lower()
    company_blob = (job.company or "").lower()

    if lifecycle in {"archived", "not_interested", "ghosted"}:
        return "archive"

    if lifecycle in {"applied", "in_flight"}:
        return "follow_up"

    if job.follow_up_due_at and (as_utc(job.follow_up_due_at) or current_time) <= current_time:
        return "follow_up"

    if job.snoozed_until and (as_utc(job.snoozed_until) or current_time) > current_time:
        return "research"

    if job.tailoring_required and not job.tailored_resume_exists:
        return "resume_tailoring"

    if any(term in title_blob for term in ("product specialist", "new grad", "entry-level")):
        return "archive"

    if "unknown company" in company_blob or "unknown" in (job.location or "").lower():
        return "research"

    if job.score >= 70:
        return "apply_now"

    if job.score >= 58 or any(term in summary_blob for term in ("terraform", "python", "platform", "infrastructure")):
        return "resume_tailoring"

    return "research"


def serialize_job(job: Job, current_time: datetime, in_flight_window_days: int = 45) -> JobResponse:
    lifecycle_state = compute_lifecycle_state(job, current_time, in_flight_window_days)
    return JobResponse(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        source=job.source,
        source_url=job.source_url,
        score=job.score,
        status=normalize_status(job.status) or "queued",
        lifecycle_state=lifecycle_state,
        next_action=derive_next_action(job, current_time, lifecycle_state),
        snoozed_until=job.snoozed_until,
        applied_at=job.applied_at,
        follow_up_due_at=job.follow_up_due_at,
        last_follow_up_at=job.last_follow_up_at,
        tailoring_required=job.tailoring_required,
        tailored_resume_exists=job.tailored_resume_exists,
        decision_reason=job.decision_reason,
        score_explanation=build_score_explanation(job),
        summary=job.summary,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def apply_job_update(job: Job, payload: JobUpdateRequest, current_time: datetime) -> None:
    status = normalize_status(payload.status)
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported status")

    if payload.next_action is not None and payload.next_action not in VALID_NEXT_ACTIONS:
        raise HTTPException(status_code=400, detail="Unsupported next action")

    if payload.snooze_days is not None and payload.snooze_days < 1:
        raise HTTPException(status_code=400, detail="Snooze days must be positive")

    if status == "applied" and payload.applied_at is None and job.applied_at is None:
        raise HTTPException(status_code=400, detail="Applied jobs require an applied date")

    decision_reason = payload.decision_reason.strip() if payload.decision_reason is not None else None
    if status == "not_interested" and not (decision_reason or job.decision_reason):
        raise HTTPException(status_code=400, detail="Not interested requires a reason")

    if status is not None:
        job.status = status

    if payload.applied_at is not None:
        job.applied_at = payload.applied_at

    if status == "applied":
        job.applied_at = payload.applied_at or job.applied_at
        if job.applied_at is None:
            raise HTTPException(status_code=400, detail="Applied jobs require an applied date")
        if job.follow_up_due_at is None:
            follow_up_due = (as_utc(job.applied_at) or current_time) + timedelta(days=FOLLOW_UP_INTERVAL_DAYS)
            job.follow_up_due_at = follow_up_due.replace(tzinfo=None)

    if payload.tailoring_required is not None:
        job.tailoring_required = payload.tailoring_required

    if payload.tailored_resume_exists is not None:
        job.tailored_resume_exists = payload.tailored_resume_exists
        if payload.tailored_resume_exists:
            job.tailoring_required = False

    if decision_reason is not None:
        job.decision_reason = decision_reason or None

    if status == "not_interested":
        job.applied_at = None
        job.follow_up_due_at = None
        job.last_follow_up_at = None
        job.next_action = "archive"

    if status == "queued":
        job.applied_at = None
        job.follow_up_due_at = None
        job.last_follow_up_at = None
        job.decision_reason = None
        job.snoozed_until = None

    if status == "archived":
        job.next_action = "archive"

    if payload.snooze_days is not None:
        job.snoozed_until = (current_time + timedelta(days=payload.snooze_days)).replace(tzinfo=None)
        job.next_action = "research"

    if payload.send_follow_up:
        if job.applied_at is None:
            raise HTTPException(status_code=400, detail="Follow-up requires an applied job")
        job.last_follow_up_at = current_time.replace(tzinfo=None)
        job.follow_up_due_at = (current_time + timedelta(days=FOLLOW_UP_INTERVAL_DAYS)).replace(tzinfo=None)
        job.next_action = "research"

    if payload.next_action is not None:
        job.next_action = payload.next_action

    if job.next_action is None:
        job.next_action = derive_next_action(job, current_time)

    job.updated_at = datetime.utcnow()


def load_ingest_state() -> dict:
    state_path = Path(settings.data_dir) / "ingest-state.json"
    if not state_path.exists():
        return {
            "updated_at": None,
            "poll_interval_seconds": 1800,
            "total_jobs": 0,
            "feed_count": 0,
            "errors": [],
            "sources": [],
        }

    with state_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_ingest_state(state: dict) -> None:
    state_path = Path(settings.data_dir) / "ingest-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def read_master_resume() -> MasterResumeResponse:
    if not MASTER_RESUME_PATH.exists():
        return MasterResumeResponse(content="", updated_at=None)

    stats = MASTER_RESUME_PATH.stat()
    updated_at = datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc)
    return MasterResumeResponse(
        content=MASTER_RESUME_PATH.read_text(encoding="utf-8"),
        updated_at=updated_at,
    )


def write_master_resume(content: str) -> MasterResumeResponse:
    MASTER_RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
    MASTER_RESUME_PATH.write_text(content.strip() + "\n", encoding="utf-8")
    return read_master_resume()


def validate_feed_payload(
    *,
    source_site: str,
    search_url: str,
    schedule_hour_local: int,
    max_pages_per_run: int,
    radius_miles: int | None,
) -> None:
    if source_site not in SUPPORTED_FEED_SITES:
        raise HTTPException(status_code=400, detail="Unsupported source site")
    if not search_url.startswith("http://") and not search_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="search_url must start with http:// or https://")
    if schedule_hour_local < 0 or schedule_hour_local > 23:
        raise HTTPException(status_code=400, detail="schedule_hour_local must be between 0 and 23")
    if max_pages_per_run < 1 or max_pages_per_run > 20:
        raise HTTPException(status_code=400, detail="max_pages_per_run must be between 1 and 20")
    if radius_miles is not None and (radius_miles < 1 or radius_miles > 300):
        raise HTTPException(status_code=400, detail="radius_miles must be between 1 and 300")


def run_ingest_async(run_id: str, feed_ids: list[str] | None = None) -> None:
    global ACTIVE_RUN_ID
    try:
        with SessionLocal() as session:
            run = session.query(IngestRun).filter(IngestRun.id == run_id).one_or_none()
            if run is None:
                return

            feeds_query = session.query(IngestFeedConfig).filter(IngestFeedConfig.enabled.is_(True))
            if feed_ids:
                feeds_query = feeds_query.filter(IngestFeedConfig.id.in_(feed_ids))

            feeds = feeds_query.order_by(IngestFeedConfig.created_at.desc()).all()
            if not feeds:
                run.status = "failed"
                run.started_at = datetime.utcnow()
                run.finished_at = datetime.utcnow()
                run.error_summary = "No enabled feeds are configured for this run."
                session.add(run)
                session.commit()
                return

            ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
            run_ingest_automation(session, run, feeds, ARTIFACTS_ROOT)
    except Exception as error:
        with SessionLocal() as session:
            run = session.query(IngestRun).filter(IngestRun.id == run_id).one_or_none()
            if run is not None:
                run.status = "failed"
                run.finished_at = datetime.utcnow()
                run.error_summary = f"Run failed: {error}"
                session.add(run)
                session.commit()
    finally:
        with RUN_LOCK:
            if ACTIVE_RUN_ID == run_id:
                ACTIVE_RUN_ID = None


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(
        status=True,
        database="ok",
        ai_base_url=settings.ai_base_url,
        ai_model=settings.ai_model,
    )


@app.get("/api/v1/jobs", response_model=list[JobResponse])
def list_jobs(db: Session = Depends(get_db)) -> list[JobResponse]:
    current_time = now_utc()
    jobs = db.query(Job).order_by(Job.score.desc(), Job.created_at.desc()).all()
    return [serialize_job(job, current_time) for job in jobs]


@app.get("/api/v1/ingest-state", response_model=IngestStateResponse)
def ingest_state() -> IngestStateResponse:
    return build_ingest_state_response(load_ingest_state())


@app.get("/api/v1/dashboard-summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    in_flight_window_days: int = Query(default=45, ge=15, le=60),
    db: Session = Depends(get_db),
) -> DashboardSummaryResponse:
    state = load_ingest_state()
    current_time = now_utc()
    jobs = db.query(Job).order_by(Job.score.desc(), Job.created_at.desc()).all()
    lifecycle_counts = {
        "queued": 0,
        "shortlisted": 0,
        "applied": 0,
        "in_flight": 0,
        "ghosted": 0,
        "archived": 0,
    }
    next_action_counts = {key: 0 for key in VALID_NEXT_ACTIONS}

    total_jobs = len(jobs)
    applied_jobs = 0
    in_flight_jobs = 0
    ghosted_jobs = 0
    follow_ups_due = 0
    apps_per_day = 0
    apps_per_week = 0
    pipeline_throughput = 0
    hours_to_apply: list[float] = []

    for job in jobs:
        lifecycle_state = compute_lifecycle_state(job, current_time, in_flight_window_days)
        if lifecycle_state in lifecycle_counts:
            lifecycle_counts[lifecycle_state] += 1
        elif lifecycle_state == "not_interested":
            lifecycle_counts["archived"] += 1

        next_action = derive_next_action(job, current_time, lifecycle_state)
        next_action_counts[next_action] = next_action_counts.get(next_action, 0) + 1

        applied_at = as_utc(job.applied_at)
        if applied_at is not None:
            applied_jobs += 1
            if current_time - applied_at <= timedelta(days=1):
                apps_per_day += 1
            if current_time - applied_at <= timedelta(days=7):
                apps_per_week += 1
            created_at = as_utc(job.created_at) or current_time
            hours_to_apply.append(max(0.0, (applied_at - created_at).total_seconds() / 3600))

        if lifecycle_state == "in_flight":
            in_flight_jobs += 1
        if lifecycle_state == "ghosted":
            ghosted_jobs += 1

        follow_up_due_at = as_utc(job.follow_up_due_at)
        if follow_up_due_at is not None and follow_up_due_at <= current_time and lifecycle_state in {"applied", "in_flight", "ghosted"}:
            follow_ups_due += 1

        updated_at = as_utc(job.updated_at)
        if updated_at is not None and updated_at >= current_time - timedelta(days=7) and lifecycle_state in {"applied", "ghosted", "archived", "not_interested"}:
            pipeline_throughput += 1

    return DashboardSummaryResponse(
        total_jobs=total_jobs,
        applied_jobs=applied_jobs,
        ghosted_jobs=ghosted_jobs,
        ghosted_percent=round((ghosted_jobs / applied_jobs) * 100, 1) if applied_jobs else 0.0,
        in_flight_jobs=in_flight_jobs,
        follow_ups_due=follow_ups_due,
        in_flight_window_days=in_flight_window_days,
        feed_count=state.get("feed_count", len(state.get("sources", {}))),
        lifecycle_counts=lifecycle_counts,
        next_action_counts=next_action_counts,
        apps_per_day=apps_per_day,
        apps_per_week=apps_per_week,
        avg_hours_to_apply=round(sum(hours_to_apply) / len(hours_to_apply), 1) if hours_to_apply else 0.0,
        pipeline_throughput=pipeline_throughput,
        updated_at=state.get("updated_at"),
    )


@app.get("/api/v1/master-resume", response_model=MasterResumeResponse)
def get_master_resume() -> MasterResumeResponse:
    return read_master_resume()


@app.put("/api/v1/master-resume", response_model=MasterResumeResponse)
def update_master_resume(payload: MasterResumeUpdateRequest) -> MasterResumeResponse:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Master resume cannot be empty")
    return write_master_resume(content)


@app.patch("/api/v1/jobs/{job_id}", response_model=JobResponse)
def update_job(job_id: str, payload: JobUpdateRequest, db: Session = Depends(get_db)) -> Job:
    job = db.query(Job).filter(Job.id == job_id).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    current_time = now_utc()
    apply_job_update(job, payload, current_time)
    db.add(job)
    db.commit()
    db.refresh(job)
    return serialize_job(job, current_time)


@app.post("/api/v1/jobs/batch-update", response_model=BatchJobUpdateResponse)
def batch_update_jobs(payload: BatchJobUpdateRequest, db: Session = Depends(get_db)) -> BatchJobUpdateResponse:
    if not payload.job_ids:
        raise HTTPException(status_code=400, detail="Select at least one job")

    jobs = db.query(Job).filter(Job.id.in_(payload.job_ids)).all()
    if len(jobs) != len(set(payload.job_ids)):
        raise HTTPException(status_code=404, detail="One or more jobs were not found")

    current_time = now_utc()
    for job in jobs:
        apply_job_update(job, payload, current_time)
        db.add(job)

    db.commit()
    return BatchJobUpdateResponse(updated_jobs=len(jobs))


@app.post("/api/v1/jobs/delete-all", response_model=DeleteAllJobsResponse)
def delete_all_jobs(payload: DeleteAllJobsRequest, db: Session = Depends(get_db)) -> DeleteAllJobsResponse:
    try:
        validate_delete_all_jobs_confirmation(payload.confirmation)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    deleted_jobs = db.execute(delete(Job)).rowcount or 0
    db.commit()
    write_ingest_state(build_cleared_ingest_state(load_ingest_state()))
    return DeleteAllJobsResponse(deleted_jobs=deleted_jobs)


@app.get("/api/v1/feeds", response_model=list[FeedConfigResponse])
def list_feeds(db: Session = Depends(get_db)) -> list[FeedConfigResponse]:
    feeds = db.query(IngestFeedConfig).order_by(IngestFeedConfig.created_at.desc()).all()
    return [FeedConfigResponse.model_validate(feed) for feed in feeds]


@app.post("/api/v1/feeds", response_model=FeedConfigResponse)
def create_feed(payload: FeedConfigCreateRequest, db: Session = Depends(get_db)) -> FeedConfigResponse:
    validate_feed_payload(
        source_site=payload.source_site,
        search_url=payload.search_url,
        schedule_hour_local=payload.schedule_hour_local,
        max_pages_per_run=payload.max_pages_per_run,
        radius_miles=payload.radius_miles,
    )
    existing = db.query(IngestFeedConfig).filter(IngestFeedConfig.name == payload.name.strip()).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Feed name already exists")

    feed = IngestFeedConfig(
        name=payload.name.strip(),
        source_site=payload.source_site,
        search_url=payload.search_url.strip(),
        enabled=payload.enabled,
        include_keywords=payload.include_keywords.strip(),
        exclude_keywords=payload.exclude_keywords.strip(),
        location_hint=payload.location_hint.strip(),
        radius_miles=payload.radius_miles,
        schedule_days=payload.schedule_days.strip().lower(),
        schedule_hour_local=payload.schedule_hour_local,
        max_pages_per_run=payload.max_pages_per_run,
    )
    db.add(feed)
    db.commit()
    db.refresh(feed)
    return FeedConfigResponse.model_validate(feed)


@app.patch("/api/v1/feeds/{feed_id}", response_model=FeedConfigResponse)
def update_feed(feed_id: str, payload: FeedConfigUpdateRequest, db: Session = Depends(get_db)) -> FeedConfigResponse:
    feed = db.query(IngestFeedConfig).filter(IngestFeedConfig.id == feed_id).one_or_none()
    if feed is None:
        raise HTTPException(status_code=404, detail="Feed not found")

    next_source_site = payload.source_site if payload.source_site is not None else feed.source_site
    next_search_url = payload.search_url.strip() if payload.search_url is not None else feed.search_url
    next_schedule_hour = payload.schedule_hour_local if payload.schedule_hour_local is not None else feed.schedule_hour_local
    next_max_pages = payload.max_pages_per_run if payload.max_pages_per_run is not None else feed.max_pages_per_run
    next_radius_miles = payload.radius_miles if payload.radius_miles is not None else feed.radius_miles
    validate_feed_payload(
        source_site=next_source_site,
        search_url=next_search_url,
        schedule_hour_local=next_schedule_hour,
        max_pages_per_run=next_max_pages,
        radius_miles=next_radius_miles,
    )

    if payload.name is not None:
        new_name = payload.name.strip()
        if new_name != feed.name:
            existing = db.query(IngestFeedConfig).filter(IngestFeedConfig.name == new_name).one_or_none()
            if existing is not None and existing.id != feed.id:
                raise HTTPException(status_code=400, detail="Feed name already exists")
        feed.name = new_name

    if payload.source_site is not None:
        feed.source_site = payload.source_site
    if payload.search_url is not None:
        feed.search_url = payload.search_url.strip()
    if payload.enabled is not None:
        feed.enabled = payload.enabled
    if payload.include_keywords is not None:
        feed.include_keywords = payload.include_keywords.strip()
    if payload.exclude_keywords is not None:
        feed.exclude_keywords = payload.exclude_keywords.strip()
    if payload.location_hint is not None:
        feed.location_hint = payload.location_hint.strip()
    if payload.radius_miles is not None:
        feed.radius_miles = payload.radius_miles
    if payload.schedule_days is not None:
        feed.schedule_days = payload.schedule_days.strip().lower()
    if payload.schedule_hour_local is not None:
        feed.schedule_hour_local = payload.schedule_hour_local
    if payload.max_pages_per_run is not None:
        feed.max_pages_per_run = payload.max_pages_per_run

    feed.updated_at = datetime.utcnow()
    db.add(feed)
    db.commit()
    db.refresh(feed)
    return FeedConfigResponse.model_validate(feed)


@app.get("/api/v1/ingest-runs", response_model=list[IngestRunResponse])
def list_ingest_runs(limit: int = Query(default=10, ge=1, le=50), db: Session = Depends(get_db)) -> list[IngestRunResponse]:
    runs = db.query(IngestRun).order_by(IngestRun.created_at.desc()).limit(limit).all()
    return [IngestRunResponse.model_validate(run) for run in runs]


@app.post("/api/v1/ingest-runs/run-now", response_model=RunNowResponse)
def run_now(payload: RunNowRequest, db: Session = Depends(get_db)) -> RunNowResponse:
    global ACTIVE_RUN_ID
    requested_feed_ids = payload.feed_ids or None

    with RUN_LOCK:
        active = db.query(IngestRun).filter(IngestRun.status.in_(["queued", "running"])).order_by(IngestRun.created_at.desc()).first()
        if active is not None:
            raise HTTPException(status_code=409, detail="Another ingest run is already queued or running")

        run = IngestRun(
            status="queued",
            trigger_type="manual",
            requested_feed_ids=",".join(requested_feed_ids) if requested_feed_ids else None,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        ACTIVE_RUN_ID = run.id

        worker = Thread(target=run_ingest_async, args=(run.id, requested_feed_ids), daemon=True)
        worker.start()

    return RunNowResponse(run_id=run.id, status=run.status)
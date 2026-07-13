from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScoreExplanationResponse(BaseModel):
    skill_match_percent: int
    seniority_match: str
    tech_stack_overlap: int
    resume_keyword_alignment: int
    company_stability_score: int


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    company: str
    location: str
    source: str
    source_url: str | None
    score: float
    status: str
    lifecycle_state: str
    next_action: str
    snoozed_until: datetime | None
    applied_at: datetime | None
    follow_up_due_at: datetime | None
    last_follow_up_at: datetime | None
    tailoring_required: bool
    tailored_resume_exists: bool
    decision_reason: str | None
    score_explanation: ScoreExplanationResponse
    summary: str
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: bool
    database: str
    ai_base_url: str
    ai_model: str


class IngestSourceResponse(BaseModel):
    name: str
    inserted: int
    status: str = "unknown"
    last_ingest_at: datetime | None = None
    errors: list[str] = []


class IngestStateResponse(BaseModel):
    updated_at: datetime | None = None
    poll_interval_seconds: int
    total_jobs: int
    feed_count: int
    errors: list[str]
    sources: list[IngestSourceResponse]


class DashboardSummaryResponse(BaseModel):
    total_jobs: int
    applied_jobs: int
    ghosted_jobs: int
    ghosted_percent: float
    in_flight_jobs: int
    follow_ups_due: int
    in_flight_window_days: int
    feed_count: int
    lifecycle_counts: dict[str, int]
    next_action_counts: dict[str, int]
    apps_per_day: int
    apps_per_week: int
    avg_hours_to_apply: float
    pipeline_throughput: int
    updated_at: datetime | None = None


class MasterResumeResponse(BaseModel):
    content: str
    updated_at: datetime | None = None


class MasterResumeUpdateRequest(BaseModel):
    content: str


class JobUpdateRequest(BaseModel):
    status: str | None = None
    next_action: str | None = None
    applied_at: datetime | None = None
    snooze_days: int | None = None
    send_follow_up: bool = False
    tailoring_required: bool | None = None
    tailored_resume_exists: bool | None = None
    decision_reason: str | None = None


class BatchJobUpdateRequest(JobUpdateRequest):
    job_ids: list[str]


class BatchJobUpdateResponse(BaseModel):
    updated_jobs: int


class DeleteAllJobsRequest(BaseModel):
    confirmation: str


class DeleteAllJobsResponse(BaseModel):
    deleted_jobs: int


class FeedConfigBase(BaseModel):
    name: str
    source_site: str
    search_url: str
    enabled: bool = True
    include_keywords: str = ""
    exclude_keywords: str = ""
    location_hint: str = ""
    radius_miles: int | None = None
    schedule_days: str = "mon,thu"
    schedule_hour_local: int = 7
    max_pages_per_run: int = 3


class FeedConfigCreateRequest(FeedConfigBase):
    pass


class FeedConfigUpdateRequest(BaseModel):
    name: str | None = None
    source_site: str | None = None
    search_url: str | None = None
    enabled: bool | None = None
    include_keywords: str | None = None
    exclude_keywords: str | None = None
    location_hint: str | None = None
    radius_miles: int | None = None
    schedule_days: str | None = None
    schedule_hour_local: int | None = None
    max_pages_per_run: int | None = None


class FeedConfigResponse(FeedConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class IngestRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    trigger_type: str
    requested_feed_ids: str | None
    started_at: datetime | None
    finished_at: datetime | None
    feeds_total: int
    feeds_completed: int
    pages_collected: int
    artifacts_processed: int
    jobs_inserted: int
    jobs_updated: int
    jobs_skipped: int
    error_summary: str | None
    created_at: datetime
    updated_at: datetime


class RunNowRequest(BaseModel):
    feed_ids: list[str] | None = None


class RunNowResponse(BaseModel):
    run_id: str
    status: str
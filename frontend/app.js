const jobsElement = document.getElementById('jobs');
const statusElement = document.getElementById('status-text');
const refreshButton = document.getElementById('refresh-button');
const totalMetricElement = document.getElementById('metric-total');
const appliedMetricElement = document.getElementById('metric-applied');
const flightMetricElement = document.getElementById('metric-flight');
const flightWindowElement = document.getElementById('metric-flight-window');
const followUpsMetricElement = document.getElementById('metric-follow-ups');
const ghostedPercentElement = document.getElementById('metric-ghosted-percent');
const appsDayMetricElement = document.getElementById('metric-apps-day');
const appsWeekMetricElement = document.getElementById('metric-apps-week');
const timeToApplyMetricElement = document.getElementById('metric-time-to-apply');
const throughputMetricElement = document.getElementById('metric-throughput');
const ingestSummaryElement = document.getElementById('ingest-summary');
const nextActionSummaryElement = document.getElementById('next-action-summary');
const nextActionLaneElement = document.getElementById('next-action-lane');
const masterResumeInput = document.getElementById('master-resume-input');
const masterResumeStatusElement = document.getElementById('master-resume-status');
const saveMasterResumeButton = document.getElementById('save-master-resume-button');
const bucketListElement = document.getElementById('bucket-list');
const feedHealthElement = document.getElementById('feed-health');
const stateMachineElement = document.getElementById('state-machine');
const searchInput = document.getElementById('search-input');
const nextActionFilter = document.getElementById('next-action-filter');
const windowFilter = document.getElementById('window-filter');
const deleteAllJobsButton = document.getElementById('delete-all-jobs-button');
const selectAllVisibleInput = document.getElementById('select-all-visible');
const batchStatusElement = document.getElementById('batch-status');
const batchAppliedDateInput = document.getElementById('batch-applied-date');
const batchReasonInput = document.getElementById('batch-reason');
const batchApplyButton = document.getElementById('batch-apply-button');
const batchNotInterestedButton = document.getElementById('batch-not-interested-button');
const batchReturnButton = document.getElementById('batch-return-button');
const batchSnoozeButton = document.getElementById('batch-snooze-button');
const runIngestNowButton = document.getElementById('run-ingest-now-button');
const ingestRunStatusElement = document.getElementById('ingest-run-status');
const ingestRunsElement = document.getElementById('ingest-runs');

const BUCKETS = [
  { key: 'queue', label: 'Queue' },
  { key: 'shortlist', label: 'Shortlist' },
  { key: 'applied', label: 'Applied' },
  { key: 'in_flight', label: 'In-Flight' },
  { key: 'ghosted', label: 'Ghosted' },
  { key: 'archived', label: 'Archived' },
  { key: 'not_interested', label: 'Not Interested' },
  { key: 'all', label: 'All' },
];

const NEXT_ACTIONS = [
  { key: 'apply_now', label: 'Apply now' },
  { key: 'resume_tailoring', label: 'Needs resume tailoring' },
  { key: 'research', label: 'Needs research' },
  { key: 'follow_up', label: 'Needs follow-up' },
  { key: 'archive', label: 'Ready to archive' },
];

let allJobs = [];
let latestIngestState = null;
let latestDashboardSummary = null;
let activeBucket = 'queue';
let activeNextAction = 'all';
const selectedJobIds = new Set();
let ingestRuns = [];

function formatTimestamp(value) {
  if (!value) {
    return 'never';
  }
  return new Date(value).toLocaleString();
}

function formatRelativeTime(value) {
  if (!value) {
    return 'No ingest timestamp yet.';
  }

  const timestamp = new Date(value);
  const diffMinutes = Math.max(0, Math.round((Date.now() - timestamp.getTime()) / 60000));
  if (diffMinutes < 1) {
    return 'updated just now';
  }
  if (diffMinutes < 60) {
    return `updated ${diffMinutes}m ago`;
  }

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) {
    return `updated ${diffHours}h ago`;
  }

  return `updated ${Math.round(diffHours / 24)}d ago`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatAppliedDate(value) {
  if (!value) {
    return 'Not applied yet';
  }
  return new Date(value).toLocaleDateString();
}

function formatDaysFromNow(value) {
  if (!value) {
    return 'No follow-up scheduled';
  }

  const diffDays = Math.ceil((new Date(value).getTime() - Date.now()) / 86400000);
  if (diffDays > 0) {
    return `Follow-up due in ${diffDays} day${diffDays === 1 ? '' : 's'}`;
  }
  if (diffDays === 0) {
    return 'Follow-up due today';
  }
  const overdueDays = Math.abs(diffDays);
  return `Follow-up overdue by ${overdueDays} day${overdueDays === 1 ? '' : 's'}`;
}

function batchCountForBucket(bucketKey) {
  return allJobs.filter((job) => bucketMatches(job, bucketKey)).length;
}

function bucketMatches(job, bucketKey = activeBucket) {
  if (bucketKey === 'all') {
    return true;
  }
  if (bucketKey === 'queue') {
    return job.lifecycle_state === 'queued';
  }
  if (bucketKey === 'shortlist') {
    return job.lifecycle_state === 'shortlisted';
  }
  if (bucketKey === 'applied') {
    return job.lifecycle_state === 'applied';
  }
  if (bucketKey === 'in_flight') {
    return job.lifecycle_state === 'in_flight';
  }
  if (bucketKey === 'ghosted') {
    return job.lifecycle_state === 'ghosted';
  }
  if (bucketKey === 'archived') {
    return job.lifecycle_state === 'archived';
  }
  if (bucketKey === 'not_interested') {
    return job.status === 'not_interested';
  }
  return true;
}

function visibleJobs() {
  const query = searchInput.value.trim().toLowerCase();
  return allJobs.filter((job) => {
    const haystack = [
      job.title,
      job.company,
      job.location,
      job.summary,
      job.source,
      job.decision_reason || '',
      job.next_action,
      job.lifecycle_state,
    ].join(' ').toLowerCase();
    const matchesQuery = !query || haystack.includes(query);
    const matchesBucket = bucketMatches(job);
    const matchesNextAction = activeNextAction === 'all' || job.next_action === activeNextAction;
    return matchesQuery && matchesBucket && matchesNextAction;
  });
}

function updateMetrics(dashboardSummary) {
  totalMetricElement.textContent = dashboardSummary?.total_jobs ?? allJobs.length;
  appliedMetricElement.textContent = dashboardSummary?.applied_jobs ?? allJobs.filter((job) => job.applied_at).length;
  flightMetricElement.textContent = dashboardSummary?.in_flight_jobs ?? 0;
  flightWindowElement.textContent = `${dashboardSummary?.in_flight_window_days ?? windowFilter.value} day window`;
  followUpsMetricElement.textContent = dashboardSummary?.follow_ups_due ?? 0;
  ghostedPercentElement.textContent = `${dashboardSummary?.ghosted_percent ?? 0}% ghosted`;
  appsDayMetricElement.textContent = dashboardSummary?.apps_per_day ?? 0;
  appsWeekMetricElement.textContent = dashboardSummary?.apps_per_week ?? 0;
  timeToApplyMetricElement.textContent = dashboardSummary ? `${dashboardSummary.avg_hours_to_apply}h` : '--';
  throughputMetricElement.textContent = dashboardSummary?.pipeline_throughput ?? 0;
}

function renderNextActionLane() {
  const counts = latestDashboardSummary?.next_action_counts || {};
  nextActionLaneElement.innerHTML = NEXT_ACTIONS.map((action) => `
    <button class="next-action-chip${activeNextAction === action.key ? ' is-active' : ''}" type="button" data-next-action-chip="${action.key}">
      <span>${action.label}</span>
      <strong>${counts[action.key] ?? 0}</strong>
    </button>
  `).join('');

  const currentLabel = NEXT_ACTIONS.find((action) => action.key === activeNextAction)?.label || 'All next actions';
  nextActionSummaryElement.textContent = activeNextAction === 'all'
    ? 'Click a lane to compress the queue into the next actual step.'
    : `Showing ${currentLabel.toLowerCase()} jobs first.`;
}

function renderBuckets() {
  bucketListElement.innerHTML = BUCKETS.map((bucket) => `
    <button class="bucket-button${activeBucket === bucket.key ? ' is-active' : ''}" type="button" data-bucket="${bucket.key}">
      <span>${bucket.label}</span>
      <strong>${batchCountForBucket(bucket.key)}</strong>
    </button>
  `).join('');
}

function renderFeedHealth() {
  if (!latestIngestState) {
    feedHealthElement.innerHTML = '<div class="empty compact-empty">Feed health unavailable.</div>';
    ingestSummaryElement.textContent = 'Ingest status unavailable.';
    return;
  }

  const feedItems = latestIngestState.sources.length
    ? latestIngestState.sources.map((source) => `
        <article class="feed-card">
          <div>
            <p class="feed-name">${escapeHtml(source.name)}</p>
            <p class="feed-meta">${escapeHtml(source.status || 'unknown')} · +${source.inserted} items added</p>
            <p class="feed-meta">${escapeHtml(source.errors?.length ? source.errors.join(' | ') : 'No source errors')}</p>
          </div>
          <p class="feed-meta">${formatRelativeTime(source.last_ingest_at || latestIngestState.updated_at)}</p>
        </article>
      `).join('')
    : '<div class="empty compact-empty">No active feeds reported.</div>';

  feedHealthElement.innerHTML = feedItems;
  const failedFeeds = latestIngestState.sources.filter((source) => source.status && source.status !== 'ok').length;
  const errorSummary = latestIngestState.errors.length ? `Errors: ${latestIngestState.errors.join(' | ')}` : 'No ingest errors';
  ingestSummaryElement.textContent = `${latestIngestState.feed_count} feeds configured · ${failedFeeds} degraded · ${formatRelativeTime(latestIngestState.updated_at)} · ${errorSummary}`;
}

function renderMasterResume(resume) {
  masterResumeInput.value = resume?.content || '';
  const contentState = resume?.content ? 'Master resume ready for scoring and tailoring.' : 'No master resume saved yet.';
  masterResumeStatusElement.textContent = `${contentState} Last updated ${formatTimestamp(resume?.updated_at)}.`;
}

function renderIngestRuns() {
  if (!ingestRuns.length) {
    ingestRunsElement.innerHTML = '<div class="empty compact-empty">No ingest runs yet.</div>';
    ingestRunStatusElement.textContent = 'No automation runs yet.';
    return;
  }

  ingestRunsElement.innerHTML = ingestRuns.map((run) => `
    <article class="run-card">
      <p class="feed-name">${escapeHtml(run.status)}</p>
      <p class="feed-meta">${formatRelativeTime(run.updated_at)}</p>
      <p class="feed-meta">feeds ${run.feeds_completed}/${run.feeds_total} · pages ${run.pages_collected} · jobs +${run.jobs_inserted}</p>
      <p class="feed-meta">updated ${run.jobs_updated} · skipped ${run.jobs_skipped}</p>
      <p class="feed-meta">${escapeHtml(run.error_summary || 'No run errors')}</p>
    </article>
  `).join('');

  const activeRun = ingestRuns.find((run) => run.status === 'queued' || run.status === 'running');
  if (activeRun) {
    ingestRunStatusElement.textContent = `Run ${activeRun.status}: feeds ${activeRun.feeds_completed}/${activeRun.feeds_total}, pages ${activeRun.pages_collected}.`;
    return;
  }

  const latestRun = ingestRuns[0];
  ingestRunStatusElement.textContent = `Last run ${latestRun.status}. Inserted ${latestRun.jobs_inserted} jobs and updated ${latestRun.jobs_updated}.`;
}

function renderStateMachine() {
  const counts = latestDashboardSummary?.lifecycle_counts || {};
  const states = [
    { key: 'queued', label: 'Queued' },
    { key: 'shortlisted', label: 'Shortlisted' },
    { key: 'applied', label: 'Applied' },
    { key: 'in_flight', label: 'In-Flight' },
    { key: 'ghosted', label: 'Ghosted' },
    { key: 'archived', label: 'Archived' },
  ];

  stateMachineElement.innerHTML = states.map((state) => `
    <div class="state-node">
      <span class="state-label">${state.label}</span>
      <strong>${counts[state.key] ?? 0}</strong>
    </div>
  `).join('<span class="state-arrow">→</span>');
}

function renderBatchStatus(jobs) {
  const visibleSelected = jobs.filter((job) => selectedJobIds.has(job.id)).length;
  batchStatusElement.textContent = selectedJobIds.size
    ? `${selectedJobIds.size} selected · ${visibleSelected} visible in the current slice.`
    : 'No jobs selected.';

  selectAllVisibleInput.checked = jobs.length > 0 && jobs.every((job) => selectedJobIds.has(job.id));
}

function buildFollowUpTemplate(job) {
  return [
    `Hi ${job.company} team,`,
    '',
    `I wanted to follow up on my application for ${job.title}. I remain very interested in the role, especially given the alignment around ${job.source} and the infrastructure-heavy work highlighted in the listing.`,
    '',
    'If there is any additional material that would help move the process forward, I can send it over quickly.',
    '',
    'Best,',
    'Kevin',
  ].join('\n');
}

function renderBadges(job) {
  const badges = [
    `<span class="badge badge-state badge-${job.lifecycle_state}">${job.lifecycle_state.replace('_', ' ')}</span>`,
    `<span class="badge badge-next">${job.next_action.replace('_', ' ')}</span>`,
  ];

  if (job.tailoring_required && !job.tailored_resume_exists) {
    badges.push('<span class="badge badge-tailoring">Tailoring required</span>');
  }
  if (job.tailored_resume_exists) {
    badges.push('<span class="badge badge-ready">Tailored resume ready</span>');
  }
  if (job.follow_up_due_at) {
    badges.push('<span class="badge badge-follow-up">Follow-up scheduled</span>');
  }
  if (job.snoozed_until) {
    badges.push(`<span class="badge badge-snoozed">Snoozed until ${new Date(job.snoozed_until).toLocaleDateString()}</span>`);
  }
  return badges.join('');
}

function renderScoreDetails(job) {
  const explanation = job.score_explanation;
  return `
    <details class="details-block">
      <summary>Why this score?</summary>
      <div class="details-grid">
        <div><span>Skill match</span><strong>${explanation.skill_match_percent}%</strong></div>
        <div><span>Seniority</span><strong>${escapeHtml(explanation.seniority_match)}</strong></div>
        <div><span>Tech stack</span><strong>${explanation.tech_stack_overlap}%</strong></div>
        <div><span>Resume alignment</span><strong>${explanation.resume_keyword_alignment}%</strong></div>
        <div><span>Company stability</span><strong>${explanation.company_stability_score}</strong></div>
      </div>
    </details>
  `;
}

function renderJobs(jobs) {
  jobsElement.innerHTML = '';

  if (!jobs.length) {
    jobsElement.innerHTML = '<div class="empty">No jobs matched the current filters.</div>';
    statusElement.textContent = 'API reachable, but nothing matches the current view.';
    renderBatchStatus(jobs);
    return;
  }

  const appliedCount = jobs.filter((job) => job.lifecycle_state === 'applied' || job.lifecycle_state === 'in_flight').length;
  const followUpCount = jobs.filter((job) => job.next_action === 'follow_up').length;
  statusElement.textContent = `${jobs.length} jobs shown. ${appliedCount} active applications. ${followUpCount} need follow-up.`;

  jobs.forEach((job) => {
    const article = document.createElement('article');
    article.className = 'job-card';
    const sourceLink = job.source_url
      ? `<a class="job-link" href="${escapeHtml(job.source_url)}" target="_blank" rel="noreferrer">Open listing</a>`
      : '<span class="job-link muted-link">No source link</span>';
    const titleMarkup = job.source_url
      ? `<a class="job-title-link" href="${escapeHtml(job.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(job.title)}</a>`
      : escapeHtml(job.title);
    const decisionReason = job.decision_reason
      ? `<p class="decision-reason"><strong>Why not interested:</strong> ${escapeHtml(job.decision_reason)}</p>`
      : '';
    const appliedValue = job.applied_at ? new Date(job.applied_at).toISOString().slice(0, 10) : '';
    const followUpTemplate = buildFollowUpTemplate(job);
    article.innerHTML = `
      <div class="job-card-topline">
        <label class="select-job">
          <input type="checkbox" data-select-job="${job.id}" ${selectedJobIds.has(job.id) ? 'checked' : ''}>
          <span>Select</span>
        </label>
        <div class="score-pill">${job.score.toFixed(0)}</div>
      </div>
      <div class="job-card-header">
        <div>
          <p class="job-company">${escapeHtml(job.company)}</p>
          <h3>${titleMarkup}</h3>
        </div>
      </div>
      <div class="badge-row">${renderBadges(job)}</div>
      <p class="job-meta">${escapeHtml(job.location)} · ${escapeHtml(job.source)} · ${escapeHtml(job.status)}</p>
      <p class="job-applied">Applied: ${formatAppliedDate(job.applied_at)}</p>
      <p class="job-follow-up">${formatDaysFromNow(job.follow_up_due_at)}</p>
      <p class="job-summary">${escapeHtml(job.summary)}</p>
      ${decisionReason}
      ${renderScoreDetails(job)}
      <div class="job-actions-meta">${sourceLink}</div>
      <div class="job-actions">
        <button class="button-secondary" data-action="shortlist" data-job-id="${job.id}" type="button">Shortlist</button>
        <button data-action="tailor" data-job-id="${job.id}" type="button">Tailor resume</button>
        <button class="button-secondary" data-action="follow-up" data-job-id="${job.id}" type="button">Send follow-up</button>
      </div>
      <div class="job-actions">
        <label class="action-field">
          <span>Applied date</span>
          <input data-applied-input="${job.id}" type="date" value="${appliedValue}">
        </label>
        <button data-action="apply" data-job-id="${job.id}" type="button">Mark Applied</button>
        <button class="button-secondary" data-action="archive" data-job-id="${job.id}" type="button">Archive</button>
      </div>
      <div class="job-actions job-actions-secondary">
        <label class="action-field action-field-wide">
          <span>Not Interested reason</span>
          <textarea data-reason-input="${job.id}" rows="2" placeholder="Explain why this role should be filtered out later.">${escapeHtml(job.decision_reason || '')}</textarea>
        </label>
        <button data-action="not-interested" data-job-id="${job.id}" type="button">Move to Not Interested</button>
        <button class="button-secondary" data-action="return" data-job-id="${job.id}" type="button">Return to Queue</button>
      </div>
      <details class="details-block follow-up-template">
        <summary>Follow-up template</summary>
        <pre>${escapeHtml(followUpTemplate)}</pre>
      </details>
    `;
    jobsElement.appendChild(article);
  });

  renderBatchStatus(jobs);
}

function renderView() {
  updateMetrics(latestDashboardSummary);
  renderNextActionLane();
  renderBuckets();
  renderFeedHealth();
  renderIngestRuns();
  renderStateMachine();
  renderJobs(visibleJobs());
}

async function updateJob(jobId, payload) {
  const response = await fetch(`/api/v1/jobs/${jobId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Update failed with ${response.status}`);
  }

  return response.json();
}

async function loadMasterResume() {
  const response = await fetch('/api/v1/master-resume');
  if (!response.ok) {
    throw new Error(`Master resume returned ${response.status}`);
  }
  return response.json();
}

async function saveMasterResume() {
  const response = await fetch('/api/v1/master-resume', {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      content: masterResumeInput.value,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Master resume update failed with ${response.status}`);
  }

  return response.json();
}

async function batchUpdateJobs(payload) {
  const response = await fetch('/api/v1/jobs/batch-update', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Batch update failed with ${response.status}`);
  }

  return response.json();
}

async function deleteAllJobs(confirmation) {
  const response = await fetch('/api/v1/jobs/delete-all', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ confirmation }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Delete all jobs failed with ${response.status}`);
  }

  return response.json();
}

function selectedIds() {
  return [...selectedJobIds];
}

async function handleCardAction(action, jobId) {
  if (action === 'shortlist') {
    await updateJob(jobId, { status: 'shortlisted', next_action: 'resume_tailoring' });
    return;
  }

  if (action === 'tailor') {
    await updateJob(jobId, { tailored_resume_exists: true, tailoring_required: false, next_action: 'apply_now' });
    return;
  }

  if (action === 'follow-up') {
    const job = allJobs.find((item) => item.id === jobId);
    if (job) {
      const template = buildFollowUpTemplate(job);
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(template);
      }
      statusElement.textContent = 'Follow-up template copied and follow-up state advanced.';
    }
    await updateJob(jobId, { send_follow_up: true });
    return;
  }

  if (action === 'apply') {
    const input = document.querySelector(`[data-applied-input="${jobId}"]`);
    const appliedDate = input?.value;
    if (!appliedDate) {
      statusElement.textContent = 'Choose an applied date before marking a job as applied.';
      return;
    }
    await updateJob(jobId, {
      status: 'applied',
      applied_at: new Date(`${appliedDate}T12:00:00Z`).toISOString(),
      next_action: 'follow_up',
    });
    return;
  }

  if (action === 'archive') {
    await updateJob(jobId, { status: 'archived', next_action: 'archive' });
    return;
  }

  if (action === 'not-interested') {
    const reasonInput = document.querySelector(`[data-reason-input="${jobId}"]`);
    const reason = reasonInput?.value?.trim();
    if (!reason) {
      statusElement.textContent = 'Not Interested requires a reason so TrashPanda can learn from it later.';
      return;
    }
    await updateJob(jobId, { status: 'not_interested', decision_reason: reason, next_action: 'archive' });
    return;
  }

  if (action === 'return') {
    await updateJob(jobId, { status: 'queued', next_action: 'apply_now' });
  }
}

async function runBatchAction(kind) {
  const jobIds = selectedIds();
  if (!jobIds.length) {
    statusElement.textContent = 'Select one or more jobs before running a batch action.';
    return;
  }

  if (kind === 'apply') {
    if (!batchAppliedDateInput.value) {
      statusElement.textContent = 'Choose a batch applied date before marking jobs as applied.';
      return;
    }
    await batchUpdateJobs({
      job_ids: jobIds,
      status: 'applied',
      applied_at: new Date(`${batchAppliedDateInput.value}T12:00:00Z`).toISOString(),
      next_action: 'follow_up',
    });
  }

  if (kind === 'not_interested') {
    const reason = batchReasonInput.value.trim();
    if (!reason) {
      statusElement.textContent = 'Batch Not Interested requires a reason.';
      return;
    }
    await batchUpdateJobs({
      job_ids: jobIds,
      status: 'not_interested',
      decision_reason: reason,
      next_action: 'archive',
    });
  }

  if (kind === 'return') {
    await batchUpdateJobs({
      job_ids: jobIds,
      status: 'queued',
      next_action: 'apply_now',
    });
  }

  if (kind === 'snooze') {
    await batchUpdateJobs({
      job_ids: jobIds,
      snooze_days: 30,
      next_action: 'research',
    });
  }

  selectedJobIds.clear();
  await loadJobs();
}

async function handleDeleteAllJobs() {
  const confirmation = window.prompt('Type DeleteAllJobs to permanently clear every job record from the database.');
  if (confirmation === null) {
    statusElement.textContent = 'Delete All Jobs canceled.';
    return;
  }

  const result = await deleteAllJobs(confirmation);
  selectedJobIds.clear();
  selectAllVisibleInput.checked = false;
  batchAppliedDateInput.value = '';
  batchReasonInput.value = '';
  await loadJobs();
  statusElement.textContent = `Deleted ${result.deleted_jobs} jobs from the database.`;
}

async function loadIngestState() {
  const response = await fetch('/api/v1/ingest-state');
  if (!response.ok) {
    throw new Error(`Ingest state returned ${response.status}`);
  }
  latestIngestState = await response.json();
}

async function loadFeedConfigs() {
  const response = await fetch('/api/v1/feeds');
  if (response.status === 404) {
    return [];
  }
  if (!response.ok) {
    throw new Error(`Feeds API returned ${response.status}`);
  }
  return response.json();
}

async function loadIngestRuns() {
  const response = await fetch('/api/v1/ingest-runs?limit=8');
  if (!response.ok) {
    throw new Error(`Ingest runs API returned ${response.status}`);
  }
  ingestRuns = await response.json();
}

async function createFeedConfig(payload) {
  const response = await fetch('/api/v1/feeds', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Create feed failed with ${response.status}`);
  }

  return response.json();
}

async function updateFeedConfig(feedId, payload) {
  const response = await fetch(`/api/v1/feeds/${feedId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Update feed failed with ${response.status}`);
  }

  return response.json();
}

async function runIngestNow() {
  const response = await fetch('/api/v1/ingest-runs/run-now', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({}),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Run now failed with ${response.status}`);
  }

  return response.json();
}

async function loadDashboardSummary() {
  const response = await fetch(`/api/v1/dashboard-summary?in_flight_window_days=${windowFilter.value}`);
  if (!response.ok) {
    throw new Error(`Dashboard summary returned ${response.status}`);
  }
  latestDashboardSummary = await response.json();
}

async function loadJobs() {
  statusElement.textContent = 'Loading jobs from the API...';

  try {
    const jobsResponse = await fetch('/api/v1/jobs');
    if (!jobsResponse.ok) {
      throw new Error(`Jobs API returned ${jobsResponse.status}`);
    }

    allJobs = await jobsResponse.json();
    await loadIngestState();
    await loadDashboardSummary();
    // Older deployments do not expose feed CRUD yet; keep dashboard available.
    await loadFeedConfigs();
    await loadIngestRuns();
    renderMasterResume(await loadMasterResume());
    renderView();
  } catch (error) {
    jobsElement.innerHTML = '<div class="empty">Dashboard could not reach the backend.</div>';
    statusElement.textContent = `Load failed: ${error.message}`;
    ingestSummaryElement.textContent = 'Ingest status unavailable.';
    masterResumeStatusElement.textContent = 'Master resume unavailable.';
  }
}

jobsElement.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-action]');
  if (!button) {
    return;
  }

  try {
    await handleCardAction(button.dataset.action, button.dataset.jobId);
    await loadJobs();
  } catch (error) {
    statusElement.textContent = `Update failed: ${error.message}`;
  }
});

jobsElement.addEventListener('change', (event) => {
  const checkbox = event.target.closest('[data-select-job]');
  if (!checkbox) {
    return;
  }

  if (checkbox.checked) {
    selectedJobIds.add(checkbox.dataset.selectJob);
  } else {
    selectedJobIds.delete(checkbox.dataset.selectJob);
  }
  renderBatchStatus(visibleJobs());
});

nextActionLaneElement.addEventListener('click', (event) => {
  const chip = event.target.closest('[data-next-action-chip]');
  if (!chip) {
    return;
  }
  activeNextAction = activeNextAction === chip.dataset.nextActionChip ? 'all' : chip.dataset.nextActionChip;
  nextActionFilter.value = activeNextAction;
  renderView();
});

bucketListElement.addEventListener('click', (event) => {
  const button = event.target.closest('[data-bucket]');
  if (!button) {
    return;
  }
  activeBucket = button.dataset.bucket;
  renderView();
});

selectAllVisibleInput.addEventListener('change', () => {
  const jobs = visibleJobs();
  if (selectAllVisibleInput.checked) {
    jobs.forEach((job) => selectedJobIds.add(job.id));
  } else {
    jobs.forEach((job) => selectedJobIds.delete(job.id));
  }
  renderView();
});

batchApplyButton.addEventListener('click', async () => {
  try {
    await runBatchAction('apply');
  } catch (error) {
    statusElement.textContent = `Batch update failed: ${error.message}`;
  }
});

batchNotInterestedButton.addEventListener('click', async () => {
  try {
    await runBatchAction('not_interested');
  } catch (error) {
    statusElement.textContent = `Batch update failed: ${error.message}`;
  }
});

batchReturnButton.addEventListener('click', async () => {
  try {
    await runBatchAction('return');
  } catch (error) {
    statusElement.textContent = `Batch update failed: ${error.message}`;
  }
});

batchSnoozeButton.addEventListener('click', async () => {
  try {
    await runBatchAction('snooze');
  } catch (error) {
    statusElement.textContent = `Batch update failed: ${error.message}`;
  }
});

deleteAllJobsButton.addEventListener('click', async () => {
  try {
    await handleDeleteAllJobs();
  } catch (error) {
    statusElement.textContent = `Delete All Jobs failed: ${error.message}`;
  }
});

saveMasterResumeButton.addEventListener('click', async () => {
  try {
    const updatedResume = await saveMasterResume();
    renderMasterResume(updatedResume);
    masterResumeStatusElement.textContent = `Master resume saved. Last updated ${formatTimestamp(updatedResume.updated_at)}.`;
  } catch (error) {
    masterResumeStatusElement.textContent = `Save failed: ${error.message}`;
  }
});

runIngestNowButton.addEventListener('click', async () => {
  try {
    const run = await runIngestNow();
    ingestRunStatusElement.textContent = `Run queued: ${run.run_id}`;
    await loadJobs();
  } catch (error) {
    ingestRunStatusElement.textContent = `Run failed: ${error.message}`;
  }
});

refreshButton.addEventListener('click', loadJobs);
searchInput.addEventListener('input', renderView);
nextActionFilter.addEventListener('change', () => {
  activeNextAction = nextActionFilter.value;
  renderView();
});
windowFilter.addEventListener('change', loadJobs);

loadJobs();
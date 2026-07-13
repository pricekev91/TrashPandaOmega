const statusElement = document.getElementById('feed-page-status');
const ingestSummaryElement = document.getElementById('ingest-summary');
const feedHealthElement = document.getElementById('feed-health');
const ingestRunsElement = document.getElementById('ingest-runs');
const ingestRunStatusElement = document.getElementById('ingest-run-status');
const runIngestNowButton = document.getElementById('run-ingest-now-button');
const refreshFeedsButton = document.getElementById('refresh-feeds-button');

const feedConfigForm = document.getElementById('feed-config-form');
const feedConfigListElement = document.getElementById('feed-config-list');
const feedNameInput = document.getElementById('feed-name');
const feedSourceInput = document.getElementById('feed-source');
const feedUrlInput = document.getElementById('feed-url');
const feedIncludeInput = document.getElementById('feed-include');
const feedExcludeInput = document.getElementById('feed-exclude');
const feedLocationInput = document.getElementById('feed-location');
const feedRadiusInput = document.getElementById('feed-radius');
const feedDaysInput = document.getElementById('feed-days');
const feedHourInput = document.getElementById('feed-hour');
const feedPagesInput = document.getElementById('feed-pages');

let feedConfigs = [];
let ingestRuns = [];
let latestIngestState = null;
let feedsApiAvailable = true;

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
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

async function loadFeedConfigs() {
  const response = await fetch('/api/v1/feeds');
  if (response.status === 404) {
    feedsApiAvailable = false;
    feedConfigs = [];
    return;
  }
  if (!response.ok) {
    throw new Error(`Feeds API returned ${response.status}`);
  }
  feedsApiAvailable = true;
  feedConfigs = await response.json();
}

async function loadIngestState() {
  const response = await fetch('/api/v1/ingest-state');
  if (!response.ok) {
    throw new Error(`Ingest state returned ${response.status}`);
  }
  latestIngestState = await response.json();
}

async function loadIngestRuns() {
  const response = await fetch('/api/v1/ingest-runs?limit=12');
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

function renderFeedConfigs() {
  if (!feedsApiAvailable) {
    feedConfigListElement.innerHTML = '<div class="empty compact-empty">This deployment does not expose /api/v1/feeds yet. Redeploy backend to enable feed CRUD.</div>';
    return;
  }

  if (!feedConfigs.length) {
    feedConfigListElement.innerHTML = '<div class="empty compact-empty">No feed configs yet.</div>';
    return;
  }

  feedConfigListElement.innerHTML = feedConfigs.map((feed) => `
    <article class="feed-config-card">
      <div>
        <p class="feed-name">${escapeHtml(feed.name)}</p>
        <p class="feed-meta">${escapeHtml(feed.source_site)} · ${escapeHtml(feed.location_hint || 'location not set')}</p>
        <p class="feed-meta">days ${escapeHtml(feed.schedule_days)} at ${feed.schedule_hour_local}:00 · max ${feed.max_pages_per_run} pages</p>
      </div>
      <label class="feed-toggle">
        <input type="checkbox" data-feed-toggle="${feed.id}" ${feed.enabled ? 'checked' : ''}>
        <span>${feed.enabled ? 'Enabled' : 'Disabled'}</span>
      </label>
    </article>
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

function renderView() {
  renderFeedConfigs();
  renderFeedHealth();
  renderIngestRuns();

  if (!feedsApiAvailable) {
    statusElement.textContent = 'Feed CRUD API unavailable on this deployment. Redeploy backend to use Add Feed and feed toggles.';
    return;
  }

  statusElement.textContent = `${feedConfigs.length} configured feed${feedConfigs.length === 1 ? '' : 's'} loaded.`;
}

async function loadPageData() {
  try {
    await Promise.all([loadFeedConfigs(), loadIngestState(), loadIngestRuns()]);
    renderView();
  } catch (error) {
    statusElement.textContent = `Load failed: ${error.message}`;
  }
}

feedConfigListElement.addEventListener('change', async (event) => {
  const checkbox = event.target.closest('[data-feed-toggle]');
  if (!checkbox) {
    return;
  }

  try {
    await updateFeedConfig(checkbox.dataset.feedToggle, { enabled: checkbox.checked });
    await loadPageData();
  } catch (error) {
    checkbox.checked = !checkbox.checked;
    statusElement.textContent = `Feed update failed: ${error.message}`;
  }
});

feedConfigForm.addEventListener('submit', async (event) => {
  event.preventDefault();

  if (!feedsApiAvailable) {
    statusElement.textContent = 'Cannot add feed until backend /api/v1/feeds is deployed.';
    return;
  }

  try {
    await createFeedConfig({
      name: feedNameInput.value.trim(),
      source_site: feedSourceInput.value,
      search_url: feedUrlInput.value.trim(),
      include_keywords: feedIncludeInput.value.trim(),
      exclude_keywords: feedExcludeInput.value.trim(),
      location_hint: feedLocationInput.value.trim(),
      radius_miles: feedRadiusInput.value ? Number(feedRadiusInput.value) : null,
      schedule_days: feedDaysInput.value.trim() || 'mon,thu',
      schedule_hour_local: Number(feedHourInput.value),
      max_pages_per_run: Number(feedPagesInput.value),
      enabled: true,
    });

    feedConfigForm.reset();
    feedDaysInput.value = 'mon,thu';
    feedHourInput.value = '7';
    feedPagesInput.value = '3';
    feedRadiusInput.value = '35';

    await loadPageData();
    statusElement.textContent = 'Feed config saved.';
  } catch (error) {
    statusElement.textContent = `Feed config failed: ${error.message}`;
  }
});

runIngestNowButton.addEventListener('click', async () => {
  try {
    const run = await runIngestNow();
    ingestRunStatusElement.textContent = `Run queued: ${run.run_id}`;
    await loadPageData();
  } catch (error) {
    ingestRunStatusElement.textContent = `Run failed: ${error.message}`;
  }
});

refreshFeedsButton.addEventListener('click', loadPageData);

loadPageData();

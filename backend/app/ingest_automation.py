from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from backend.app.models import IngestFeedConfig, IngestRun, Job


log = logging.getLogger(__name__)


class _JobLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.page_title = ""
        self.links: list[tuple[str, str]] = []
        self._active_href: str | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self.in_title = True
        if tag == "a":
            attr_map = dict(attrs)
            href = (attr_map.get("href") or "").strip()
            if href:
                self._active_href = href
                self._active_text = []

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.page_title += data
        if self._active_href is not None:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag == "a" and self._active_href is not None:
            text = " ".join(part.strip() for part in self._active_text if part.strip())
            self.links.append((self._active_href, text))
            self._active_href = None
            self._active_text = []


def _sanitize_slug(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return lowered.strip("-") or "feed"


def _request_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": "TrashPanda/0.2 (+self-hosted ingest automation)"})
    with urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def _collect_feed_pages_http(feed: IngestFeedConfig, feed_dir: Path) -> tuple[int, list[str]]:
    warnings: list[str] = []
    page_count = 0

    try:
        html = _request_html(feed.search_url)
    except URLError as error:
        raise RuntimeError(f"Unable to fetch search URL: {error}") from error

    page_count += 1
    html_path = feed_dir / "page-001.html"
    html_path.write_text(html, encoding="utf-8")
    meta_path = feed_dir / "page-001.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "source_site": feed.source_site,
                "feed_name": feed.name,
                "search_url": feed.search_url,
                "page_number": 1,
                "collector_mode": "http_fetch",
                "fetched_at": datetime.utcnow().isoformat() + "Z",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if feed.max_pages_per_run > 1:
        warnings.append("HTTP fetch collector saved page 1 only. Install Playwright for page-to-page browser automation.")

    return page_count, warnings


def _collect_feed_pages_browser(feed: IngestFeedConfig, feed_dir: Path) -> tuple[int, list[str]]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception:
        return _collect_feed_pages_http(feed, feed_dir)

    page_count = 0
    warnings: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(feed.search_url, wait_until="domcontentloaded", timeout=45000)

        for page_number in range(1, max(1, feed.max_pages_per_run) + 1):
            html_path = feed_dir / f"page-{page_number:03d}.html"
            meta_path = feed_dir / f"page-{page_number:03d}.meta.json"
            html_path.write_text(page.content(), encoding="utf-8")
            meta_path.write_text(
                json.dumps(
                    {
                        "source_site": feed.source_site,
                        "feed_name": feed.name,
                        "search_url": feed.search_url,
                        "page_number": page_number,
                        "collector_mode": "playwright",
                        "fetched_at": datetime.utcnow().isoformat() + "Z",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            page_count += 1

            if page_number >= feed.max_pages_per_run:
                break

            try:
                page.click('a[aria-label*="Next"],button[aria-label*="Next"],a[rel="next"]', timeout=5000)
                page.wait_for_timeout(800)
            except PlaywrightTimeoutError:
                warnings.append("No next-page control found; stopped early.")
                break

        browser.close()

    return page_count, warnings


def collect_feed_artifacts(feed: IngestFeedConfig, run_root: Path) -> tuple[int, list[str], Path]:
    feed_dir = run_root / _sanitize_slug(feed.name)
    feed_dir.mkdir(parents=True, exist_ok=True)

    source_normalized = (feed.source_site or "").strip().lower()
    use_browser = source_normalized in {"linkedin", "indeed", "glassdoor", "ziprecruiter", "google_jobs", "flexjobs"}

    if use_browser:
        pages, warnings = _collect_feed_pages_browser(feed, feed_dir)
    else:
        pages, warnings = _collect_feed_pages_http(feed, feed_dir)

    return pages, warnings, feed_dir


def _extract_candidate_links(base_url: str, html_content: str) -> tuple[str, list[tuple[str, str]]]:
    parser = _JobLinkParser()
    parser.feed(html_content)

    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, text in parser.links:
        absolute_href = urljoin(base_url, href)
        href_lower = absolute_href.lower()
        if "job" not in href_lower and "career" not in href_lower and "position" not in href_lower:
            continue
        if absolute_href in seen:
            continue
        seen.add(absolute_href)
        normalized.append((absolute_href, text.strip()))

    return parser.page_title.strip(), normalized


def parse_artifacts_into_jobs(db: Session, feed: IngestFeedConfig, feed_dir: Path) -> tuple[int, int, int, int]:
    html_files = sorted(feed_dir.glob("page-*.html"))
    processed_artifacts = 0
    inserted = 0
    updated = 0
    skipped = 0

    for html_file in html_files:
        processed_artifacts += 1
        html = html_file.read_text(encoding="utf-8", errors="replace")
        page_title, candidates = _extract_candidate_links(feed.search_url, html)

        if not candidates:
            skipped += 1
            continue

        for source_url, link_text in candidates[:50]:
            source_key = source_url
            title = link_text or page_title or "Imported job listing"
            summary = (
                f"Imported from HTML artifact. Feed={feed.name}; "
                f"location_hint={feed.location_hint or 'unspecified'}; include_keywords={feed.include_keywords or 'none'}"
            )

            existing = db.query(Job).filter(Job.source_key == source_key).one_or_none()
            if existing is None:
                db.add(
                    Job(
                        title=title[:255],
                        company="Unknown company",
                        location=feed.location_hint or "Unknown",
                        source=f"artifact-{feed.source_site}",
                        source_key=source_key,
                        source_url=source_url,
                        score=55.0,
                        status="queued",
                        next_action="research",
                        tailoring_required=False,
                        summary=summary[:320],
                    )
                )
                inserted += 1
            else:
                existing.title = title[:255]
                existing.location = feed.location_hint or existing.location
                existing.source_url = source_url
                existing.summary = summary[:320]
                existing.updated_at = datetime.utcnow()
                db.add(existing)
                updated += 1

    return processed_artifacts, inserted, updated, skipped


def run_ingest_automation(db: Session, run: IngestRun, feeds: list[IngestFeedConfig], artifacts_root: Path) -> IngestRun:
    run_root = artifacts_root / "runs" / run.id
    run_root.mkdir(parents=True, exist_ok=True)

    run.status = "running"
    run.started_at = datetime.utcnow()
    run.feeds_total = len(feeds)
    db.add(run)
    db.commit()

    errors: list[str] = []

    for index, feed in enumerate(feeds, start=1):
        if not feed.enabled:
            continue

        try:
            pages_collected, warnings, feed_dir = collect_feed_artifacts(feed, run_root)
            artifacts_processed, inserted, updated, skipped = parse_artifacts_into_jobs(db, feed, feed_dir)

            run.pages_collected += pages_collected
            run.artifacts_processed += artifacts_processed
            run.jobs_inserted += inserted
            run.jobs_updated += updated
            run.jobs_skipped += skipped
            run.feeds_completed = index

            if warnings:
                errors.extend(f"{feed.name}: {warning}" for warning in warnings)

            db.add(run)
            db.commit()
        except Exception as error:
            log.exception("automation ingest feed failed: %s", feed.name)
            errors.append(f"{feed.name}: {error}")
            run.feeds_completed = index
            db.add(run)
            db.commit()

    run.finished_at = datetime.utcnow()
    run.status = "completed" if not errors else "completed_with_warnings"
    run.error_summary = " | ".join(errors)[:2000] if errors else None
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

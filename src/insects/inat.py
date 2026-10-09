"""Thin iNaturalist API client.

Only the pieces this project needs: a polite session, cursor pagination over
observations, and batched taxon lookups. Every network call in the project goes
through here so that rate limiting and retry behaviour are defined once.
"""
from __future__ import annotations

import logging
import time
from typing import Iterator

import requests

from . import config

log = logging.getLogger(__name__)


class INatClient:
    """A rate-limited, retrying client for the iNaturalist v1 API."""

    def __init__(self, delay: float = config.REQUEST_DELAY,
                 max_retries: int = config.MAX_RETRIES):
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})
        self._last_call = 0.0

    def _throttle(self) -> None:
        elapsed = time.perf_counter() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.perf_counter()

    def get(self, path: str, params: dict | None = None) -> dict:
        """GET {API}/{path}, retrying on rate limits and transient failures."""
        url = f"{config.API}/{path.lstrip('/')}"
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                r = self.session.get(url, params=params, timeout=60)
            except requests.RequestException as exc:
                wait = config.BACKOFF_BASE * (2 ** attempt)
                log.warning("%s on %s; retrying in %.0fs", type(exc).__name__, url, wait)
                time.sleep(wait)
                continue

            if r.status_code == 200:
                return r.json()

            # 429 = rate limited, 5xx = transient. Anything else is our fault.
            if r.status_code == 429 or r.status_code >= 500:
                wait = config.BACKOFF_BASE * (2 ** attempt)
                log.warning("HTTP %s on %s; backing off %.0fs",
                            r.status_code, url, wait)
                time.sleep(wait)
                continue

            r.raise_for_status()

        raise RuntimeError(f"giving up on {url} after {self.max_retries} attempts")

    def iter_observations(self, **overrides) -> Iterator[dict]:
        """Yield every matching observation, paging by descending id.

        The API caps offset pagination at 10,000 records, so we cursor with
        ``id_below`` instead — this is the documented way to walk a full result
        set and is what makes the pull reproducible.
        """
        params = {
            "place_id": config.PLACE_ID,
            "quality_grade": config.QUALITY_GRADE,
            "iconic_taxa": config.ICONIC_TAXA,
            "photo_license": config.PHOTO_LICENCES,
            "photos": "true",
            "per_page": config.PER_PAGE,
            "order_by": "id",
            "order": "desc",
        }
        params.update(overrides)

        cursor = None
        seen = 0
        total = None
        while True:
            page = dict(params)
            if cursor is not None:
                page["id_below"] = cursor

            payload = self.get("observations", page)
            if total is None:
                total = payload.get("total_results", 0)
                log.info("%s observations to fetch", f"{total:,}")

            batch = payload.get("results", [])
            if not batch:
                break

            yield from batch

            seen += len(batch)
            log.info("fetched %s/%s observations (%.1f%%)",
                     f"{seen:,}", f"{total:,}", 100 * seen / total if total else 0)
            cursor = batch[-1]["id"]

    def fetch_taxa(self, taxon_ids: list[int]) -> list[dict]:
        """Look up taxa by id, batched at the API's 30-per-request limit."""
        out: list[dict] = []
        ids = sorted({int(t) for t in taxon_ids})
        for i in range(0, len(ids), config.TAXA_BATCH):
            chunk = ids[i:i + config.TAXA_BATCH]
            payload = self.get("taxa/" + ",".join(str(c) for c in chunk))
            out.extend(payload.get("results", []))
            log.info("resolved %s/%s taxa", f"{len(out):,}", f"{len(ids):,}")
        return out

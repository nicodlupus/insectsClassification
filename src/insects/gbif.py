"""Step 6a - harvest additional butterfly images from GBIF.

The iNaturalist set built in steps 1-3 is one photographic regime: one platform,
one community, one set of crop conventions. A classifier trained on it learns
some of iNaturalist along with the butterflies. GBIF aggregates hundreds of
other publishers (Observation.org, museum collections, national atlases), so the
images it yields differ in camera, background and framing - which is the point.

GBIF also republishes iNaturalist itself, and that dataset is excluded here: it
is exactly the data we already hold, and re-downloading it would inflate the
class counts with duplicates.

    python -m insects.gbif --match         # resolve the 33 species to taxonKeys
    python -m insects.gbif --harvest       # pull media rows for each taxonKey
"""
from __future__ import annotations

import argparse
import logging
import time
from typing import Iterator

import pandas as pd
import requests

from . import config

log = logging.getLogger(__name__)

# Aligned with butterfly_images.csv wherever a column means the same thing, so
# the two tables concatenate in step 6 without a rename layer.
MEDIA_COLS = [
    "photo_id", "occurrence_key", "label_species", "taxon_name", "gbif_taxon_key",
    "photo_url_medium", "license_code", "attribution", "photographer",
    "publisher", "dataset_key", "country", "basis_of_record", "observed_on",
    "source",
]


class GBIFClient:
    """A rate-limited, retrying client for the GBIF v1 API.

    Deliberately the same shape as ``INatClient``: one throttle, one backoff
    policy, one User-Agent, defined once per API rather than at each call site.
    """

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
        """GET {GBIF_API}/{path}, retrying on rate limits and transient failures."""
        url = f"{config.GBIF_API}/{path.lstrip('/')}"
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

            if r.status_code == 429 or r.status_code >= 500:
                wait = config.BACKOFF_BASE * (2 ** attempt)
                log.warning("HTTP %s on %s; backing off %.0fs",
                            r.status_code, url, wait)
                time.sleep(wait)
                continue

            r.raise_for_status()

        raise RuntimeError(f"giving up on {url} after {self.max_retries} attempts")

    def match_taxon(self, name: str) -> dict:
        """Resolve a scientific name to a GBIF taxonKey via /species/match.

        Harvesting by key rather than by name is the same rule the project
        already applies to iNaturalist (``BUTTERFLY_TAXON_ID``): names are
        synonymised and reused across kingdoms, keys are not.
        """
        payload = self.get("species/match", {"name": name, "rank": "SPECIES",
                                             "strict": "false"})
        return {
            "label_species": name,
            "gbif_taxon_key": payload.get("usageKey"),
            "matched_name": payload.get("scientificName"),
            "match_type": payload.get("matchType"),
            "confidence": payload.get("confidence"),
            "status": payload.get("status"),
        }

    def iter_occurrences(self, taxon_key: int, limit: int) -> Iterator[dict]:
        """Yield occurrence records carrying still images, newest first.

        GBIF caps offset pagination at 100,000 records, far above anything this
        harvest needs, so plain offset paging is safe here (unlike the iNat pull,
        which had to cursor with ``id_below``).
        """
        offset = 0
        while offset < limit:
            payload = self.get("occurrence/search", {
                "taxonKey": taxon_key,
                "mediaType": "StillImage",
                "limit": min(config.GBIF_PAGE, limit - offset),
                "offset": offset,
            })
            batch = payload.get("results", [])
            if not batch:
                return
            yield from batch
            offset += len(batch)
            if payload.get("endOfRecords"):
                return


def licence_code(url: str | None) -> str | None:
    """Map a GBIF licence URL onto the project's short licence vocabulary."""
    if not url:
        return None
    # Match on the stable middle of the URL: GBIF emits both ".../by-nc/4.0/"
    # and ".../by-nc/4.0/legalcode", and both http and https forms.
    for fragment, code in config.GBIF_LICENCE_CODES.items():
        if fragment in url:
            return code
    return None


def is_inaturalist(record: dict, media: dict) -> bool:
    """True if this image is one we already hold from the iNaturalist pull."""
    if record.get("datasetKey") == config.GBIF_INAT_DATASET_KEY:
        return True
    if (media.get("publisher") or "").strip().lower() == "inaturalist":
        return True
    # Some publishers mirror iNat URLs without declaring the source.
    return "inaturalist" in (media.get("identifier") or "").lower()


def flatten(record: dict, label_species: str) -> list[dict]:
    """Turn one GBIF occurrence into one row per usable still image."""
    rows = []
    for i, media in enumerate(record.get("media") or []):
        if media.get("type") != "StillImage":
            continue
        url = media.get("identifier")
        if not url or is_inaturalist(record, media):
            continue
        if (media.get("format") or "image/jpeg") not in ("image/jpeg", "image/png"):
            continue

        # The occurrence-level licence is the fallback: a few publishers state
        # the licence once per record rather than on each media entry.
        code = licence_code(media.get("license")) or licence_code(record.get("license"))
        if code is None:
            continue

        creator = media.get("creator") or record.get("recordedBy")
        holder = media.get("rightsHolder") or record.get("rightsHolder")
        rows.append({
            # A stable, collision-free file name: occurrence key + media index.
            # download.target_path() writes "<photo_id>.jpg", so this string is
            # what the image is called on disk and in Drive.
            "photo_id": f"gbif-{record.get('key')}-{i}",
            "occurrence_key": record.get("key"),
            "label_species": label_species,
            "taxon_name": record.get("species") or record.get("acceptedScientificName"),
            "gbif_taxon_key": record.get("taxonKey"),
            "photo_url_medium": url,
            "license_code": code,
            "attribution": f"(c) {holder or creator or 'unknown'} ({code})",
            "photographer": creator,
            "publisher": media.get("publisher") or record.get("publishingOrgKey"),
            "dataset_key": record.get("datasetKey"),
            "country": record.get("country"),
            "basis_of_record": record.get("basisOfRecord"),
            "observed_on": record.get("eventDate"),
            "source": "gbif",
        })
    return rows


def match_all(species: list[str], out_path=None) -> pd.DataFrame:
    """Resolve every label_species to a GBIF taxonKey and cache the table."""
    out_path = out_path or config.GBIF_TAXA_CSV
    client = GBIFClient()
    rows = []
    for name in species:
        row = client.match_taxon(name)
        log.info("%-28s -> %s (%s, confidence %s)", name, row["gbif_taxon_key"],
                 row["match_type"], row["confidence"])
        rows.append(row)

    table = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path, index=False)

    # Anything not EXACT is a name the harvest would silently get wrong; it is
    # surfaced here rather than discovered later as a mislabelled class.
    suspect = table[table["match_type"] != "EXACT"]
    if not suspect.empty:
        log.warning("%s species did not match exactly:\n%s", len(suspect),
                    suspect[["label_species", "matched_name", "match_type"]])
    return table


def shortfall(target: int, media_path=None) -> dict[str, int]:
    """How many more images each species still needs, from a previous harvest."""
    media_path = media_path or config.GBIF_MEDIA_CSV
    if not media_path.exists():
        return {}
    have = pd.read_csv(media_path)["label_species"].value_counts()
    return {name: target - int(n) for name, n in have.items() if n < target}


def harvest(taxa: pd.DataFrame, wanted: dict[str, int] | None = None,
            out_path=None, oversample: float = 3.0,
            append: bool = False) -> pd.DataFrame:
    """Pull media rows for each species, stopping once `wanted` are collected.

    `oversample` exists because the useful rows are a minority of what GBIF
    returns: iNat records are dropped, unlicensed and non-photo media are
    dropped, and some images will fail to download later. Asking for a multiple
    of the target avoids a second pass for most species.
    """
    out_path = out_path or config.GBIF_MEDIA_CSV
    wanted = wanted or {}
    client = GBIFClient()
    collected: list[dict] = []

    # A top-up run must not re-collect what it already has: the URLs of the
    # previous harvest are loaded as the seen-set, so a second pass only ever
    # deepens the shortfall species.
    previous = pd.DataFrame(columns=MEDIA_COLS)
    already: set[str] = set()
    if append and out_path.exists():
        previous = pd.read_csv(out_path)
        already = set(previous["photo_url_medium"])
        log.info("topping up on %s existing rows", f"{len(previous):,}")

    for _, taxon in taxa.iterrows():
        name = taxon["label_species"]
        key = taxon["gbif_taxon_key"]
        if pd.isna(key):
            log.warning("%s has no GBIF key; skipped", name)
            continue

        target = wanted.get(name, config.TOPUP_PER_SPECIES)
        if target <= 0:
            log.info("%-28s already at target; skipped", name)
            continue

        rows: list[dict] = []
        seen_urls: set[str] = set(already)
        for record in client.iter_occurrences(int(key), int(target * oversample)):
            for row in flatten(record, name):
                # The same photo can appear under several occurrences; the URL
                # is the only identifier shared across publishers.
                if row["photo_url_medium"] in seen_urls:
                    continue
                seen_urls.add(row["photo_url_medium"])
                rows.append(row)
            if len(rows) >= target:
                break

        rows = rows[:target]
        collected.extend(rows)
        log.info("%-28s %s images", name, f"{len(rows):,}")

    table = pd.concat([previous, pd.DataFrame(collected, columns=MEDIA_COLS)],
                      ignore_index=True)
    table = table.drop_duplicates(subset="photo_url_medium", keep="first")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path, index=False)
    log.info("wrote %s GBIF media rows (+%s new) -> %s",
             f"{len(table):,}", f"{len(collected):,}", out_path)
    return table


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--match", action="store_true", help="resolve species to taxonKeys")
    ap.add_argument("--harvest", action="store_true", help="pull media rows")
    ap.add_argument("--topup", action="store_true",
                    help="re-harvest only the species still short, digging deeper")
    ap.add_argument("--per-species", type=int, default=config.TOPUP_PER_SPECIES)
    ap.add_argument("--oversample", type=float, default=3.0,
                    help="records scanned per image wanted; raise it for species "
                         "whose GBIF presence is mostly iNaturalist")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    existing = pd.read_csv(config.BUTTERFLY_IMAGES_CSV)
    species = sorted(existing["label_species"].dropna().unique())

    if args.match or not config.GBIF_TAXA_CSV.exists():
        taxa = match_all(species)
    else:
        taxa = pd.read_csv(config.GBIF_TAXA_CSV)

    if args.topup:
        gap = shortfall(args.per_species)
        log.info("%s species short of %s", len(gap), args.per_species)
        harvest(taxa[taxa["label_species"].isin(gap)], gap,
                oversample=args.oversample, append=True)
    elif args.harvest:
        harvest(taxa, {name: args.per_species for name in species},
                oversample=args.oversample)


if __name__ == "__main__":
    main()

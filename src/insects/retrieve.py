"""Step 1 - pull observations from iNaturalist into a flat photo-level table.

Supersedes the original ``Data/retriever.py``. The important difference is the
set of fields kept: the first pull discarded ``taxon.ancestor_ids`` (which is
what answers "is this a butterfly?"), the taxon id, the photo id (the only
stable key for naming downloaded files), the observation date and the
coordinates. All of them are free — they were already in the same payload.

One row per photo, exactly as before, so the row granularity the audit was
written against is unchanged.

    python -m insects.retrieve                # full pull
    python -m insects.retrieve --limit 400    # smoke test
"""
from __future__ import annotations

import argparse
import csv
import logging

from . import config
from .inat import INatClient

log = logging.getLogger(__name__)

FIELDS = [
    "observation_id",
    "photo_id",
    "taxon_id",
    "taxon_name",
    "taxon_rank",
    "ancestor_ids",       # pipe-delimited; CSV-safe and re-parsable
    "iconic_taxon_name",
    "photo_url",
    "photo_width",
    "photo_height",
    "license_code",
    "attribution",
    "observed_on",
    "latitude",
    "longitude",
    "positional_accuracy",
    "location",
]


def flatten(obs: dict) -> list[dict]:
    """Turn one observation into one row per photo."""
    taxon = obs.get("taxon") or {}
    ancestors = taxon.get("ancestor_ids") or []

    # `location` on the observation is a "lat,lon" string; place_guess is the
    # user-typed free text the audit already knows about.
    lat = lon = None
    coords = obs.get("location")
    if coords and "," in coords:
        lat, _, lon = coords.partition(",")

    base = {
        "observation_id": obs.get("id"),
        "taxon_id": taxon.get("id"),
        "taxon_name": taxon.get("name"),
        "taxon_rank": taxon.get("rank"),
        "ancestor_ids": "|".join(str(a) for a in ancestors),
        "iconic_taxon_name": taxon.get("iconic_taxon_name"),
        "observed_on": obs.get("observed_on"),
        "latitude": lat,
        "longitude": lon,
        "positional_accuracy": obs.get("positional_accuracy"),
        "location": obs.get("place_guess"),
    }

    rows = []
    for photo in obs.get("photos", []):
        dims = photo.get("original_dimensions") or {}
        rows.append({
            **base,
            "photo_id": photo.get("id"),
            "photo_url": photo.get("url"),
            "photo_width": dims.get("width"),
            "photo_height": dims.get("height"),
            "license_code": photo.get("license_code"),
            "attribution": photo.get("attribution"),
        })
    return rows


def retrieve(out_path=None, limit: int | None = None) -> int:
    """Write the photo-level table to CSV. Returns the number of rows written."""
    out_path = out_path or config.OBSERVATIONS_CSV
    out_path.parent.mkdir(parents=True, exist_ok=True)

    client = INatClient()
    n_rows = n_obs = 0

    # Streamed to disk rather than accumulated in memory, so an interrupted run
    # still leaves a readable partial file.
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for obs in client.iter_observations():
            rows = flatten(obs)
            writer.writerows(rows)
            n_rows += len(rows)
            n_obs += 1
            if limit and n_obs >= limit:
                log.info("stopping early at --limit %s observations", limit)
                break

    log.info("wrote %s photo rows from %s observations -> %s",
             f"{n_rows:,}", f"{n_obs:,}", out_path)
    return n_rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=lambda p: __import__("pathlib").Path(p),
                    default=config.OBSERVATIONS_CSV)
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N observations (smoke test)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    retrieve(args.out, args.limit)


if __name__ == "__main__":
    main()

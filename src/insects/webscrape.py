"""Step 6b - top up the classes that GBIF cannot fill, from image search.

GBIF runs dry on exactly the species this project cares most about: the Cyprus
endemics (*Maniola cypricola*, *Hipparchia cypriensis*, *Glaucopsyche paphos*)
have almost no openly licensed non-iNaturalist records anywhere. This module is
the last resort for those classes, and it is deliberately the smallest source.

Two properties of these rows are different from every other row in the project,
and both are recorded rather than hidden:

* **No licence.** Search results carry no rights metadata, so `license_code` is
  ``"unknown"`` and `redistributable` is False. These images may be used to
  train a model for the coursework; they may not be republished as a dataset.
* **No verified identification.** GBIF and iNaturalist rows were identified by
  naturalists against a taxon key. These were identified by whoever wrote the
  page the image sits on. They need a manual spot-check before use - see
  ``Analysis/FinalDataset.ipynb``.

    python -m insects.webscrape --report     # what is still short, no network
    python -m insects.webscrape --harvest
"""
from __future__ import annotations

import argparse
import logging
import time

import pandas as pd

from . import config

log = logging.getLogger(__name__)

MEDIA_COLS = [
    "photo_id", "label_species", "photo_url_medium", "license_code",
    "attribution", "photographer", "page_url", "page_title",
    "width", "height", "query", "source",
]

# Two phrasings per species. The first is the plain scientific name, which is
# what museum, atlas and field-guide pages use. The second adds "butterfly" and
# excludes "moth", because several of these genera have moth lookalikes that
# search engines happily mix in.
QUERY_TEMPLATES = [
    '"{species}"',
    '"{species}" butterfly -moth',
    # Specimen and field-guide phrasings surface museum plates and atlas pages
    # that the plain name misses.
    '"{species}" specimen',
    '"{species}" Cyprus',
    # Search engines rank by page language, so the same species in another
    # language reaches a largely disjoint set of European nature sites.
    '"{species}" papillon',
    '"{species}" mariposa',
    '"{species}" Schmetterling',
]


def _as_int(value) -> int | None:
    """Search results report dimensions as strings, and sometimes not at all."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def search_species(species: str, wanted: int,
                   cap: int = config.WEB_CANDIDATE_CAP,
                   already: set[str] | None = None,
                   start_index: int = 0) -> list[dict]:
    """Collect candidate image URLs for one species across every query form."""
    from ddgs import DDGS           # imported lazily: only this path needs it

    rows: list[dict] = []
    seen: set[str] = set(already or ())

    with DDGS() as ddgs:
        for template in QUERY_TEMPLATES:
            if len(rows) >= wanted:
                break
            query = template.format(species=species)
            try:
                results = ddgs.images(query, max_results=cap)
            except Exception as exc:
                # A failed query costs one species one phrasing, never the run.
                log.warning("%s: query %r failed (%s)", species, query,
                            type(exc).__name__)
                continue

            for hit in results:
                url = hit.get("image")
                if not url or url in seen:
                    continue
                seen.add(url)

                # Cheap pre-filters on the metadata the engine already gives us,
                # so obviously unusable candidates never cost a download.
                w, h = _as_int(hit.get("width")), _as_int(hit.get("height"))
                if w and h and min(w, h) < config.MIN_IMAGE_PX:
                    continue
                if not url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png")):
                    continue

                rows.append({
                    # Positional id, so a re-run that returns results in a
                    # different order cannot collide with files already on disk.
                    "photo_id": f"web-{species.replace(' ', '_')}"
                                f"-{start_index + len(rows):04d}",
                    "label_species": species,
                    "photo_url_medium": url,
                    "license_code": "unknown",
                    "attribution": f"source: {hit.get('url') or 'unknown'} "
                                   f"(licence unverified, not for redistribution)",
                    "photographer": None,
                    "page_url": hit.get("url"),
                    "page_title": hit.get("title"),
                    "width": w,
                    "height": h,
                    "query": query,
                    "source": "web_scrape",
                })
                if len(rows) >= wanted:
                    break

            time.sleep(config.REQUEST_DELAY)   # same politeness as the APIs

    log.info("%-28s %s candidates", species, f"{len(rows):,}")
    return rows


def next_index(existing_ids: pd.Series) -> int:
    """One past the highest index already used for a species.

    Counting the rows instead would be wrong: ids are assigned during the
    search, and the URL de-duplication afterwards removes some of them, so the
    surviving ids have gaps. A later append that numbered from the row count
    would land on ids that are still in use - and since the id is the file name,
    two different images would end up writing to one file.
    """
    numbers = (existing_ids.astype(str).str.rsplit("-", n=1).str[-1]
               .pipe(pd.to_numeric, errors="coerce").dropna())
    return int(numbers.max()) + 1 if len(numbers) else 0


def harvest(gaps: dict[str, int], out_path=None,
            oversample: float = 1.6, append: bool = False) -> pd.DataFrame:
    """Search for every species in `gaps` and write the candidate table.

    `oversample` covers the images that will fail the download-time checks
    (dead links, HTML error pages served as .jpg, thumbnails). Unlike GBIF the
    cost here is a search query, not a page of API results, so the multiple is
    kept small.
    """
    out_path = out_path or config.WEB_MEDIA_CSV

    previous = pd.DataFrame(columns=MEDIA_COLS)
    if append and out_path.exists():
        previous = pd.read_csv(out_path)
        log.info("adding to %s existing candidates", f"{len(previous):,}")

    collected: list[dict] = []
    for species, need in gaps.items():
        prior = previous.loc[previous["label_species"] == species, "photo_id"]
        collected.extend(search_species(
            species, int(need * oversample),
            already=set(previous["photo_url_medium"]),
            start_index=next_index(prior)))

    table = pd.concat([previous, pd.DataFrame(collected, columns=MEDIA_COLS)],
                      ignore_index=True)
    table = table.drop_duplicates(subset="photo_url_medium", keep="first")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path, index=False)
    log.info("wrote %s candidate rows -> %s", f"{len(table):,}", out_path)
    return table


def remaining_gaps(target: int = config.TOPUP_PER_SPECIES) -> dict[str, int]:
    """Species still short of `target` after the GBIF harvest."""
    existing = pd.read_csv(config.BUTTERFLY_IMAGES_CSV)
    species = sorted(existing["label_species"].dropna().unique())

    have = pd.Series(0, index=species, dtype=int)
    for path in (config.GBIF_MEDIA_CSV, config.WEB_MEDIA_CSV):
        if path.exists():
            counts = pd.read_csv(path)["label_species"].value_counts()
            have = have.add(counts.reindex(species).fillna(0).astype(int),
                            fill_value=0)

    gaps = (target - have)
    return {name: int(n) for name, n in gaps.items() if n > 0}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", action="store_true", help="show gaps, no network")
    ap.add_argument("--harvest", action="store_true")
    ap.add_argument("--append", action="store_true",
                    help="keep existing candidates and search for the rest")
    ap.add_argument("--per-species", type=int, default=config.TOPUP_PER_SPECIES)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    gaps = remaining_gaps(args.per_species)
    log.info("%s species short, %s images total", len(gaps), f"{sum(gaps.values()):,}")

    if args.report:
        for name, n in sorted(gaps.items(), key=lambda kv: -kv[1]):
            print(f"{name:<28} {n:>4}")
        return
    if args.harvest:
        harvest(gaps, append=args.append)


if __name__ == "__main__":
    main()

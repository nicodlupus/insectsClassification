"""Step 6c - validate the downloaded files and remove duplicates across sources.

Three sources now point at the same image tree, and they overlap: GBIF and the
search engines both index pages that mirror each other, and a mirrored copy of
an image the project already has from iNaturalist would inflate a class count
while teaching the model nothing. Exact duplicates are caught by the SHA-256 the
downloader already computes; **re-encoded** copies - the same photo at a
different size or JPEG quality, which is how mirroring normally happens - are
not, and need a perceptual hash.

This module also does the content validation the downloader deliberately does
not: the downloader's job is bytes on disk, and a 404 page served as `.jpg` is
bytes on disk.

    python -m insects.dedup
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import imagehash
import numpy as np
import pandas as pd
from PIL import Image, ImageFile

from . import config

log = logging.getLogger(__name__)

# Truncated JPEGs are common in scraped material. Reading what arrived beats
# discarding the file, and the size checks below still reject the useless ones.
ImageFile.LOAD_TRUNCATED_IMAGES = True

# Which source wins when the same photo appears twice. iNaturalist rows carry a
# research-grade identification and a licence; GBIF rows carry a licence; the
# scraped rows carry neither, so they lose every tie.
SOURCE_RANK = {"cyprus_inat": 0, "global_inat": 1, "gbif": 2, "web_scrape": 3}


def inspect(path: Path) -> dict:
    """Open one image and report its dimensions and perceptual hash.

    Returns ``ok=False`` rather than raising: one unreadable file out of 23,000
    must not end the pass.
    """
    try:
        size = path.stat().st_size
        with Image.open(path) as img:
            img = img.convert("RGB")     # phash needs a consistent mode
            width, height = img.size
            phash = str(imagehash.phash(img))
    except Exception as exc:
        return {"ok": False, "reason": f"{type(exc).__name__}", "bytes": None,
                "width": None, "height": None, "phash": None}

    if size < config.MIN_IMAGE_BYTES:
        return {"ok": False, "reason": "too_small_bytes", "bytes": size,
                "width": width, "height": height, "phash": phash}
    if min(width, height) < config.MIN_IMAGE_PX:
        return {"ok": False, "reason": "too_small_px", "bytes": size,
                "width": width, "height": height, "phash": phash}

    return {"ok": True, "reason": None, "bytes": size,
            "width": width, "height": height, "phash": phash}


def inspect_all(table: pd.DataFrame, root: Path | None = None) -> pd.DataFrame:
    """Run `inspect` over every row that has a file on disk."""
    root = root or config.IMAGES
    records = []
    for i, row in enumerate(table.itertuples(index=False), start=1):
        path = (root / str(row.label_species).replace(" ", "_")
                / f"{row.photo_id}.jpg")
        result = {"photo_id": row.photo_id, "local_path": str(path)}
        result.update(inspect(path) if path.exists()
                      else {"ok": False, "reason": "missing", "bytes": None,
                            "width": None, "height": None, "phash": None})
        records.append(result)
        if i % 2000 == 0:
            log.info("inspected %s/%s", f"{i:,}", f"{len(table):,}")
    return pd.DataFrame(records)


def _phash_bits(hashes: pd.Series) -> np.ndarray:
    """Pack 16-character hex phashes into one uint64 each.

    A perceptual hash is 64 bits; as a uint64 the Hamming distance between two
    of them is ``bitwise_count(a ^ b)``, which numpy does over whole arrays at
    once. Comparing them as strings would be several hundred times slower.
    """
    return np.array([int(h, 16) for h in hashes], dtype=np.uint64)


def near_duplicate_pairs(bits: np.ndarray, threshold: int,
                         chunk: int = 512) -> list[tuple[int, int]]:
    """All index pairs (i, j), i < j, whose hashes differ by <= `threshold`.

    Chunked so the comparison matrix is bounded: the full N x N matrix for
    23,000 images would be 4 GB, a 512-row slice of it is 94 MB.
    """
    n = len(bits)
    pairs: list[tuple[int, int]] = []
    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        block = bits[start:stop, None] ^ bits[None, :]        # (chunk, n)
        distance = np.bitwise_count(block)
        rows, cols = np.nonzero(distance <= threshold)
        rows = rows + start
        keep = rows < cols                # upper triangle only; drops self-pairs
        pairs.extend(zip(rows[keep].tolist(), cols[keep].tolist()))
    return pairs


def resolve_duplicates(table: pd.DataFrame,
                       threshold: int = config.PHASH_DISTANCE) -> pd.DataFrame:
    """Flag every row that duplicates a better-ranked row.

    Adds `duplicate_of`: null for rows that are kept, otherwise the `photo_id`
    of the copy that was kept instead. Nothing is deleted here - the flag is
    evidence for the datasheet, and the notebook filters on it.
    """
    table = table.copy()
    table["duplicate_of"] = pd.NA

    usable = table[table["phash"].notna()].reset_index(drop=True)
    bits = _phash_bits(usable["phash"])
    rank = usable["source"].map(SOURCE_RANK).fillna(99).to_numpy()
    ids = usable["photo_id"].to_numpy()

    # Union-find: transitive groups matter, because A can duplicate B while B
    # duplicates C without A and C being within the threshold of each other.
    parent = list(range(len(usable)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    pairs = near_duplicate_pairs(bits, threshold)
    for i, j in pairs:
        ri, rj = find(i), find(j)
        if ri != rj:
            # Point the worse-ranked root at the better-ranked one, so the
            # group's representative is always the most trustworthy source.
            if (rank[ri], ri) <= (rank[rj], rj):
                parent[rj] = ri
            else:
                parent[ri] = rj

    log.info("%s near-duplicate pairs at distance <= %s", f"{len(pairs):,}", threshold)

    duplicate_of = {}
    for i in range(len(usable)):
        root = find(i)
        if root != i:
            duplicate_of[ids[i]] = ids[root]

    table["duplicate_of"] = table["photo_id"].map(duplicate_of)
    log.info("%s rows are duplicates of a better-ranked copy",
             f"{table['duplicate_of'].notna().sum():,}")
    return table


def normalise(table: pd.DataFrame, root: Path | None = None,
              max_side: int = config.MAX_IMAGE_SIDE,
              quality: int = config.JPEG_QUALITY) -> pd.DataFrame:
    """Downscale oversized images in place; returns the table with fresh `bytes`.

    The three sources arrive at wildly different resolutions - iNaturalist
    serves ~500px "medium" files, GBIF hands back the photographer's original,
    which can be 4000px. Capping the long side does three things at once: it
    keeps the Drive upload near 2 GB instead of 5.5, it removes a resolution
    signal that would otherwise let a model separate the sources rather than the
    species, and it matches what a training pipeline would resize to anyway.

    Run this *after* `inspect_all`: `width` and `height` stay the dimensions the
    image was *published* at, which is what the source comparison is about, while
    `bytes` is refreshed to what is actually stored and uploaded.
    """
    root = root or config.IMAGES
    saved = 0
    stored: dict = {}

    for i, row in enumerate(table.itertuples(index=False), start=1):
        path = Path(row.local_path) if pd.notna(row.local_path) else None
        if path is None or not path.exists():
            continue
        try:
            before = path.stat().st_size
            with Image.open(path) as img:
                if max(img.size) > max_side:
                    img = img.convert("RGB")
                    img.thumbnail((max_side, max_side), Image.LANCZOS)
                    img.save(path, "JPEG", quality=quality, optimize=True)
            after = path.stat().st_size
            saved += before - after
            stored[row.photo_id] = after
        except Exception as exc:
            log.warning("could not resize %s (%s)", path.name, type(exc).__name__)
        if i % 2000 == 0:
            log.info("normalised %s/%s, %.2f GB saved",
                     f"{i:,}", f"{len(table):,}", saved / 1e9)

    log.info("normalisation freed %.2f GB", saved / 1e9)
    table = table.copy()
    table["bytes"] = table["photo_id"].map(stored).fillna(table["bytes"])
    return table


def comparison_report(table: pd.DataFrame) -> pd.DataFrame:
    """Per-source image statistics - the visual comparison measure.

    If the new sources were merely a re-scrape of iNaturalist, their dimensions,
    aspect ratios and duplicate rates would match it. This table is what shows
    they do not.
    """
    kept = table[table["duplicate_of"].isna()]
    stats = kept.groupby("source").agg(
        images=("photo_id", "size"),
        species=("label_species", "nunique"),
        mean_width=("width", "mean"),
        mean_height=("height", "mean"),
        median_bytes=("bytes", "median"),
    )
    stats["aspect_ratio"] = (kept.groupby("source")
                             .apply(lambda g: (g["width"] / g["height"]).mean(),
                                    include_groups=False))
    stats["dup_rate_%"] = (table.groupby("source")["duplicate_of"]
                           .apply(lambda s: 100 * s.notna().mean()))
    return stats.round(2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--table", type=Path, default=config.FINAL_CSV)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    table = pd.read_csv(args.table)
    inspected = inspect_all(table)
    merged = table.merge(inspected, on="photo_id", how="left", validate="1:1")
    resolved = resolve_duplicates(merged)
    print(comparison_report(resolved).to_string())


if __name__ == "__main__":
    main()

"""Step 3 - materialise the image files referenced by a photo table.

Turns a table of photo URLs into real files on disk plus a manifest that indexes
them. Resumable and idempotent: a re-run fetches only what is missing, so an
interrupted download is continued rather than restarted.

    python -m insects.download --table Data/ButterfliesOnly/butterflies_all.csv
"""
from __future__ import annotations

import argparse
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from . import config

log = logging.getLogger(__name__)

MANIFEST_COLS = ["photo_id", "label_species", "local_path",
                 "bytes", "sha256", "status", "error"]


def target_path(label_species: str, photo_id: int, root: Path) -> Path:
    """images/<Label_species>/<photo_id>.jpg - the ImageFolder layout."""
    return root / str(label_species).replace(" ", "_") / f"{photo_id}.jpg"


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    """Hash a file without loading it into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_one(url: str, dest: Path, session: requests.Session) -> dict:
    """Download one image atomically. Never raises; reports failure instead."""
    if dest.exists() and dest.stat().st_size > 0:
        return {"bytes": dest.stat().st_size, "sha256": sha256_of(dest),
                "status": "cached", "error": None}

    tmp = dest.with_suffix(".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with session.get(url, timeout=config.DOWNLOAD_TIMEOUT, stream=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as fh:
                for block in r.iter_content(chunk_size=1 << 16):
                    fh.write(block)

        tmp.replace(dest)          # atomic: only now does the final path exist
        return {"bytes": dest.stat().st_size, "sha256": sha256_of(dest),
                "status": "ok", "error": None}

    except Exception as exc:
        tmp.unlink(missing_ok=True)
        return {"bytes": None, "sha256": None,
                "status": "failed", "error": f"{type(exc).__name__}: {exc}"}


def download(df: pd.DataFrame, root: Path | None = None,
             manifest_path: Path | None = None,
             url_col: str = f"photo_url_{config.PHOTO_SIZE}",
             workers: int = config.DOWNLOAD_WORKERS) -> pd.DataFrame:
    """Fetch every image in `df`, resuming from an existing manifest."""
    root = root or config.IMAGES
    manifest_path = manifest_path or config.MANIFEST_CSV

    done: set[int] = set()
    previous = pd.DataFrame(columns=MANIFEST_COLS)
    if manifest_path.exists():
        previous = pd.read_csv(manifest_path)
        ok = previous[previous["status"].isin(["ok", "cached"])]
        done = set(ok["photo_id"])
        log.info("manifest has %s completed images", f"{len(done):,}")

    todo = df[~df["photo_id"].isin(done)]
    log.info("%s to fetch, %s already done", f"{len(todo):,}", f"{len(done):,}")
    if todo.empty:
        return previous

    session = requests.Session()
    session.headers.update({"User-Agent": config.USER_AGENT})
    # urllib3 pools 10 connections per host by default; with more workers than
    # that the extra ones are opened, used once and discarded. Sizing the pool
    # to the worker count keeps connections alive across requests instead.
    adapter = requests.adapters.HTTPAdapter(pool_connections=workers,
                                            pool_maxsize=workers)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    records = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_one, row[url_col],
                        target_path(row["label_species"], row["photo_id"], root),
                        session): row
            for _, row in todo.iterrows()
        }
        for i, future in enumerate(as_completed(futures), start=1):
            row = futures[future]
            result = future.result()
            records.append({
                "photo_id": row["photo_id"],
                "label_species": row["label_species"],
                "local_path": str(
                    target_path(row["label_species"], row["photo_id"], root)
                    .relative_to(config.ROOT)),
                **result,
            })
            if i % 500 == 0:
                log.info("%s/%s fetched", f"{i:,}", f"{len(futures):,}")

    manifest = pd.concat([previous, pd.DataFrame(records)], ignore_index=True)
    manifest = manifest.drop_duplicates(subset="photo_id", keep="last")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest[MANIFEST_COLS].to_csv(manifest_path, index=False)

    counts = manifest["status"].value_counts().to_dict()
    log.info("manifest: %s rows %s -> %s", f"{len(manifest):,}", counts, manifest_path)
    return manifest[MANIFEST_COLS]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--table", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--workers", type=int, default=config.DOWNLOAD_WORKERS)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    download(pd.read_csv(args.table), args.root, workers=args.workers)


if __name__ == "__main__":
    main()

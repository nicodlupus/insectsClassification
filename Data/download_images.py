# author: Nikolas Antoniou

# Downloads every photo in the dataset from iNaturalist's open-data bucket on Amazon S3 and writes
# a manifest that maps each CSV row to its image file.
#
# naming scheme (one file per CSV row, recoverable from the name alone):
#   <out>/<label_species>/<observation_id>_<photo_id>.<ext>
#   e.g. images/Vanessa_cardui/387625264_709822987.jpg
#
# usage (from the repo root):
#   python Data/download_images.py                          # medium (~500px) into ./images
#   python Data/download_images.py --size large --out /mnt/storage/images
#
# Re-running skips files that already exist, so an interrupted download resumes.
# Images are never committed: ./images is in .gitignore.

import argparse
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).resolve().parent
SIZES = ["small", "medium", "large", "original"]
MANIFEST_COLS = ["file_path", "observation_id", "photo_id", "label_species", "taxon_name",
                 "photo_url", "license_code", "attribution", "status"]

session = requests.Session()
session.headers["User-Agent"] = "insectsClassification (academic project)"


def photo_id(url):
    # https://inaturalist-open-data.s3.amazonaws.com/photos/709822987/square.jpg -> 709822987
    m = re.search(r"/photos/(\d+)/", url)
    return int(m.group(1)) if m else None


def sized_url(url, size):
    return re.sub(r"/(square|small|medium|large|original)\.", f"/{size}.", url)


def image_path(row, root):
    label = re.sub(r"[^A-Za-z0-9]+", "_", row["label_species"]).strip("_")
    ext = Path(row["photo_url"]).suffix.lower() or ".jpg"
    return Path(root) / label / f"{row['observation_id']}_{row['photo_id']}{ext}"


def fetch(url, dest, tries=4, sleep=0.2):
    if dest.exists() and dest.stat().st_size > 0:
        return "exists"
    for attempt in range(tries):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(dest.suffix + ".part")
                tmp.write_bytes(r.content)
                tmp.replace(dest)         # atomic: no half-written images after a crash
                time.sleep(sleep)
                return "ok"
            if r.status_code in (403, 404):
                return f"http_{r.status_code}"
        except requests.RequestException:
            pass
        time.sleep(2 ** (attempt + 1))  # backoff on errors / throttling
    return "failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DATA / "insects_clean.csv")
    ap.add_argument("--out", default=DATA.parent / "images")
    ap.add_argument("--size", default="medium", choices=SIZES)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, help="only the first N rows (for testing)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    if args.limit:
        df = df.head(args.limit)
    df["photo_id"] = df["photo_url"].map(photo_id)
    df["photo_url"] = df["photo_url"].map(lambda u: sized_url(u, args.size))
    df["file_path"] = df.apply(lambda r: image_path(r, args.out), axis=1)

    status = {}
    start = time.perf_counter()
    with ThreadPoolExecutor(args.workers) as pool:
        jobs = {pool.submit(fetch, r.photo_url, r.file_path): i for i, r in df.iterrows()}
        for n, job in enumerate(as_completed(jobs), 1):
            status[jobs[job]] = job.result()
            elapsed = time.perf_counter() - start
            eta = (len(df) - n) / (n / elapsed)
            print(f"\r{n:,}/{len(df):,} | {elapsed/60:4.1f} min elapsed | ~{eta/60:4.1f} min left",
                  end="", flush=True)
    print()

    df["status"] = pd.Series(status)
    df["file_path"] = df["file_path"].map(lambda p: Path(p).relative_to(args.out).as_posix())
    manifest = Path(args.out) / "manifest.csv"
    df[MANIFEST_COLS].to_csv(manifest, index=False)
    print(df["status"].value_counts().to_string())
    print(f"manifest -> {manifest}")


if __name__ == "__main__":
    main()

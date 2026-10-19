# author: Nikolas Antoniou

# Maps photos that were already downloaded (e.g. the Google Drive folder) back to their CSV rows,
# without downloading anything. A file is matched when its name contains the iNaturalist photo id
# (the number in the photo URL: .../photos/<photo_id>/medium.jpg).
#
# usage (from the repo root):
#   python Data/build_manifest.py /path/to/drive/photos
#
# outputs, written next to the photos:
#   manifest.csv        one row per CSV entry, with file_path (empty if no file was found)
#   unmatched_files.csv image files whose name contains no known photo id

import argparse
import re
from pathlib import Path

import pandas as pd

from download_images import DATA, MANIFEST_COLS, photo_id

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--csv", default=DATA / "insects_clean.csv")
    args = ap.parse_args()

    root = Path(args.folder)
    df = pd.read_csv(args.csv)
    df["photo_id"] = df["photo_url"].map(photo_id)
    known = set(df["photo_id"])

    found, unmatched = {}, []
    files = [p for p in root.rglob("*") if p.suffix.lower() in IMAGE_EXT]
    for p in files:
        # any run of digits in the path that is a known photo id
        ids = [int(n) for n in re.findall(r"\d+", p.relative_to(root).as_posix())
               if int(n) in known]
        if ids:
            found.setdefault(ids[-1], p.relative_to(root).as_posix())
        else:
            unmatched.append(p.relative_to(root).as_posix())

    df["file_path"] = df["photo_id"].map(found)
    df["status"] = df["file_path"].notna().map({True: "matched", False: "missing"})
    df[MANIFEST_COLS].to_csv(root / "manifest.csv", index=False)
    pd.Series(unmatched, name="file_path").to_csv(root / "unmatched_files.csv", index=False)

    print(f"image files found     : {len(files):,}")
    print(f"CSV rows matched      : {df['file_path'].notna().sum():,} of {len(df):,}")
    print(f"files with no match   : {len(unmatched):,}  (see unmatched_files.csv)")
    if len(unmatched) == len(files) and files:
        print("no file name contains a photo id -> re-download with download_images.py instead")


if __name__ == "__main__":
    main()

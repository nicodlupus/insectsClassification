"""Step 6d - mirror ./images to Google Drive and turn it into link columns.

The deliverable is a table anyone can train from without first re-running the
harvest, which means the images have to live somewhere durable and shareable.
Drive is that somewhere, and `rclone` is how the bytes get there: it is
content-addressed and idempotent, so an interrupted upload is resumed by
re-running the same command, exactly like ``download.py``.

Authentication is yours, not this module's. Run once, interactively:

    rclone config      # n -> name: insects -> storage: drive -> scope 1 -> browser
    rclone config reconnect insects:      # if the browser step did not finish
    rclone mkdir insects:insects/images

Then:

    python -m insects.drive --upload
    python -m insects.drive --link --table Data/ButterfliesOnly/final_butterfly.csv
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
from pathlib import Path

import pandas as pd

from . import config

log = logging.getLogger(__name__)

# The "uc?export=download" form is the only Drive URL that returns image bytes
# to a plain HTTP client. It is for spot-checks, not for training - see the
# warning in `add_links`.
FILE_URL = "https://drive.google.com/uc?export=download&id={file_id}"


def _rclone(*args: str, capture: bool = False) -> str:
    """Run rclone, surfacing a missing remote as a readable error."""
    cmd = ["rclone", *args]
    log.info("$ %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"rclone failed ({result.returncode}). If the remote is missing, "
            f"run `rclone config` and create one named '{config.DRIVE_REMOTE}'."
        )
    return result.stdout if capture else ""


def remote_path() -> str:
    return f"{config.DRIVE_REMOTE}:{config.DRIVE_FOLDER}"


def upload(root: Path | None = None) -> None:
    """Copy the local image tree to Drive, sending only what is missing."""
    root = root or config.IMAGES
    _rclone("copy", str(root), remote_path(),
            f"--transfers={config.RCLONE_TRANSFERS}",
            f"--checkers={config.RCLONE_CHECKERS}",
            f"--drive-pacer-min-sleep={config.RCLONE_PACER_SLEEP}",
            f"--drive-pacer-burst={config.RCLONE_PACER_BURST}",
            # Every file here is well under the 8 MB cutoff, so each one is a
            # single simple upload. A large chunk size would only reserve a
            # buffer per transfer that no file is big enough to use.
            "--drive-upload-cutoff=64M",
            # One recursive listing of the destination instead of a request per
            # directory - it is what makes a resumed run cheap.
            "--fast-list",
            "--stats=30s", "--stats-one-line")


def list_remote() -> pd.DataFrame:
    """One row per file in Drive: relative path -> Drive file id.

    `lsjson -R` is a single API walk of the whole folder. Asking Drive for the
    id of each file individually would be 23,000 requests and would exhaust the
    per-minute quota long before it finished.
    """
    raw = _rclone("lsjson", "-R", "--files-only", remote_path(), capture=True)
    entries = json.loads(raw)
    return pd.DataFrame([
        {"drive_rel_path": e["Path"], "drive_file_id": e["ID"],
         "drive_bytes": e.get("Size")}
        for e in entries
    ])


def add_links(table: pd.DataFrame, remote: pd.DataFrame | None = None) -> pd.DataFrame:
    """Join Drive ids onto the table by the path each image occupies.

    Three columns rather than one, because they serve different consumers:

    * `drive_path`  - what a training job reads, after `drive.mount()` in Colab.
      **Use this one.** Reading thousands of `drive_url`s over HTTP trips
      Drive's abuse threshold, after which it returns an HTML interstitial
      instead of a JPEG; a loader would take that as a corrupt image and the
      failure would be silent and mid-epoch.
    * `drive_url`   - a browser-openable link, for spot-checking single rows and
      for anyone without Drive access.
    * `drive_file_id` - the stable identity, for rebuilding either of the above.
    """
    remote = list_remote() if remote is None else remote

    table = table.copy()
    table["drive_rel_path"] = (table["label_species"].str.replace(" ", "_")
                               + "/" + table["photo_id"].astype(str) + ".jpg")

    merged = table.merge(remote, on="drive_rel_path", how="left", validate="1:1")
    merged["drive_path"] = f"{config.DRIVE_FOLDER}/" + merged["drive_rel_path"]
    merged["drive_url"] = merged["drive_file_id"].apply(
        lambda fid: FILE_URL.format(file_id=fid) if pd.notna(fid) else pd.NA)

    missing = merged["drive_file_id"].isna().sum()
    if missing:
        log.warning("%s rows have no file in Drive; re-run --upload",
                    f"{missing:,}")
    return merged.drop(columns="drive_rel_path")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--link", action="store_true", help="write link columns back")
    ap.add_argument("--table", type=Path, default=config.FINAL_CSV)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.upload:
        upload()
    if args.link:
        table = add_links(pd.read_csv(args.table))
        table.to_csv(args.table, index=False)
        log.info("wrote Drive links for %s rows -> %s",
                 f"{len(table):,}", args.table)


if __name__ == "__main__":
    main()

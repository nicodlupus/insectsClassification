"""Step 2b - apply the audit's cleaning rules to produce the modelling table.

Every rule traces back to a numbered finding in
``Analysis/DataAudit&Analysis.ipynb`` so the cleaning step stays auditable
rather than folklore. Each rule is a small function; ``clean()`` chains them and
records how many rows each one removed.

    python -m insects.clean
"""
from __future__ import annotations

import argparse
import logging
import re

import pandas as pd

from . import config

log = logging.getLogger(__name__)


# --- individual transformations ---------------------------------------------

def parse_photographer(value) -> str | None:
    """Pull the photographer's name out of the formatted copyright line (S9)."""
    if not isinstance(value, str):
        return None
    s = re.sub(r"^\(c\)\s*", "", value)
    s = re.split(
        r",\s*(?:some rights reserved|all rights reserved|no rights reserved)", s
    )[0]
    s = re.sub(r"\s*\(CC[^)]*\)\s*$", "", s)
    return s.strip() or None


def to_district(value) -> str:
    """Map free-text place_guess onto one of the six Cypriot districts (S10)."""
    if not isinstance(value, str):
        return "unknown"
    t = value.lower()
    for district, keys in config.DISTRICTS.items():
        if any(k in t for k in keys):
            return district
    return "other"


def to_size(url: str, size: str = config.PHOTO_SIZE) -> str:
    """Rewrite an iNaturalist photo URL to a different size variant (S11).

    The stored URLs are all the 75x75 ``square`` thumbnail, which is far below
    the input resolution of any modern classifier. The path is size-templated,
    so this is a free fix - but it must happen before anything is downloaded.
    """
    return re.sub(r"/(%s)\." % "|".join(config.PHOTO_SIZES), f"/{size}.", url)


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Species label, photographer, district, full-size URL."""
    df = df.copy()
    df["taxon_name"] = df["taxon_name"].str.strip()

    # Labels mix ranks (S6): a trinomial is a subspecies, so truncate to the
    # binomial; a single word is a genus, which has no species label at all.
    words = df["taxon_name"].str.split()
    df["label_species"] = words.str[:2].str.join(" ")
    df.loc[words.str.len() == 1, "label_species"] = pd.NA

    df["photographer"] = df["attribution"].map(parse_photographer)
    df["district"] = df["location"].map(to_district)
    df[f"photo_url_{config.PHOTO_SIZE}"] = df["photo_url"].map(to_size)
    return df


# --- the rule chain ----------------------------------------------------------

def clean(df: pd.DataFrame, min_photos: int = config.MIN_PHOTOS_PER_CLASS
          ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply every cleaning rule. Returns (clean_frame, per-step log)."""
    df = add_derived(df)
    log_rows = []

    def step(name: str, frame: pd.DataFrame) -> pd.DataFrame:
        log_rows.append({
            "step": name,
            "rows_after": len(frame),
            "rows_removed": len(df) - len(frame) if not log_rows
            else log_rows[-1]["rows_after"] - len(frame),
        })
        return frame

    out = df
    # S4/S8 - one photo is all-rights-reserved despite the open-licence filter;
    # redistributing it would be a licence violation, not a quality nuisance.
    out = step("drop non-open licence (S4/S8)", out[out["license_code"].notna()])
    # S5 - the same image file under two observation ids: a hard leak.
    out = step("drop repeated image files (S5)",
               out.drop_duplicates(subset="photo_url", keep="first"))
    # S6 - genus-only rows have no species-level target.
    out = step("drop genus-only labels (S6)", out[out["label_species"].notna()])
    # S7 - classes below the support floor cannot be split train/test at all.
    keep = out["label_species"].value_counts()
    keep = keep[keep >= min_photos].index
    out = step(f"drop classes with < {min_photos} photos (S7)",
               out[out["label_species"].isin(keep)])

    # NOTE (professor, 2026-08): multiple photos per observation are KEPT on
    # purpose - several views of the same individual are good augmentation. The
    # leakage risk they create is handled at split time, not by deletion:
    # splits must be grouped by observation_id (S5).

    return out.reset_index(drop=True), pd.DataFrame(log_rows).set_index("step")


OUT_COLS = [
    "observation_id", "photo_id", "label_species", "taxon_name", "taxon_rank",
    "order", "superfamily", "family", "subfamily", "tribe", "genus",
    "is_butterfly", "is_moth",
    "photo_url", f"photo_url_{config.PHOTO_SIZE}", "photo_width", "photo_height",
    "license_code", "attribution", "photographer",
    "observed_on", "latitude", "longitude", "location", "district",
]


def run(in_path=None, out_path=None, min_photos: int = config.MIN_PHOTOS_PER_CLASS
        ) -> pd.DataFrame:
    in_path = in_path or config.ENRICHED_CSV
    out_path = out_path or config.CLEAN_CSV

    df = pd.read_csv(in_path, dtype={"ancestor_ids": str})
    out, steps = clean(df, min_photos)
    log.info("cleaning steps:\n%s", steps.to_string())

    cols = [c for c in OUT_COLS if c in out.columns]
    out[cols].to_csv(out_path, index=False)
    log.info("wrote %s rows, %s classes, %s observations -> %s",
             f"{len(out):,}", f"{out['label_species'].nunique():,}",
             f"{out['observation_id'].nunique():,}", out_path)
    return out[cols]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="in_path", default=None)
    ap.add_argument("--out", dest="out_path", default=None)
    ap.add_argument("--min-photos", type=int, default=config.MIN_PHOTOS_PER_CLASS)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args.in_path, args.out_path, args.min_photos)


if __name__ == "__main__":
    main()

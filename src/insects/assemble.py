"""Step 6e - assemble the three sources into `final_butterfly.csv`.

One row per image, one table, four sources. The columns that existed in
`butterfly_images.csv` keep their meaning so that anything written against that
table still works; the new columns record what the old table had no need to say:
where the image came from, whether it may be redistributed, whether it survived
deduplication, and where it lives in Drive.

    python -m insects.assemble
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from . import config, dedup

log = logging.getLogger(__name__)

FINAL_COLS = [
    # identity
    "photo_id", "label_species", "family", "genus", "taxon_name", "subspecies",
    # grouping - the split key (audit S5)
    "observation_group", "observation_id",
    # provenance
    "source", "photo_url_medium", "license_code", "commercial_ok",
    "redistributable", "attribution", "photographer", "location", "district",
    # storage
    "class_dir", "file_name", "local_path",
    "drive_file_id", "drive_path", "drive_url",
    # image properties / QA
    "width", "height", "bytes", "phash", "duplicate_of", "ok", "reason",
]


def _species_taxonomy() -> pd.DataFrame:
    """family/genus per species, taken from the already-audited iNat table.

    The new sources report taxonomy in their own vocabularies. Rather than trust
    those, the ranks are looked up from the table whose taxonomy was resolved
    through iNaturalist ancestor ids in step 2 - so all 33 classes keep one
    consistent family and genus.
    """
    existing = pd.read_csv(config.BUTTERFLY_IMAGES_CSV)
    return (existing.groupby("label_species")[["family", "genus"]]
            .agg(lambda s: s.dropna().iloc[0] if s.notna().any() else pd.NA)
            .reset_index())


def _inat_rows() -> pd.DataFrame:
    """The existing dataset, renamed into the final schema."""
    df = pd.read_csv(config.BUTTERFLY_IMAGES_CSV)
    df["observation_group"] = df["observation_id"].astype("Int64").astype(str)
    return df


def _gbif_rows() -> pd.DataFrame:
    df = pd.read_csv(config.GBIF_MEDIA_CSV)
    # One GBIF occurrence can carry several photos of the same individual, which
    # is the same leakage risk observation_id guards against on the iNat side.
    df["observation_group"] = "gbif:" + df["occurrence_key"].astype(str)
    df["observation_id"] = pd.NA
    df["location"] = df["country"]
    df["district"] = pd.NA
    df["subspecies"] = pd.NA
    return df


def _web_rows() -> pd.DataFrame:
    df = pd.read_csv(config.WEB_MEDIA_CSV)
    # No occurrence to group by: each scraped image is its own group, which is
    # the conservative assumption for a leakage-free split.
    df["observation_group"] = df["photo_id"]
    df["observation_id"] = pd.NA
    df["taxon_name"] = df["label_species"]
    df["location"] = pd.NA
    df["district"] = pd.NA
    df["subspecies"] = pd.NA
    return df


def assemble(out_path=None, inspect: bool = True,
             normalise: bool = True) -> pd.DataFrame:
    """Concatenate, validate, deduplicate and write the final table."""
    out_path = out_path or config.FINAL_CSV

    table = pd.concat([_inat_rows(), _gbif_rows(), _web_rows()],
                      ignore_index=True)
    log.info("%s rows before QA: %s", f"{len(table):,}",
             table["source"].value_counts().to_dict())

    # photo_id is the file name on disk and in Drive, so a collision means two
    # different images sharing one file. Checked here, where the offending rows
    # can still be named, rather than surfacing later as a merge error.
    collisions = table.loc[table["photo_id"].duplicated(keep=False), "photo_id"]
    if not collisions.empty:
        raise ValueError(
            f"{collisions.nunique()} photo_id collisions, e.g. "
            f"{sorted(collisions.unique())[:5]}")

    # Taxonomy from one authority, not three.
    taxonomy = _species_taxonomy()
    table = (table.drop(columns=["family", "genus"], errors="ignore")
             .merge(taxonomy, on="label_species", how="left"))

    # Licence consequences, derived rather than stored per source, so the rule
    # lives in one place (config) and cannot drift between sources.
    table["commercial_ok"] = table["license_code"].isin(config.COMMERCIAL_SAFE)
    table["redistributable"] = ~table["license_code"].fillna("unknown").isin(
        config.TRAINING_ONLY_LICENCES)

    table["class_dir"] = table["label_species"].str.replace(" ", "_")
    table["file_name"] = table["photo_id"].astype(str) + ".jpg"

    if inspect:
        inspected = dedup.inspect_all(table)
        table = (table.drop(columns=["width", "height", "bytes", "local_path"],
                            errors="ignore")
                 .merge(inspected, on="photo_id", how="left", validate="1:1"))
        table = dedup.resolve_duplicates(table)
        if normalise:
            # After the inspection, so the recorded dimensions are the ones the
            # image was published at rather than the ones we stored it at.
            table = dedup.normalise(table)
    else:
        for col in ["width", "height", "bytes", "phash", "duplicate_of",
                    "ok", "reason", "local_path"]:
            table[col] = table.get(col, pd.NA)

    # Drive columns are filled in by `insects.drive --link` after the upload;
    # they are created here so the schema is the same before and after.
    for col in ["drive_file_id", "drive_path", "drive_url"]:
        if col not in table:
            table[col] = pd.NA

    table = table.reindex(columns=FINAL_COLS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path, index=False)

    # .eq(True) rather than .fillna(False): `ok` is object dtype while the Drive
    # columns are still empty, and fillna would silently downcast it.
    usable = table[table["ok"].eq(True) & table["duplicate_of"].isna()]
    log.info("wrote %s rows (%s usable) -> %s",
             f"{len(table):,}", f"{len(usable):,}", out_path)
    return table


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-inspect", action="store_true",
                    help="skip the on-disk image pass (schema only)")
    ap.add_argument("--no-normalise", action="store_true",
                    help="leave oversized images at their published resolution")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    assemble(inspect=not args.no_inspect, normalise=not args.no_normalise)


if __name__ == "__main__":
    main()

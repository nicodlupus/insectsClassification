"""Step 6f - regenerate the datasheet for `final_butterfly.csv`.

Follows Gebru et al., "Datasheets for Datasets" (CACM, 2021), like the datasheet
for the iNaturalist-only table. It is generated from the table rather than
written by hand, so the numbers in it cannot drift away from the data.

The existing `butterfly_images_datasheet.md` is left alone: it documents
`butterfly_images.csv`, which still exists and is still the clean, fully
licensed subset. This one documents the augmented table, whose provenance and
licensing are genuinely different and should not be described by the same page.

    python -m insects.datasheet
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

import pandas as pd

from . import config

log = logging.getLogger(__name__)

OUT_PATH = config.REPORTS / "final_butterfly_datasheet.md"

SOURCE_NOTES = {
    "cyprus_inat": "iNaturalist, Cyprus, through the audited pipeline",
    "global_inat": "iNaturalist, worldwide, harvested by taxon id",
    "gbif": "GBIF occurrence media, iNaturalist records excluded",
    "web_scrape": "image search, last resort for the Cyprus endemics",
}


def _table(frame: pd.DataFrame, headers: list[str], aligns: list[str]) -> str:
    """Render a markdown table without pulling in a dependency for it."""
    head = "| " + " | ".join(headers) + " |"
    rule = "|" + "|".join(aligns) + "|"
    rows = ["| " + " | ".join(str(v) for v in row) + " |"
            for row in frame.itertuples(index=False)]
    return "\n".join([head, rule, *rows])


def build(table: pd.DataFrame) -> str:
    """Render the datasheet markdown from the final table."""
    usable = table[table["ok"].eq(True) & table["duplicate_of"].isna()]
    counts = usable["label_species"].value_counts()

    provenance = (usable["source"].value_counts()
                  .rename_axis("source").reset_index(name="images"))
    provenance["share_%"] = (100 * provenance["images"] / len(usable)).round(1)
    provenance["what it is"] = provenance["source"].map(SOURCE_NOTES)

    licences = (usable["license_code"].fillna("unknown").value_counts()
                .rename_axis("licence").reset_index(name="images"))
    licences["share_%"] = (100 * licences["images"] / len(usable)).round(1)
    licences["redistributable"] = ~licences["licence"].isin(
        config.TRAINING_ONLY_LICENCES)
    licences["licence"] = "`" + licences["licence"] + "`"

    scraped_species = table.loc[table["source"] == "web_scrape",
                                "label_species"].nunique()
    dupes = int(table["duplicate_of"].notna().sum())
    failed = int(table["ok"].eq(False).sum())
    redistributable = int(usable["redistributable"].sum())
    commercial = int(usable["commercial_ok"].sum())

    return f"""# Datasheet — `final_butterfly`

*Generated {date.today()} by `insects.datasheet`. Do not edit by hand.*

## Motivation
Fine-grained image classification of the butterflies (superfamily Papilionoidea)
recorded in Cyprus. Built for an academic project supervised by
Dr. Demetris Trihinas. Not intended for commercial use.

This table supersedes `butterfly_images.csv` for **training only**. That table
was drawn entirely from iNaturalist, which meant a single photographic regime —
one platform, one community, one set of framing conventions — and left the
Cyprus endemics badly under-represented. This one adds two further sources to
widen both the visual variety and the thin classes.

## Composition
- **{len(usable):,}** usable images across **{usable['label_species'].nunique()}** species,
  from **{len(table):,}** harvested rows.
- Class balance: max **{counts.max():,}**, median **{int(counts.median()):,}**,
  min **{counts.min():,}** — a ratio of **{counts.max() / counts.min():.1f}:1**.
- Removed during QA: **{dupes:,}** near-duplicates (perceptual hash, Hamming
  distance ≤ {config.PHASH_DISTANCE}) and **{failed:,}** rows that were missing,
  undecodable or below the size floor.
- One row per image.

{_table(provenance[['source', 'what it is', 'images', 'share_%']],
        ['Source', 'What it is', 'Images', 'Share'],
        ['---', '---', '---:', '---:'])}

## Collection process
The iNaturalist rows are unchanged from the audited pipeline: observations from
`/v1/observations` at `quality_grade=research`, with class membership decided
**taxonomically** — by testing whether taxon **47224** (Papilionoidea) appears in
each record's `ancestor_ids`, never by matching species names. The
circumscription follows Heikkilä et al. (2012, doi:10.1098/rspb.2011.1430) and
Kawahara et al. (2023, doi:10.1038/s41559-023-02041-9), and therefore includes
skippers (Hesperiidae).

GBIF rows were harvested by GBIF `taxonKey`, resolved once per species through
`/species/match` and cached. The iNaturalist dataset republished by GBIF
(`{config.GBIF_INAT_DATASET_KEY}`) is excluded, as are media whose URL or
publisher identifies them as iNaturalist, so that no image is collected twice.

Scraped rows were collected by image search for the {scraped_species} species that
neither source could fill, and are flagged accordingly (see Limitations).

All images were capped at {config.MAX_IMAGE_SIDE}px on the long side. Beyond
saving storage, this removes resolution as a signal that would let a model
separate the *sources* rather than the species.

## Licensing
{_table(licences[['licence', 'images', 'share_%', 'redistributable']],
        ['Licence', 'Images', 'Share', 'Redistributable'],
        ['---', '---:', '---:', '---'])}

- **{redistributable:,} images ({100 * redistributable / len(usable):.1f}%) may be redistributed.**
  The remainder are NoDerivatives or unlicensed: usable as training input,
  **not** publishable as a dataset. Filter on `redistributable`.
- **{commercial:,} images ({100 * commercial / len(usable):.1f}%) permit commercial use.**
  Filter on `commercial_ok` before any non-academic reuse.
- Every row carries `license_code` and `attribution`, which must be preserved.

## Recommended use
- Target variable: `label_species`.
- **Split grouped by `observation_group`** — the iNaturalist observation id, the
  GBIF occurrence key, or the image itself for scraped rows. Multiple photos of
  one individual exist by design and must not straddle train/test (audit
  finding S5).
- Filter to `ok == True` and `duplicate_of.isna()` before training.
- Read images from `drive_path` after mounting Drive — not from `drive_url`,
  which is rate-limited and returns an HTML interstitial once the quota trips.
- Evaluate on `source == "cyprus_inat"` to measure performance on the actual task.

## Limitations
- **Unverified labels in the scraped subset.** iNaturalist and GBIF rows carry an
  identification made by a naturalist against a taxon key. Scraped rows carry
  whatever the surrounding web page claimed. They were spot-checked by eye in
  `Analysis/FinalDataset.ipynb`, which is a weaker standard; treat them as the
  noisiest part of the label distribution.
- **No licence on the scraped subset**, hence `redistributable = False`.
- **Residual imbalance.** The Cyprus endemics could not be topped up to target:
  outside iNaturalist there is very little openly licensed material of them.
- **Geographic domain shift.** Most images are still from outside Cyprus.
- **Source-correlated appearance.** GBIF leans on specimen and atlas photography,
  iNaturalist on handheld field photos. That variety is the point, but it also
  means `source` is itself predictive and must never be given to the model.
- Recency bias in the harvest and uneven subspecies coverage, as before.

*Structure follows Gebru et al., "Datasheets for Datasets" (Communications of the ACM, 2021).*
"""


def write(table: pd.DataFrame | None = None, out_path=None) -> str:
    out_path = out_path or OUT_PATH
    if table is None:
        table = pd.read_csv(config.FINAL_CSV)
    text = build(table)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    log.info("wrote datasheet -> %s", out_path)
    return text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    write()


if __name__ == "__main__":
    main()

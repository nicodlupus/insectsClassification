# Datasheet — `butterfly_images`

*Generated 2026-09-12 by `Analysis/DataEngineering.ipynb`. Do not edit by hand.*

## Motivation
Fine-grained image classification of the butterflies (superfamily Papilionoidea)
recorded in Cyprus. Built for an academic project supervised by
Dr. Demetris Trihinas. Not intended for commercial use.

## Composition
- **15,088** images across **33** species,
  **5** families, **9,434** observations.
- Class balance: max **500**, median **500**, min **116**
  — a ratio of **4.3:1**.
- Subspecies recorded for **125** images
  (14 distinct subspecies across
  14 species).
- Provenance: `global_inat` 12,188 / `cyprus_inat` 2,900.
- One row per image; files are sharded into 33 per-species zip archives.

## Collection process
Observations were retrieved from the iNaturalist API (`/v1/observations`),
restricted to `quality_grade=research` and to openly licensed photos.
Class membership was determined **taxonomically**, by testing whether iNaturalist
taxon **47224** (Papilionoidea) appears in each record's `ancestor_ids` — never by
matching species names. The circumscription follows Heikkilä et al. (2012,
doi:10.1098/rspb.2011.1430) and Kawahara et al. (2023, doi:10.1038/s41559-023-02041-9),
and therefore includes skippers (Hesperiidae).

Cyprus records came through the audited pipeline (`insects_clean.csv`). Additional
images were harvested worldwide **by `taxon_id`**, capped at 500 images per
species to limit class imbalance.

## Licensing
All images are openly licensed; every row carries `license_code` and `attribution`,
which must be preserved on redistribution.

| Licence | Images | Share |
|---|---:|---:|
| `cc-by-nc` | 12,840 | 85.1% |
| `cc-by` | 1,562 | 10.4% |
| `cc0` | 419 | 2.8% |
| `cc-by-nc-sa` | 165 | 1.1% |
| `cc-by-sa` | 102 | 0.7% |

**Only 2,083 images (13.8%) permit commercial use.**
Filter on `commercial_ok` before any non-academic reuse.

## Recommended use
- Target variable: `label_species` (33 classes).
- **Split grouped by `observation_id`** — multiple photos of one individual exist by
  design and must not straddle train/test (audit finding S5).
- Evaluate on `source == "cyprus_inat"` to measure performance on the actual task.

## Limitations
See section 4.4 of the generating notebook: geographic domain shift (81% non-Cyprus),
residual imbalance driven by Cyprus endemics, recency bias in the harvest,
NonCommercial licensing, uneven subspecies coverage, and the absence of
image-content validation.

*Structure follows Gebru et al., "Datasheets for Datasets" (Communications of the ACM, 2021).*

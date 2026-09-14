# Datasheet — `final_butterfly`

*Generated 2026-09-13 by `insects.datasheet`. Do not edit by hand.*

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
- **22,683** usable images across **33** species,
  from **23,221** harvested rows.
- Class balance: max **757**, median **739**,
  min **286** — a ratio of **2.6:1**.
- Removed during QA: **376** near-duplicates (perceptual hash, Hamming
  distance ≤ 4) and **163** rows that were missing,
  undecodable or below the size floor.
- One row per image.

| Source | What it is | Images | Share |
|---|---|---:|---:|
| global_inat | iNaturalist, worldwide, harvested by taxon id | 12084 | 53.3 |
| gbif | GBIF occurrence media, iNaturalist records excluded | 7109 | 31.3 |
| cyprus_inat | iNaturalist, Cyprus, through the audited pipeline | 2874 | 12.7 |
| web_scrape | image search, last resort for the Cyprus endemics | 616 | 2.7 |

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
(`50c9509d-22c7-4a22-a47d-8c48425ef4a7`) is excluded, as are media whose URL or
publisher identifies them as iNaturalist, so that no image is collected twice.

Scraped rows were collected by image search for the 8 species that
neither source could fill, and are flagged accordingly (see Limitations).

All images were capped at 800px on the long side. Beyond
saving storage, this removes resolution as a signal that would let a model
separate the *sources* rather than the species.

## Licensing
| Licence | Images | Share | Redistributable |
|---|---:|---:|---|
| `cc-by-nc` | 13151 | 58.0 | True |
| `cc-by-nc-nd` | 5863 | 25.8 | False |
| `cc-by` | 2216 | 9.8 | True |
| `unknown` | 616 | 2.7 | False |
| `cc0` | 427 | 1.9 | True |
| `cc-by-nc-sa` | 247 | 1.1 | True |
| `cc-by-sa` | 139 | 0.6 | True |
| `cc-by-nd` | 24 | 0.1 | False |

- **16,180 images (71.3%) may be redistributed.**
  The remainder are NoDerivatives or unlicensed: usable as training input,
  **not** publishable as a dataset. Filter on `redistributable`.
- **2,782 images (12.3%) permit commercial use.**
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

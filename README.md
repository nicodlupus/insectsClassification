# Insects: butterfly image classification dataset (Cyprus)

Dataset pipeline for fine-grained image classification of the butterflies
(Papilionoidea) recorded in Cyprus. Academic project supervised by
Dr. Demetris Trihinas.

## Where things live

| What | Where |
|---|---|
| Code, tables (CSV), notebooks, datasheets | this GitHub repository |
| **Images (~23,000 JPEGs)** | **Google Drive** (not in git, see below) |

### Images are on Google Drive

The photos are too large for git, so `images/` is git-ignored and hosted on
Google Drive instead.

**Drive folder: `<PASTE GOOGLE DRIVE LINK HERE>`**

The folder mirrors the local layout `images/<Genus_species>/<photo_id>.jpg`
(ImageFolder-compatible). `Data/ButterfliesOnly/final_butterfly.csv` is the
training table, and `Data/image_manifest.csv` lists every downloaded file with
its sha256. To work locally, download the Drive folder and place it at
`./images/`.

## Repository layout

- `Data/`: source and cleaned tables. `ButterfliesOnly/final_butterfly.csv` is
  the final training table (22,683 usable images, 33 species).
- `Analysis/`: audit, engineering and final-dataset notebooks.
- `Reports/`: datasheets describing how each table was built.
- `src/insects/`: the pipeline (iNaturalist, GBIF and web harvest, cleaning,
  dedup, Drive upload, datasheet generation).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Re-uploading images to Drive uses `rclone` (see `src/insects/drive.py`).

## Licence

See [LICENSE](LICENSE). Image licences vary per source; see the datasheets.

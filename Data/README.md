# Data pipeline

Run from the repo root, in this order:

| step | script | output |
|---|---|---|
| 1 | `retriever.py` | `insects.csv`: raw iNaturalist records, one row per photo |
| 2 | `../Analysis/DataAudit&Analysis.ipynb` | `insects_clean.csv`: species labels, at least 20 photos per class, `medium` URLs |
| 3 | `taxonomy.py --apply` | `taxonomy.csv` and new columns in `insects_clean.csv`: `taxon_id, rank, order, superfamily, family, subfamily, genus, is_butterfly` |
| 4 | `multiphoto.py` | `insects_multiphoto.csv`: observations with 2 or more photos of the same insect |
| 5a | `download_images.py --out <storage>` | images and `manifest.csv` |
| 5b | `build_manifest.py <folder>` | `manifest.csv` for photos already downloaded elsewhere (e.g. Google Drive) |

## Mapping a CSV row to its photo

Every photo is named after its own IDs, so the CSV row can be recovered from the file name alone:

```
<storage>/<label_species>/<observation_id>_<photo_id>.jpg
e.g. images/Vanessa_cardui/387625264_709822987.jpg
```

`photo_id` is the number in `photo_url` (`.../photos/<photo_id>/medium.jpg`). `manifest.csv` lists
each file path with its observation, label, licence and attribution. The attribution is required
by every licence except CC0.

## Notes

- **Subcategory.** `is_butterfly = 1` means the taxon is in superfamily *Papilionoidea*. That is the
  taxonomic definition of a butterfly; all other Lepidoptera are moths. The lineage comes from the
  iNaturalist taxa API, not from the Latin name, because butterfly names share no common term.
- **Hosting.** The photos already live on Amazon S3 in iNaturalist's open-data bucket
  (`inaturalist-open-data.s3.amazonaws.com`). The bucket needs no account. The downloader stays
  polite (4 workers, retries with backoff) and resumes after an interruption.
- **Git.** Images are never committed (`images/` is in `.gitignore`). Pass `--out` to point at the
  provided storage.
- **Splits.** Always group train/val/test by `observation_id`. Photos of the same observation show
  the same individual insect.

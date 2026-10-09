"""Project-wide constants and paths.

Everything that a downstream module might want to tweak lives here, so that no
magic number is buried inside a transformation.
"""
from pathlib import Path

# --- paths ------------------------------------------------------------------
# repo root = three levels up from this file (src/insects/config.py)
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "Data"
RAW = DATA / "raw"
IMAGES = ROOT / "images"          # gitignored; the professor supplies storage
REPORTS = ROOT / "Reports"

OBSERVATIONS_CSV = RAW / "observations.csv"      # step 1 output
TAXONOMY_CSV = RAW / "taxonomy.csv"              # step 2 taxon lookup table
ENRICHED_CSV = RAW / "observations_enriched.csv"  # step 2 output
CLEAN_CSV = DATA / "insects_clean.csv"           # step 2 deliverable
MANIFEST_CSV = DATA / "image_manifest.csv"       # step 3 deliverable
SPLIT_CSV = DATA / "splits.csv"                  # step 5 deliverable

# --- butterfly augmentation (step 6) ----------------------------------------
BUTTERFLIES = DATA / "ButterfliesOnly"
BUTTERFLY_IMAGES_CSV = BUTTERFLIES / "butterfly_images.csv"   # the iNat dataset
FINAL_CSV = BUTTERFLIES / "final_butterfly.csv"               # step 6 deliverable
GBIF_TAXA_CSV = RAW / "gbif_taxa.csv"            # label_species -> GBIF taxonKey
GBIF_MEDIA_CSV = RAW / "gbif_media.csv"          # GBIF harvest, one row per image
WEB_MEDIA_CSV = RAW / "web_media.csv"            # search-engine harvest

# --- iNaturalist API --------------------------------------------------------
API = "https://api.inaturalist.org/v1"
USER_AGENT = (
    "insectsClassification/0.1 (academic dataset build; "
    "https://github.com/nicodlupus/insectsClassification)"
)

PLACE_ID = 10289          # Cyprus
ICONIC_TAXA = ["Insecta"]
QUALITY_GRADE = "research"
# Only openly licensed photos; anything outside this set is a licence violation
# to redistribute (see audit S8).
PHOTO_LICENCES = ["cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa"]
COMMERCIAL_SAFE = {"cc0", "cc-by", "cc-by-sa"}

PER_PAGE = 200            # API maximum
TAXA_BATCH = 30           # /v1/taxa/{ids} accepts up to 30 comma-separated ids

# iNaturalist asks for <=100 requests/minute and recommends ~1/second.
REQUEST_DELAY = 1.0
MAX_RETRIES = 5
BACKOFF_BASE = 2.0        # seconds; doubled per retry

# --- taxonomy ---------------------------------------------------------------
# Butterflies sensu lato. Papilionoidea in current iNaturalist taxonomy includes
# skippers (Hesperiidae) and the Hedylidae, so this flag is broader than the
# colloquial "butterfly" but matches how the clade is now circumscribed.
BUTTERFLY_TAXON_ID = 47224        # superfamily Papilionoidea
MOTH_CONTRAST_TAXON_ID = 47157    # order Lepidoptera (butterflies + moths)

# Ranks lifted out of the ancestry chain into their own columns.
RANK_COLUMNS = ["order", "superfamily", "family", "subfamily", "tribe", "genus"]

# --- cleaning rules (audit S4-S7) -------------------------------------------
MIN_PHOTOS_PER_CLASS = 20
GROUP_KEY = "observation_id"      # mandatory split grouping key (audit S5)
LABEL_COLUMN = "label_species"

# --- images -----------------------------------------------------------------
PHOTO_SIZE = "medium"             # ~500px; "original" is 10-20x the bytes
PHOTO_SIZES = ("square", "small", "medium", "large", "original")
DOWNLOAD_WORKERS = 8
DOWNLOAD_TIMEOUT = 30

# --- GBIF API (step 6, second image source) ---------------------------------
GBIF_API = "https://api.gbif.org/v1"
GBIF_PAGE = 300           # occurrence/search max limit
# GBIF republishes iNaturalist, so the one dataset we must NOT harvest is the
# one we already have. Negation (`datasetKey=!<uuid>`) is rejected by the API
# with HTTP 400, so this is filtered client-side instead.
GBIF_INAT_DATASET_KEY = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"

# GBIF states licences as URLs; the project speaks the short iNaturalist codes.
# One vocabulary downstream means the licence table in the datasheet stays a
# single table rather than two that must be reconciled by the reader.
GBIF_LICENCE_CODES = {
    "publicdomain/zero/1.0": "cc0",
    "licenses/by/4.0": "cc-by",
    "licenses/by-sa/4.0": "cc-by-sa",
    "licenses/by-nc/4.0": "cc-by-nc",
    "licenses/by-nc-sa/4.0": "cc-by-nc-sa",
    "licenses/by-nd/4.0": "cc-by-nd",
    "licenses/by-nc-nd/4.0": "cc-by-nc-nd",
}
# NoDerivatives licences dominate the largest non-iNat dataset (Observation.org).
# They are usable as training input but may not be redistributed as a dataset,
# so they are admitted into a second tier rather than dropped or waved through.
TRAINING_ONLY_LICENCES = {"cc-by-nd", "cc-by-nc-nd", "unknown"}

# --- augmentation targets ---------------------------------------------------
TOPUP_PER_SPECIES = 250   # extra images wanted per class, on top of the iNat set
WEB_CANDIDATE_CAP = 400   # search results inspected per species before giving up
MIN_IMAGE_BYTES = 15_000  # below this it is a thumbnail or an error page
MIN_IMAGE_PX = 200        # shortest side; smaller cannot be resized up usefully
PHASH_DISTANCE = 4        # Hamming distance at which two images are "the same"
# GBIF returns the photographer's original (up to ~4000px) where iNaturalist
# returns a ~500px "medium". Capping the long side keeps the Drive upload
# manageable and stops resolution from being a give-away signal for the source.
MAX_IMAGE_SIDE = 800
JPEG_QUALITY = 88

# --- Google Drive hosting ---------------------------------------------------
DRIVE_REMOTE = "insects"         # rclone remote name; created by `rclone config`
DRIVE_FOLDER = "insects/images"  # path inside Drive that mirrors ./images
# 23,000 files of ~100 KB are a latency problem, not a bandwidth one: almost all
# of the time goes on Drive's per-file round trip. rclone's default pacer waits
# 100ms between API calls, capping the whole transfer at ~10 files/second no
# matter how many workers there are, so the pacer is loosened and the worker
# count raised to match. Drive starts returning 403 rateLimitExceeded past
# roughly this point, and rclone backs off on its own when it does.
RCLONE_TRANSFERS = 32
RCLONE_CHECKERS = 32
RCLONE_PACER_SLEEP = "10ms"
RCLONE_PACER_BURST = 200

# --- location normalisation (audit S10) -------------------------------------
DISTRICTS = {
    "nicosia": ["nicosia", "lefkosia", "lefkosa", "λευκωσία", "nikosia", "nicosie"],
    "limassol": ["limassol", "lemesos", "λεμεσός", "limasol"],
    "paphos": ["paphos", "pafos", "πάφος", "baf"],
    "larnaca": ["larnaca", "larnaka", "λάρνακα"],
    "famagusta": ["famagusta", "ammochostos", "gazimagusa", "αμμόχωστος",
                  "protaras", "ayia napa", "agia napa"],
    "kyrenia": ["kyrenia", "girne", "keryneia", "κερύνεια"],
}

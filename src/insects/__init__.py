"""Reusable pipeline for the Cyprus insect image-classification dataset.

The modules are ordered as the pipeline runs:

    retrieve   pull observations + photos from the iNaturalist API
    taxonomy   resolve ancestor_ids into named rank columns + butterfly flags
    clean      apply the data-audit rules -> the modelling table
    download   fetch the images themselves (resumable, manifest-driven)
    split      materialise a leakage-free grouped train/val/test split

Step 6 augments the butterfly set with images from outside iNaturalist and
publishes the result to Google Drive:

    gbif       harvest additional images from GBIF (iNaturalist excluded)
    webscrape  last-resort top-up for the species GBIF cannot fill
    dedup      validate files, normalise size, remove cross-source duplicates
    assemble   concatenate the sources -> Data/ButterfliesOnly/final_butterfly.csv
    drive      mirror ./images to Google Drive and add the link columns
    datasheet  regenerate the datasheet from the final table

Each is importable and runnable (``python -m insects.clean``). Notebooks should
import from here rather than redefining any of it.
"""
from . import config  # noqa: F401

__version__ = "0.1.0"

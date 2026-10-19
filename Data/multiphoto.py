# author: Nikolas Antoniou

# Mini dataset of observations that have several photos of the same individual insect.
# Several views of one specimen are useful for image classification (multi-view training,
# test-time augmentation, consistency checks), as long as an observation never spans two splits.
#
# usage (from the repo root):
#   python Data/multiphoto.py      -> Data/insects_multiphoto.csv

from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent
MIN_PHOTOS = 2

df = pd.read_csv(DATA / "insects_clean.csv")
df["n_photos"] = df.groupby("observation_id")["photo_url"].transform("size")
multi = df[df["n_photos"] >= MIN_PHOTOS].copy()
multi["photo_index"] = multi.groupby("observation_id").cumcount()

multi.to_csv(DATA / "insects_multiphoto.csv", index=False)
print(f"observations with >= {MIN_PHOTOS} photos : {multi['observation_id'].nunique():,}")
print(f"photos                         : {len(multi):,}")
print(f"species covered                : {multi['label_species'].nunique():,} "
      f"of {df['label_species'].nunique():,}")
print(multi.drop_duplicates("observation_id")["n_photos"].describe().round(1).to_string())

# author: Nikolas Antoniou

# Adds taxonomic subcategories (order, superfamily, family, is_butterfly) to every taxon in the
# dataset, using the iNaturalist taxa API instead of guessing from the Latin name.
# A butterfly is any Lepidoptera in the superfamily Papilionoidea; every other Lepidoptera is a moth.
#
# usage (from the repo root):
#   python Data/taxonomy.py                # resolve all names, write Data/taxonomy.csv
#   python Data/taxonomy.py --apply        # also merge the columns into Data/insects_clean.csv
#
# Results are cached in Data/taxonomy.csv, so an interrupted run resumes where it stopped.

import argparse
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://api.inaturalist.org/v1/taxa"
INSECTA_ID = 47158       # restrict name lookups to insects, so plant/bird homonyms never match
PAPILIONOIDEA = "Papilionoidea"
RANKS = ["order", "superfamily", "family", "subfamily", "genus"]
SLEEP = 1.0              # iNaturalist asks for <= 60 requests / minute

DATA = Path(__file__).resolve().parent
RAW = DATA / "insects.csv"
CLEAN = DATA / "insects_clean.csv"
OUT = DATA / "taxonomy.csv"
COLUMNS = ["taxon_name", "taxon_id", "rank"] + RANKS + ["is_butterfly"]

session = requests.Session()
session.headers["User-Agent"] = "insectsClassification (academic project)"


def get(url, params=None, tries=5):
    # retries with exponential backoff on network errors, 429 and 5xx
    for attempt in range(tries):
        try:
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code not in (429, 500, 502, 503, 504):
                r.raise_for_status()
        except requests.RequestException as e:
            if attempt == tries - 1:
                raise
            print(f"\n  retry ({e.__class__.__name__})", end="")
        time.sleep(SLEEP * 2 ** (attempt + 1))
    raise RuntimeError(f"giving up on {url}")


def resolve(name):
    # name -> taxon id, preferring an exact, active match inside Insecta
    data = get(API, {"q": name, "taxon_id": INSECTA_ID, "per_page": 10})
    exact = [t for t in data["results"] if t["name"].lower() == name.lower()]
    exact.sort(key=lambda t: not t.get("is_active", True))
    return exact[0] if exact else None


def lineage(taxon_ids):
    # batch lookup (30 ids per request) of each taxon's ancestors
    out = {}
    for i in range(0, len(taxon_ids), 30):
        chunk = taxon_ids[i:i + 30]
        data = get(f"{API}/{','.join(map(str, chunk))}")
        for t in data["results"]:
            ranks = {a["rank"]: a["name"] for a in t.get("ancestors", [])}
            ranks[t["rank"]] = t["name"]
            out[t["id"]] = ranks
        time.sleep(SLEEP)
    return out


def build():
    names = sorted(pd.read_csv(RAW)["taxon_name"].dropna().str.strip().unique())
    done = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=COLUMNS)
    todo = [n for n in names if n not in set(done["taxon_name"])]
    print(f"{len(names):,} taxon names | {len(done):,} cached | {len(todo):,} to resolve")

    resolved = []
    for i, name in enumerate(todo, 1):
        t = resolve(name)
        resolved.append({"taxon_name": name,
                         "taxon_id": t["id"] if t else None,
                         "rank": t["rank"] if t else None})
        print(f"\r{i:,}/{len(todo):,} resolved", end="", flush=True)
        time.sleep(SLEEP)
    print()

    new = pd.DataFrame(resolved, columns=["taxon_name", "taxon_id", "rank"])
    ids = [int(x) for x in new["taxon_id"].dropna()]
    lines = lineage(ids)
    for r in RANKS:
        new[r] = new["taxon_id"].map(lambda i: lines.get(int(i), {}).get(r) if pd.notna(i) else None)
    new["is_butterfly"] = (new["superfamily"] == PAPILIONOIDEA).astype(int)

    tax = pd.concat([done, new], ignore_index=True)[COLUMNS]
    tax["taxon_id"] = tax["taxon_id"].astype("Int64")
    tax.to_csv(OUT, index=False)

    missing = tax["taxon_id"].isna().sum()
    print(f"wrote {len(tax):,} rows -> {OUT.name} ({missing} names not found on iNaturalist)")
    print(tax["order"].value_counts().head(10).to_string())
    print(f"butterfly taxa: {tax['is_butterfly'].sum()}")
    return tax


def apply(tax):
    # merge the subcategory columns into the cleaned dataset (re-runnable: old columns replaced)
    clean = pd.read_csv(CLEAN)
    clean = clean.drop(columns=[c for c in COLUMNS[1:] if c in clean.columns])
    clean = clean.merge(tax, on="taxon_name", how="left")
    clean["is_butterfly"] = clean["is_butterfly"].fillna(0).astype(int)
    clean.to_csv(CLEAN, index=False)
    print(f"merged into {CLEAN.name}: {clean['is_butterfly'].sum():,} butterfly photos "
          f"of {len(clean):,}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="merge results into insects_clean.csv")
    args = ap.parse_args()
    tax = build()
    if args.apply:
        apply(tax)

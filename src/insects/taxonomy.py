"""Step 2a - resolve the ancestry chain into named rank columns.

Answers the professor's question ("can we know if the insect is a butterfly?")
without regex on Latin names and without an LLM: every observation already
carries ``taxon.ancestor_ids``, and butterflies are everything descended from
superfamily Papilionoidea (47224).

Building the full hierarchy costs the same as the binary flag and gives
``order`` / ``family`` / ``genus`` for free, which is what makes a hierarchical
(family -> genus -> species) classifier possible later.

    python -m insects.taxonomy
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from . import config
from .inat import INatClient

log = logging.getLogger(__name__)


def parse_ancestors(value) -> list[int]:
    """'48460|1|47120' -> [48460, 1, 47120]."""
    if not isinstance(value, str) or not value:
        return []
    return [int(v) for v in value.split("|") if v]


def required_taxon_ids(df: pd.DataFrame) -> set[int]:
    """Every taxon id mentioned by any row, whether as a leaf or an ancestor."""
    ids: set[int] = set()
    for chain in df["ancestor_ids"].dropna():
        ids.update(parse_ancestors(chain))
    ids.update(int(t) for t in df["taxon_id"].dropna().unique())
    return ids


def build_taxon_table(df: pd.DataFrame, cached: pd.DataFrame | None = None,
                      client: INatClient | None = None) -> pd.DataFrame:
    """Fetch id -> (name, rank) for every taxon this frame needs.

    Only the ids missing from ``cached`` are fetched, so a partial cache (e.g.
    left over from a smoke run) is topped up rather than trusted wholesale.
    """
    needed = required_taxon_ids(df)
    known = set(cached.index) if cached is not None else set()
    missing = sorted(needed - known)

    if not missing:
        log.info("taxon cache covers all %s required taxa", f"{len(needed):,}")
        return cached

    log.info("resolving %s taxa (%s already cached)",
             f"{len(missing):,}", f"{len(needed & known):,}")
    client = client or INatClient()
    records = client.fetch_taxa(missing)

    fetched = pd.DataFrame([
        {"taxon_id": r["id"], "taxon_rank": r.get("rank"), "name": r.get("name")}
        for r in records
    ]).set_index("taxon_id")

    if cached is None or cached.empty:
        return fetched
    return pd.concat([cached, fetched])


def enrich(df: pd.DataFrame, taxa: pd.DataFrame) -> pd.DataFrame:
    """Add one column per rank in RANK_COLUMNS, plus the butterfly flags."""
    rank_of = taxa["taxon_rank"].to_dict()
    name_of = taxa["name"].to_dict()

    def ranks_for(chain: str) -> dict:
        out = {}
        for tid in parse_ancestors(chain):
            rank = rank_of.get(tid)
            if rank in config.RANK_COLUMNS:
                out[rank] = name_of.get(tid)
        return out

    df = df.copy()
    expanded = pd.DataFrame(
        [ranks_for(c) for c in df["ancestor_ids"]], index=df.index
    ).reindex(columns=config.RANK_COLUMNS)
    df[config.RANK_COLUMNS] = expanded

    ancestor_sets = df["ancestor_ids"].map(lambda c: set(parse_ancestors(c)))
    df["is_butterfly"] = ancestor_sets.map(
        lambda s: int(config.BUTTERFLY_TAXON_ID in s)
    )
    # Lepidoptera minus Papilionoidea = moths, the useful contrast class.
    df["is_moth"] = ancestor_sets.map(
        lambda s: int(config.MOTH_CONTRAST_TAXON_ID in s
                      and config.BUTTERFLY_TAXON_ID not in s)
    )
    return df


def run(obs_path=None, out_path=None, taxa_path=None) -> pd.DataFrame:
    obs_path = obs_path or config.OBSERVATIONS_CSV
    out_path = out_path or config.ENRICHED_CSV
    taxa_path = taxa_path or config.TAXONOMY_CSV

    df = pd.read_csv(obs_path, dtype={"ancestor_ids": str})

    # The taxon table is cached because it is the slow part and changes far
    # less often than the observation pull. The cache is topped up, not trusted:
    # a stale or partial cache would silently leave rows unenriched.
    cached = None
    if taxa_path.exists():
        cached = pd.read_csv(taxa_path).set_index("taxon_id")
        log.info("loaded %s cached taxa from %s", f"{len(cached):,}", taxa_path)

    taxa = build_taxon_table(df, cached)
    if cached is None or len(taxa) != len(cached):
        taxa_path.parent.mkdir(parents=True, exist_ok=True)
        taxa.to_csv(taxa_path)

    out = enrich(df, taxa)
    out.to_csv(out_path, index=False)

    n_bf = int(out["is_butterfly"].sum())
    log.info("wrote %s rows -> %s", f"{len(out):,}", out_path)
    log.info("butterflies: %s rows (%.1f%%), %s species",
             f"{n_bf:,}", 100 * n_bf / len(out),
             out.loc[out["is_butterfly"] == 1, "taxon_name"].nunique())
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--obs", type=lambda p: __import__("pathlib").Path(p), default=None)
    ap.add_argument("--out", type=lambda p: __import__("pathlib").Path(p), default=None)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args.obs, args.out)


if __name__ == "__main__":
    main()

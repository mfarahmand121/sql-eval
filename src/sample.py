"""Sampling strategies.

Phase 0 needs one thing: a deterministic, stratified 200-example subset of BIRD
dev to generate against. Phase 4 adds the interesting sampling (by predicted
failure likelihood, query complexity, judge uncertainty) alongside it.
"""

from __future__ import annotations

import random
from collections import defaultdict

from schema import load_dev

BASELINE_SEED = 20260718
BASELINE_N = 200


def select_baseline(n: int = BASELINE_N, seed: int = BASELINE_SEED) -> list[dict]:
    """Stratified sample across (db_id, difficulty), proportional to dev-set shares.

    Stratifying matters here: `challenging` is only 9.5% of dev, and a plain
    random 200 could easily hand us a dozen of them. The failure modes we care
    about most in phase 1 cluster in the harder strata, so we hold their share
    fixed rather than letting it drift.

    Deterministic given (n, seed) so the trace set is reproducible.
    """
    dev = load_dev()
    strata: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for rec in dev:
        strata[(rec["db_id"], rec["difficulty"])].append(rec)

    rng = random.Random(seed)
    # Largest-remainder apportionment, so the quotas sum to exactly n.
    quotas: dict[tuple[str, str], int] = {}
    remainders: list[tuple[float, tuple[str, str]]] = []
    for key, recs in strata.items():
        exact = len(recs) * n / len(dev)
        quotas[key] = min(int(exact), len(recs))
        remainders.append((exact - int(exact), key))

    remainders.sort(key=lambda pair: (-pair[0], pair[1]))
    shortfall = n - sum(quotas.values())
    for _, key in remainders:
        if shortfall <= 0:
            break
        if quotas[key] < len(strata[key]):
            quotas[key] += 1
            shortfall -= 1

    picked: list[dict] = []
    for key in sorted(strata):
        picked.extend(rng.sample(strata[key], quotas[key]))
    picked.sort(key=lambda rec: rec["question_id"])
    return picked


if __name__ == "__main__":
    from collections import Counter

    sample = select_baseline()
    print(f"{len(sample)} examples")
    print(Counter(r["difficulty"] for r in sample))
    print(Counter(r["db_id"] for r in sample))

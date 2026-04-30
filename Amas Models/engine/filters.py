"""Filter primitives + combo enumeration for the Amas Models engine.

Per the design spec, Category G (Statistical hygiene): filter combos use AND
semantics, not OR. A row passes a combo iff every named filter's
`passes_<key>` flag is True.

Each model's bespoke filters (e.g. shallow sweep) are computed in the model's
own file and attached to trade rows as `passes_<key>: bool`. This module owns
the orchestration: enumerating 2^N combos and applying them.
"""
from __future__ import annotations

from itertools import combinations


def enumerate_combos(keys: list[str]) -> list[frozenset[str]]:
    """Return all 2^N subsets of the given filter keys, including the empty set."""
    out: list[frozenset[str]] = []
    for r in range(len(keys) + 1):
        for c in combinations(keys, r):
            out.append(frozenset(c))
    return out


def apply_combo(rows: list[dict], combo: frozenset[str]) -> list[dict]:
    """Return only the rows where every filter in `combo` passes (AND semantics).

    A row missing a `passes_<key>` flag is treated as failing that filter
    (conservative default — never include a row whose filter status is unknown).
    """
    if not combo:
        return list(rows)
    out: list[dict] = []
    for r in rows:
        if all(r.get(f"passes_{k}", False) for k in combo):
            out.append(r)
    return out

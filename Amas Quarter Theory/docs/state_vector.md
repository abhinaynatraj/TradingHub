# State Vector — Schema v1

This document is the single source of truth for the state-key string format.
Python engine (`engine/state_vector.py`) and Pine indicator
(`pine/quarter_theory.pine`) MUST produce byte-identical strings for the
same logical state, and the same `canonical_hash()` of those strings.

Schema bumps require:
1. Update `SCHEMA_VERSION` in `engine/constants.py` and Pine.
2. Re-run `engine/build.py`.
3. Re-paste `_generated_tables.pine`.
4. Re-run parity test (`tests/test_state_vector.py::test_pine_parity` after Phase 9).

## Triad key format

```
v1|sym=<sym>|tf=triad|block=<block>|c1cls=<c1cls>|c2q=<c2q>|c2vh=<c2vh>|c2vl=<c2vl>|c2sw_c1h=<Y|N>|c2sw_c1l=<Y|N>|c2_inside=<Y|N>|midhr=<midhr>|mid3h=<mid3h>|box_react=<box_react>
```

## Hour key format

```
v1|sym=<sym>|tf=hour|block=<block>|hour_idx=<hour_idx>|q=<q>|q1cls=<...>|q2cls=<...>|q3cls=<...>|q4cls=<...>|sweep_set=<sorted comma-joined | "none">|midhr=<...>|box_react=<...>
```

## Allowed values

See `engine/state_vector.py` constants `_VALID_*` for the canonical allowed-value sets.

## Canonical hash

`canonical_hash(key)` = base36 of the low 64 bits of SHA-256(key as utf-8). The Pine side replicates with byte-level arithmetic (Phase 9). Both sides agree to ≤13 chars in `[0-9a-z]`.

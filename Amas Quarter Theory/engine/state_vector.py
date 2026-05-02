"""State-vector schema v1.

The state-key string format is the contract between this Python engine and
the Pine indicator. Both sides MUST produce byte-identical strings for the
same logical state, and MUST compute the same canonical_hash() of those
strings. Parity is tested in Phase 9.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple

from engine import constants as C


SCHEMA_VERSION = C.SCHEMA_VERSION


# ── Allowed value sets ────────────────────────────────────────────────────────

_VALID_SYMS = ("NQ", "ES")
_VALID_C1CLS = ("line-up", "line-down", "doji")
_VALID_C2Q = ("Q1", "Q2", "Q3", "Q4", "closed")
_VALID_VS = ("above", "inside", "below", "na")
_VALID_MIDLINE = ("support", "reject", "untouched")
_VALID_BOX_REACT = ("none", "05up_rejected", "05dn_rejected", "10up_rejected", "10dn_rejected", "multi")
_VALID_QCLS = ("in-stat-high", "in-stat-low", "out-stat-high", "out-stat-low",
               "swept-q1-high", "swept-q1-low", "swept-q2-high", "swept-q2-low",
               "swept-q3-high", "swept-q3-low", "inside")
_VALID_HOUR_IDX = (1, 2, 3)


def _yn(b: bool) -> str:
    return "Y" if b else "N"


def _validate(field: str, val: object, allowed: tuple) -> None:
    if val not in allowed:
        raise ValueError(f"invalid {field}: {val!r} not in {allowed}")


# ── Triad inputs / key ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class TriadStateInputs:
    sym: Literal["NQ", "ES"]
    block: str
    c1cls: Literal["line-up", "line-down", "doji"]
    c2q: Literal["Q1", "Q2", "Q3", "Q4", "closed"]
    c2vh: Literal["above", "inside", "below", "na"]
    c2vl: Literal["above", "inside", "below", "na"]
    c2sw_c1h: bool
    c2sw_c1l: bool
    c2_inside: bool
    midhr: Literal["support", "reject", "untouched"]
    mid3h: Literal["support", "reject", "untouched"]
    box_react: str

    def __post_init__(self) -> None:
        _validate("sym", self.sym, _VALID_SYMS)
        _validate("block", self.block, C.BLOCK_IDS)
        _validate("c1cls", self.c1cls, _VALID_C1CLS)
        _validate("c2q", self.c2q, _VALID_C2Q)
        _validate("c2vh", self.c2vh, _VALID_VS)
        _validate("c2vl", self.c2vl, _VALID_VS)
        _validate("midhr", self.midhr, _VALID_MIDLINE)
        _validate("mid3h", self.mid3h, _VALID_MIDLINE)
        _validate("box_react", self.box_react, _VALID_BOX_REACT)


def build_triad_key(s: TriadStateInputs) -> str:
    return (
        f"{SCHEMA_VERSION}|sym={s.sym}|tf=triad|block={s.block}|c1cls={s.c1cls}|c2q={s.c2q}|"
        f"c2vh={s.c2vh}|c2vl={s.c2vl}|c2sw_c1h={_yn(s.c2sw_c1h)}|c2sw_c1l={_yn(s.c2sw_c1l)}|"
        f"c2_inside={_yn(s.c2_inside)}|midhr={s.midhr}|mid3h={s.mid3h}|box_react={s.box_react}"
    )


# ── Hour inputs / key ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HourStateInputs:
    sym: Literal["NQ", "ES"]
    block: str
    hour_idx: Literal[1, 2, 3]
    q: Literal["Q1", "Q2", "Q3", "Q4", "closed"]
    q1cls: str
    q2cls: str
    q3cls: str
    q4cls: str
    sweep_set: Tuple[str, ...]
    midhr: Literal["support", "reject", "untouched"]
    box_react: str

    def __post_init__(self) -> None:
        _validate("sym", self.sym, _VALID_SYMS)
        _validate("block", self.block, C.BLOCK_IDS)
        _validate("hour_idx", self.hour_idx, _VALID_HOUR_IDX)
        _validate("q", self.q, _VALID_C2Q)
        for fn in ("q1cls", "q2cls", "q3cls", "q4cls"):
            _validate(fn, getattr(self, fn), _VALID_QCLS)
        _validate("midhr", self.midhr, _VALID_MIDLINE)
        _validate("box_react", self.box_react, _VALID_BOX_REACT)


def build_hour_key(s: HourStateInputs) -> str:
    sweep_str = ",".join(sorted(s.sweep_set)) if s.sweep_set else "none"
    return (
        f"{SCHEMA_VERSION}|sym={s.sym}|tf=hour|block={s.block}|hour_idx={s.hour_idx}|q={s.q}|"
        f"q1cls={s.q1cls}|q2cls={s.q2cls}|q3cls={s.q3cls}|q4cls={s.q4cls}|"
        f"sweep_set={sweep_str}|midhr={s.midhr}|box_react={s.box_react}"
    )


# ── Compact hash (Pine map keys) ─────────────────────────────────────────────

_HASH_BASE  = 131
# 32-bit truncation: keeps the running hash within float53 mantissa
# precision so Pine's float-based emulation stays bit-exact. Collision
# rate over ~3K keys per map: ~3000^2 / 2^32 ≈ 1 in 2 million probability
# of *any* collision. We have ~13K distinct hashed keys total in the v1
# build, so total collision probability is <0.02% — acceptable.
_HASH_MOD   = 1 << 32


def canonical_hash(key: str) -> str:
    """Return a base36-encoded 32-bit polynomial rolling hash of the key.

    Both Python and Pine MUST produce the same digest. We use a polynomial
    rolling hash (h = h*131 + c, 32-bit truncated) because it's ~10 lines
    of Pine to replicate, vs. ~300 for SHA-256, and 32-bit modulus fits
    inside float64 mantissa precision cleanly.

    All state-key strings are pure ASCII by construction, so `ord(c)`
    gives byte codepoints in [0, 127]. Pine emulates with a 95-char
    printable-ASCII lookup table indexed by str.substring().
    """
    h = 0
    for c in key:
        h = (h * _HASH_BASE + ord(c)) % _HASH_MOD
    return _to_base36(h)


def _to_base36(n: int) -> str:
    if n == 0:
        return "0"
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = []
    while n > 0:
        out.append(chars[n % 36])
        n //= 36
    return "".join(reversed(out))

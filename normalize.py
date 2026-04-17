from __future__ import annotations

import json
import re
from pathlib import Path

_RULES_PATH = Path(__file__).parent / "normalize_rules.json"

def _load_rules():
    with open(_RULES_PATH, encoding="utf-8") as f:
        return json.load(f)

def normalize_djs(names: list[str]) -> list[tuple[str, str, str]]:
    """
    Normalize a list of raw DJ name strings.

    Returns a list of (raw_name, normalized_name, rule_applied) tuples.
    rule_applied is one of: b2b_split, slash_split, nere_a_merge, manual_remap,
    expand, skip, none.

    Callers should filter out entries where normalized_name is None (skipped).
    """
    rules = _load_rules()
    remaps = {k.upper(): v for k, v in rules.get("remaps", {}).items()}
    skip_set = {s.upper() for s in rules.get("skip", [])}
    expand = {k.upper(): v for k, v in rules.get("expand", {}).items()}

    # Strip Unicode zero-width and invisible characters from all names
    names = [re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", n) for n in names]

    # Step 1: check for NE/RE/A fragment merge across the whole list
    lower_set = {n.strip().lower() for n in names}
    if {"ne", "re", "a"}.issubset(lower_set):
        return [("ne, re, a (fragments)", "NE/RE/A", "nere_a_merge")]

    # Step 2: split each name on B2B and "/"
    exploded = []  # (raw, candidate, rule)
    for name in names:
        raw = name.strip()
        upper = raw.upper()

        if re.search(r"\bb2b\b", raw, re.IGNORECASE):
            parts = re.split(r"\bb2b\b", raw, flags=re.IGNORECASE)
            for p in parts:
                p = p.strip()
                if p:
                    exploded.append((raw, p.upper(), "b2b_split"))
        elif " / " in raw:
            parts = [p.strip() for p in raw.split(" / ") if p.strip()]
            for p in parts:
                exploded.append((raw, p.upper(), "slash_split"))
        else:
            exploded.append((raw, upper, "none"))

    # Step 3: apply manual rules (expand, skip, remap)
    results = []
    for raw, candidate, rule in exploded:
        # Drop concatenation artifacts: BasementXXXX or StudioXXXX fused strings
        if re.match(r"^(BASEMENT|STUDIO)\S", candidate):
            results.append((raw, None, "skip"))
            continue

        # Strip trailing performance qualifiers
        candidate = re.sub(r"\s+LIVE$", "", candidate).strip()
        candidate = re.sub(r"\s*\(DJ SET\)$", "", candidate).strip()
        candidate = re.sub(r"\s+PRESENTS\s+.*$", "", candidate).strip()
        if candidate in skip_set:
            results.append((raw, None, "skip"))
            continue
        if candidate in expand:
            for expanded in expand[candidate]:
                results.append((raw, expanded.upper(), "expand"))
            continue
        if candidate in remaps:
            results.append((raw, remaps[candidate].upper(), "manual_remap"))
            continue
        results.append((raw, candidate, rule))

    return results


def normalize_title(title: str, source: str = "web") -> tuple[str, str]:
    """
    Normalize an event title string.
    source: "web" or "ra"

    Returns (normalized_title, rule_applied).
    normalized_title is:
      - None  → caller should drop the event entirely (postponed/cancelled)
      - ""    → suppressed (month-named or bare BASEMENT); still included in review
      - str   → canonical title

    rule_applied is one of: suppressed, postponed_cancelled, title_remaps_both,
    title_remaps_web, title_remaps_ra, none.
    """
    rules = _load_rules()
    shared_remaps = rules.get("title_remaps_both", {})
    source_key = "title_remaps_web" if source == "web" else "title_remaps_ra"
    source_remaps = rules.get(source_key, {})
    suppress_patterns = rules.get("suppress_title_patterns", [])

    upper = title.upper()

    # Drop test/dummy events entirely (fake DJ names pollute counts)
    for pat in suppress_patterns:
        if re.search(pat, upper, re.IGNORECASE):
            return None, "suppressed_test"

    # RA-source: drop postponed/cancelled entirely
    if source == "ra" and re.search(r"\b(POSTPONED|CANCELLED)\b", upper):
        return None, "postponed_cancelled"

    # Web-source: suppress month-named titles, BasementXXXX concatenations,
    # and bare "BASEMENT" (not anniversary)
    if source == "web":
        if re.search(r"\b(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\b", upper):
            return "", "suppressed"
        # Catch month-name typos (DECEMEBER, SSEPTEMBER, etc.) — double letters or transpositions
        if re.search(r"\b(DECEMEBER|SSEPTEMBER|JANURAY|FEBRURAY|OCOTBER)\b", upper):
            return "", "suppressed"
        # Scraper artifact: "Basement" fused directly to DJ names with no space
        if re.match(r"^BASEMENT\S", upper):
            return "", "suppressed"
        if re.search(r"\bBASEMENT\b", upper) and not re.search(r"\bANNIVERSARY\b", upper):
            return "", "suppressed"

    # Apply shared remaps first (covers both sources)
    for pattern, canonical in shared_remaps.items():
        if re.search(pattern, upper, re.IGNORECASE):
            return canonical, "title_remaps_both"

    # Apply source-specific remaps
    for pattern, canonical in source_remaps.items():
        if re.search(re.escape(pattern), upper, re.IGNORECASE):
            return canonical, source_key

    # Suppress lineup-style titles (DJ / DJ / DJ) that weren't matched as a party
    if " / " in title:
        return "", "suppressed"

    return title, "none"

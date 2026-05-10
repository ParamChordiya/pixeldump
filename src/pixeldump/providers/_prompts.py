"""Internal shared prompt builders for vision providers.

Both ClaudeProvider and OllamaProvider import these so prompt text isn't
duplicated. Not part of the public API.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from pixeldump.core.taxonomy import ALL_CATEGORIES
from pixeldump.core.types import LibraryStats, NamingMode

CLASSIFY_SYSTEM_PROMPT: str = (
    "You are a vision classifier for a personal photo organizer. "
    "Look at the supplied photos (they all come from the same time-clustered event) "
    "and classify the event with a single primary category from this list:\n"
    f"{', '.join(ALL_CATEGORIES)}\n\n"
    "Respond with ONLY a JSON object on a single line, no prose, no markdown. "
    "Schema:\n"
    "{\n"
    '  "category": "<one of the categories above>",\n'
    '  "subcategory": "<short snake_case sub-key or null>",\n'
    '  "confidence": <float 0.0-1.0>,\n'
    '  "description": "<one short sentence>",\n'
    '  "notable": ["<thing 1>", "<thing 2>"]\n'
    "}\n"
    "If you cannot tell, use category \"uncategorized\". Keep description under 120 chars."
)


_MODE_INSTRUCTIONS: dict[NamingMode, str] = {
    NamingMode.CORPORATE: (
        "Style: clean, professional, descriptive. Snake_case, lowercase. "
        'Examples: "japan_trip_march", "sarah_wedding", "team_offsite_q2".'
    ),
    NamingMode.CHAOTIC: (
        "Style: Gen-Z slang, pop culture references, descriptive but fun. "
        "Snake_case, lowercase. "
        'Examples: "ate_good_in_tokyo", "main_character_energy_brunch", '
        '"besties_did_iceland".'
    ),
    NamingMode.UNHINGED: (
        "Style: maximum brainrot, absurd, vaguely related to the photos. "
        "Snake_case, lowercase, still under 40 chars. "
        'Examples: "proof_i_went_outside_once", "the_yassification_of_brunch", '
        '"skibidi_holiday_arc".'
    ),
}


def build_name_prompt(category: str, mode: NamingMode) -> str:
    """Return the user prompt for `name_event`. Constrains output to a bare folder name."""
    style = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS[NamingMode.CORPORATE])
    return (
        "Generate a single folder name for this group of photos.\n"
        f"Category: {category}\n"
        f"{style}\n"
        "Hard rules:\n"
        "- snake_case, lowercase ASCII letters/digits/underscores only\n"
        "- 40 characters or less\n"
        "- no quotes, no punctuation, no file extension, no date prefix\n"
        "- output ONLY the folder name, nothing else"
    )


def build_roast_prompt(stats: LibraryStats) -> str:
    """Return a prompt asking the model to roast the user's library."""
    payload = json.dumps(asdict(stats), default=str)
    return (
        "You are a sassy, Gen-Z photo-app voice. Roast the user's photo library "
        "based on these stats. 3 to 6 short lines, mention specific numbers "
        "(cats, screenshots, food, selfies, duplicates, total photos, time elapsed). "
        "Be playful, not mean. No hashtags. No emoji walls (one or two is fine). "
        "Keep total output under 600 characters.\n\n"
        f"Stats JSON: {payload}"
    )

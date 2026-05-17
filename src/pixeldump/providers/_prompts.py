"""Internal shared prompt builders for vision providers.

Both ClaudeProvider and OllamaProvider import these so prompt text isn't
duplicated. Not part of the public API.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from pixeldump.core.taxonomy import ALL_CATEGORIES
from pixeldump.core.types import LibraryStats, NamingMode, PhotoInput

CLASSIFY_SYSTEM_PROMPT: str = (
    "You are a vision classifier for a personal photo organizer. "
    "All photos supplied come from the same time-clustered event. "
    "You will receive METADATA and thumbnail images. "
    "Always read the metadata block first — it carries hard evidence that visuals alone cannot provide.\n\n"

    "METADATA SIGNALS — apply these to ALL classification decisions, not just screenshots:\n\n"

    "  GPS coordinates:\n"
    "    • present → this is a camera photo (never a screenshot or scanned doc)\n"
    "    • use the coordinates with your geography knowledge to identify the country/city/region\n"
    "    • coordinates far from home / in another country → strongly favour travel or international\n"
    "    • known landmark / national-park coordinates → nature, hiking, or travel\n"
    "    • city-centre coordinates + evening time → social, concert, date_night, or city_break\n\n"

    "  Time of day (from date field):\n"
    "    • 05:00–08:00 (early morning) → running, gym, hiking, nature sunrise\n"
    "    • 08:00–12:00 (morning)       → brunch, travel sightseeing, work_event\n"
    "    • 12:00–17:00 (afternoon)     → travel, outdoor social, everyday\n"
    "    • 17:00–21:00 (evening)       → dinner_party, happy_hour, date_night, concert\n"
    "    • 21:00–03:00 (night)         → concert, club_night, party, festival\n\n"

    "  Cluster time span (from earliest to latest date):\n"
    "    • multi-day (2+ days)  → travel, camping, ski_trip, festival, wedding\n"
    "    • single day / hours   → local event, everyday, social, work_event\n\n"

    "  Camera model:\n"
    "    • set (any value)               → real camera photo; NEVER classify as screenshot\n"
    "    • Sony / Canon / Nikon / Fuji   → likely creative, professional, or travel\n"
    "    • GoPro / DJI                   → likely action sport, travel, or adventure\n"
    "    • iPhone / Samsung / Pixel      → everyday, social, travel — check other signals\n"
    "    • none                          → possible screenshot/document; use visual cues\n\n"

    "  GPS = none AND camera = none → could be a screenshot or scanned document; inspect visuals carefully\n\n"

    "Classify the event into one PRIMARY CATEGORY and the most specific SUBCATEGORY.\n\n"

    "PRIMARY CATEGORIES (pick exactly one):\n"
    f"{', '.join(ALL_CATEGORIES)}\n\n"

    "SUBCATEGORY GUIDE — always use the most specific match available:\n\n"

    # ── Documents ──────────────────────────────────────────────────────────────
    "DOCUMENTS — both on-screen captures AND physical documents photographed on a surface.\n"
    "Key signals: status bar / battery icon, window chrome, typed form fields, "
    "letterhead, barcodes, official seals, or a camera pointing at paper.\n\n"

    "  Screenshots (the image IS a screen capture):\n"
    "    screenshot_app          single app UI: banking, maps, settings, streaming, games\n"
    "    screenshot_web          browser visible with URL bar or recognisable webpage\n"
    "    screenshot_conversation chat thread — SMS, iMessage, WhatsApp, Telegram, DMs\n"
    "    screenshot_social       social feed, post, story, or reel: Instagram, TikTok, Twitter/X, Reddit\n"
    "    screenshot_meme         meme, viral image, or humorous captioned screenshot\n"
    "    screenshot_map          map, turn-by-turn directions, or dropped-pin screenshot\n"
    "    screenshot              generic screen capture not matching any type above\n\n"

    "  Financial:\n"
    "    receipt                 itemised purchase list with merchant name, subtotal, tax, and total\n"
    "    bill                    periodic service bill — electricity, gas, water, phone, internet, rent\n"
    "    invoice                 B2B or freelance invoice with line items and payment terms\n"
    "    bank_statement          account statement listing transactions and running balance\n"
    "    credit_card_statement   credit card bill showing individual charges and minimum payment due\n"
    "    paycheck                pay stub or direct-deposit earnings statement\n"
    "    tax_doc                 W-2, 1099, tax return, or IRS/revenue-agency correspondence\n\n"

    "  Identity:\n"
    "    id_card                 national or state government-issued photo ID\n"
    "    passport                passport photo page or biographical data page\n"
    "    drivers_license         driver's licence or learner's permit\n"
    "    insurance_card          health, dental, vision, or auto insurance card\n"
    "    visa                    travel visa sticker or entry/exit stamp\n\n"

    "  Travel Documents:\n"
    "    boarding_pass           flight, train, or bus boarding pass with gate, seat, and barcode\n"
    "    hotel_confirmation      hotel booking confirmation, check-in voucher, or room receipt\n"
    "    event_ticket            concert, sports, museum, or theme-park ticket\n"
    "    itinerary               multi-day printed or digital travel itinerary\n\n"

    "  Medical:\n"
    "    prescription            pharmacy label, Rx slip, or prescription printout\n"
    "    medical_doc             doctor's note, discharge summary, referral letter, EOB, or insurance claim\n"
    "    lab_result              blood-work panel, diagnostic test result, or pathology report\n"
    "    vaccination_record      vaccine card or official immunisation history printout\n\n"

    "  Legal:\n"
    "    contract                signed agreement, terms of service, or NDA\n"
    "    lease                   rental or property lease agreement\n"
    "    certificate             achievement, birth, marriage, death, or other official certificate\n"
    "    legal_doc               court filings, notarised documents, or formal legal correspondence\n\n"

    "  Miscellaneous Documents:\n"
    "    whiteboard              whiteboard, chalkboard, or sticky-note brainstorm\n"
    "    menu                    restaurant, bar, or venue menu\n"
    "    business_card           business card with contact info\n"
    "    qr_code                 QR code or barcode as the primary subject\n"
    "    handwritten_note        handwritten letter, reminder, or notebook entry\n"
    "    package_label           shipping or delivery label, or tracking notice\n"
    "    gift_card               gift card, store voucher, or coupon\n"
    "    form                    survey, application, waiver, or registration form\n"
    "    scanned_doc             generic document scan not matching any type above\n\n"

    # ── Health & Fitness ───────────────────────────────────────────────────────
    "HEALTH_FITNESS — use for exercise, sport, or body-progress content.\n"
    "Subcategories: gym, workout, running, yoga, cycling, sports_game, sports_practice, "
    "progress_photo, before_after, meal_prep.\n"
    "Use health_fitness (not everyday) when the primary subject is deliberate physical "
    "activity or a fitness-tracking photo.\n\n"

    # ── Confidence calibration ─────────────────────────────────────────────────
    "CONFIDENCE CALIBRATION:\n"
    "  0.9-1.0  unmistakable — content and context are both clear\n"
    "  0.7-0.9  highly likely — one or two ambiguous signals\n"
    "  0.5-0.7  reasonable guess — notable uncertainty\n"
    "  < 0.5    too unclear → set category to uncategorized\n\n"

    # ── Output schema ──────────────────────────────────────────────────────────
    "OUTPUT: respond with ONLY a single-line JSON object. No prose, no markdown fences.\n"
    '{"category":"<primary>","subcategory":"<specific sub-key or null>",'
    '"confidence":<0.0-1.0>,"description":"<one sentence, max 120 chars>",'
    '"notable":["<key visual element>","<another element>"]}'
)


_MODE_INSTRUCTIONS: dict[NamingMode, str] = {
    NamingMode.CORPORATE: (
        "Style: clean, professional, instantly legible to a stranger. "
        "Capture the specific event, location, or occasion — not just the category. "
        "Snake_case, lowercase. "
        'Examples: "tokyo_client_summit", "sarah_alex_wedding_tuscany", '
        '"team_offsite_q2_2024", "moms_70th_birthday", "iceland_family_trip".'
    ),
    NamingMode.CHAOTIC: (
        "Style: Gen-Z energy, pop-culture references, chaotic but still descriptive. "
        "Snake_case, lowercase. "
        'Examples: "ate_in_tokyo_fr", "main_character_bali_era", '
        '"besties_did_iceland", "family_chaos_thanksgiving", "that_brunch_slapped_ngl".'
    ),
    NamingMode.UNHINGED: (
        "Style: maximum brainrot, absurdist, only loosely tethered to the actual content. "
        "Snake_case, lowercase, still under 40 chars. "
        'Examples: "proof_i_touched_grass", "the_yassification_of_brunch", '
        '"my_villain_era_in_milan", "skibidi_christmas_arc", "ate_left_no_crumbs".'
    ),
}


def build_name_prompt(
    category: str,
    mode: NamingMode,
    metadata_context: str = "",
) -> str:
    """Return the user prompt for `name_event`. Constrains output to a bare folder name.

    Pass ``metadata_context`` (from ``build_cluster_metadata_context``) to give the
    model GPS location, time-of-day, and camera context when naming — so folders like
    "tokyo_trip" or "paris_evening_walk" emerge naturally from coordinates.
    """
    style = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS[NamingMode.CORPORATE])
    meta_section = f"{metadata_context}\n\n" if metadata_context else ""
    return (
        f"{meta_section}"
        "Generate a single descriptive folder name for this group of photos.\n"
        f"Category: {category}\n"
        f"{style}\n"
        "Hard rules:\n"
        "- snake_case, lowercase ASCII letters, digits, and underscores only\n"
        "- 40 characters or fewer\n"
        "- no quotes, no punctuation, no file extension, no date prefix\n"
        "- if GPS location is provided above, work it into the name "
        "(e.g. 'tokyo_street_food', 'paris_evening_walk', 'yosemite_hike')\n"
        "- name the specific event or place, not just the category\n"
        "- output ONLY the folder name, nothing else"
    )


def _time_of_day(hour: int) -> str:
    if 5 <= hour < 8:
        return "early morning"
    if 8 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def build_cluster_metadata_context(photos: list[PhotoInput]) -> str:
    """Format rich EXIF metadata as a context block for ALL classification decisions.

    Includes per-photo details (filename, camera, GPS coords, time-of-day, dimensions)
    and a cluster-level summary (location centroid, time span, cameras seen).
    Passed to the LLM alongside thumbnails so metadata can disambiguate category,
    subcategory, and location — not just screenshot vs. photo.
    """
    if not photos:
        return ""

    lines = ["╌╌╌ PHOTO METADATA — read before looking at images ╌╌╌"]

    for i, photo in enumerate(photos, 1):
        m = photo.metadata
        camera = m.camera_model or "none"
        if m.gps:
            gps_str = f"{m.gps.lat:.5f}, {m.gps.lon:.5f}"
        else:
            gps_str = "none"
        if m.date_taken:
            tod = _time_of_day(m.date_taken.hour)
            date_str = f"{m.date_taken.strftime('%Y-%m-%d %H:%M')} ({tod})"
        else:
            date_str = "unknown"
        kb = m.file_size // 1024
        dims = f"{m.width}×{m.height}"
        lines.append(
            f"  [{i}] {m.path.name}  |  {dims}  |  {kb}KB"
            f"\n      camera: {camera}  |  gps: {gps_str}  |  {date_str}"
        )

    # ── Cluster summary ───────────────────────────────────────────────────────
    lines.append("")
    lines.append("CLUSTER SUMMARY:")

    gps_list = [p.metadata.gps for p in photos if p.metadata.gps]
    if gps_list:
        avg_lat = sum(g.lat for g in gps_list) / len(gps_list)
        avg_lon = sum(g.lon for g in gps_list) / len(gps_list)
        lines.append(
            f"  location centroid: {avg_lat:.5f}, {avg_lon:.5f}"
            " — identify the nearest city/country/landmark and use it for category and name"
        )
    else:
        lines.append("  location: no GPS data available")

    dates = sorted(p.metadata.date_taken for p in photos if p.metadata.date_taken)
    if len(dates) >= 2:
        span = (dates[-1] - dates[0]).days
        lines.append(
            f"  time span: {dates[0].strftime('%Y-%m-%d')} → {dates[-1].strftime('%Y-%m-%d')}"
            f" ({span}d) — spans > 1 day suggest a trip, event, or multi-day occasion"
        )
    elif dates:
        lines.append(f"  date: {dates[0].strftime('%Y-%m-%d')}")

    cameras = sorted({p.metadata.camera_model for p in photos if p.metadata.camera_model})
    if cameras:
        lines.append(f"  camera(s): {', '.join(cameras)}")

    lines.append("╌╌╌")
    return "\n".join(lines)


def build_roast_prompt(stats: LibraryStats) -> str:
    """Return a prompt asking the model to roast the user's library."""
    payload = json.dumps(asdict(stats), default=str)
    return (
        "You are a sassy, Gen-Z photo-app that just finished reorganising someone's entire camera roll. "
        "Roast them lovingly based on these stats.\n\n"
        "Rules:\n"
        "- 3 to 6 short, punchy lines — vary the sentence structure\n"
        "- Mention specific numbers wherever possible: total photos, duplicates, "
        "screenshots, cats, food shots, selfies, folders created, time taken\n"
        "- If notable_findings has entries, weave at least one in naturally\n"
        "- Be playful and self-aware, never cruel\n"
        "- No hashtags. Max 2 emojis total.\n"
        "- Total output under 600 characters\n\n"
        f"Stats JSON:\n{payload}"
    )

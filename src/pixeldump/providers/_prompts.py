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
    "All photos supplied come from the same time-clustered event. "
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


def build_name_prompt(category: str, mode: NamingMode) -> str:
    """Return the user prompt for `name_event`. Constrains output to a bare folder name."""
    style = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS[NamingMode.CORPORATE])
    return (
        "Look at these photos and generate a single descriptive folder name for this event.\n"
        f"Category hint: {category}\n"
        f"{style}\n"
        "Hard rules:\n"
        "- snake_case, lowercase ASCII letters, digits, and underscores only\n"
        "- 40 characters or fewer\n"
        "- no quotes, no punctuation, no file extension, no date prefix\n"
        "- name the specific event or place, not just the category\n"
        "- output ONLY the folder name, nothing else"
    )


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

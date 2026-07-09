"""Single source of truth for all CRUX/Agnes model identifiers.

GPT Agnes audit fix #1: 82 hardcoded "agnes-*" strings across 15+ files.
One version bump now changes ONE file. Also eliminates typo bugs and
makes model routing tests stable.

Usage:
    from core.agnes_models import CRUX_TEXT, CRUX_IMAGE, CRUX_VIDEO
    client.chat(model=CRUX_TEXT)
"""

# ── Primary CRUX models (active generation) ──

# Text / chat / vision / tool-calling model
CRUX_TEXT = "agnes-2.0-flash"

# Image generation models
CRUX_IMAGE_FAST = "agnes-image-2.1-flash"  # high-quality text-to-image
CRUX_IMAGE_EDIT = "agnes-image-2.0-flash"  # image-to-image / multi-image editing

# Video generation model
CRUX_VIDEO = "agnes-video-v2.0"

# ── Legacy / deprecated models (kept for reference) ──

CRUX_TEXT_LEGACY = "agnes-1.5-flash"  # still available on API

# ── Convenience aliases (match models.json tier naming) ──

CRUX_IMAGE = CRUX_IMAGE_FAST  # default image model
CRUX_IMAGE_MULTI = CRUX_IMAGE_EDIT  # alias for multi-image workflows

# ── Mapping: tier → model ID (for ProviderManager.get_model()) ──

TIER_TO_MODEL = {
    "light": CRUX_TEXT,
    "pro": CRUX_TEXT,
    "heavy": CRUX_TEXT,
    "image": CRUX_IMAGE,
    "image_edit": CRUX_IMAGE_EDIT,
    "video": CRUX_VIDEO,
}

# ── All available CRUX models (for /models listing) ──

ALL_CRUX_MODELS = [
    CRUX_TEXT,
    CRUX_TEXT_LEGACY,
    CRUX_IMAGE,
    CRUX_IMAGE_EDIT,
    CRUX_VIDEO,
]

"""JSON tool schemas exposed by the NovelAI Hermes plugin."""

from __future__ import annotations

from typing import Any

from .constants import ASPECT_DIMENSIONS, MODELS, VALID_NOISE_SCHEDULES, VALID_SAMPLERS

NOVELAI_GENERATE_SCHEMA: dict[str, Any] = {
    "name": "novelai_generate",
    "description": (
        "Generate anime/illustration images via NovelAI with full parameter control: "
        "NAI Diffusion 5 / 4.5 / 4 / 3 models, custom negative prompts & UC presets, "
        "multi-character prompts with spatial coordinates (V4/V4.5/V5), custom resolution/steps/CFG/sampler/seed, "
        "Variety+ boost, img2img (strength/noise), Precise Reference (character/style), and Vibe Transfer. "
        "IMPORTANT: Always include the returned `media_tag` (`MEDIA:/abs/path/to/image.png`) on its own line "
        "in your reply so Telegram sends the image."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Main positive prompt in English (Danbooru tags and/or concise natural description). "
                    "Supports NovelAI weighting syntax like `1.2::blue eyes::`, `{emphasis}`, `[de-emphasis]`."
                ),
            },
            "negative_prompt": {
                "type": "string",
                "description": "Extra undesired content (UC) tags to avoid. Merged with uc_preset unless uc_preset='none'.",
            },
            "uc_preset": {
                "type": "string",
                "enum": ["heavy", "light", "furry_focus", "human_focus", "none"],
                "description": "Built-in NovelAI Undesired Content preset (default: 'heavy').",
            },
            "model": {
                "type": "string",
                "enum": list(MODELS.keys()),
                "description": "NovelAI diffusion model (default: configured model, usually 'nai-diffusion-5-full').",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": list(ASPECT_DIMENSIONS.keys()),
                "description": (
                    "Preset canvas size. Opus-free sizes: portrait (832x1216), landscape (1216x832), "
                    "square (1024x1024). Larger sizes: large_portrait (1024x1536), large_landscape (1536x1024), "
                    "large_square (1472x1472), wallpaper_portrait (1088x1920), wallpaper_landscape (1920x1088)."
                ),
            },
            "width": {
                "type": "integer",
                "description": "Optional custom width in pixels (auto-aligned to multiple of 64, max 2048). Overrides aspect_ratio when paired with height.",
            },
            "height": {
                "type": "integer",
                "description": "Optional custom height in pixels (auto-aligned to multiple of 64, max 2048). Overrides aspect_ratio when paired with width.",
            },
            "characters": {
                "type": "array",
                "description": "V4 / V4.5 / V5 multi-character prompt list (up to 6 characters). Each character can have its own prompt, negative_prompt, and optional position center {x, y} in [0..1].",
                "items": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Character-specific appearance/pose prompt (e.g. 'girl, silver hair, red eyes, holding umbrella').",
                        },
                        "negative_prompt": {
                            "type": "string",
                            "description": "Optional character-specific negative prompt.",
                        },
                        "center": {
                            "type": "object",
                            "description": "Optional normalized position {x, y} where (0,0) is top-left and (1,1) is bottom-right.",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                        },
                    },
                    "required": ["prompt"],
                },
            },
            "steps": {
                "type": "integer",
                "description": "Sampling steps (1-50, default 23; keep <= 28 for Opus free tier).",
            },
            "scale": {
                "type": "number",
                "description": "Prompt Guidance / CFG scale (0-15, default 7.0).",
            },
            "cfg_rescale": {
                "type": "number",
                "description": "Prompt Guidance Rescale (0.0-1.0, default 0.0; try 0.1-0.4 if colors look over-saturated).",
            },
            "sampler": {
                "type": "string",
                "enum": list(VALID_SAMPLERS),
                "description": "Sampler algorithm (default: 'k_euler_ancestral').",
            },
            "noise_schedule": {
                "type": "string",
                "enum": list(VALID_NOISE_SCHEDULES),
                "description": "Noise schedule (default: 'karras').",
            },
            "seed": {
                "type": "integer",
                "description": "Fixed RNG seed for reproducibility (increments by +1 per image when count > 1). Omit for random seeds.",
            },
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 8,
                "description": "Number of images to generate sequentially with the same prompt (1-8, default 1; runs serially with n_samples=1 to keep Opus free tier and avoid 429 concurrency errors).",
            },
            "quality_tags": {
                "type": "boolean",
                "description": "Auto-append NovelAI's recommended quality tags for the selected model (default: true).",
            },
            "variety_boost": {
                "type": "boolean",
                "description": "Enable Variety+ (skip_cfg_above_sigma) for more diverse compositions/poses (default: false).",
            },
            "source_image": {
                "type": "string",
                "description": "Absolute local file path or URL of an existing image for img2img transformation.",
            },
            "strength": {
                "type": "number",
                "description": "Img2Img transformation strength (0.01-0.99, default 0.7; lower preserves more of source_image).",
            },
            "noise": {
                "type": "number",
                "description": "Img2Img extra noise (0.0-0.99, default 0.0).",
            },
            "character_references": {
                "type": "array",
                "description": "V5 / V4.5 Precise Reference images (up to 4) for character identity, outfit (V5), and/or art style consistency. Cannot be combined with vibe_references.",
                "items": {
                    "type": "object",
                    "properties": {
                        "image": {"type": "string", "description": "Local file path or URL of reference image."},
                        "mode": {
                            "type": "string",
                            "enum": ["character&style", "character", "style", "outfit"],
                            "description": "Reference mode (default: 'character&style'; 'outfit' requires V5).",
                        },
                        "strength": {
                            "type": "number",
                            "description": "Reference strength: 0.0-5.0 on V5 (default: 1.0), 0.0-1.0 on V4.5.",
                        },
                        "fidelity": {
                            "type": "number",
                            "description": "V4.5 only: reference fidelity 0.0-1.0 (default: 1.0; ignored on V5).",
                        },
                    },
                    "required": ["image"],
                },
            },
            "vibe_references": {
                "type": "array",
                "description": "Vibe Transfer style/mood reference images (up to 4). Supported on V4.5 / V4 / V3 only (not V5, and cannot be combined with character_references). Encoding a new vibe on V4/V4.5 costs 2 Anlas once and is cached locally.",
                "items": {
                    "type": "object",
                    "properties": {
                        "image": {"type": "string", "description": "Local file path or URL of reference image."},
                        "strength": {"type": "number", "description": "Vibe strength 0.0-1.0 (default: 0.6)."},
                        "information_extracted": {
                            "type": "number",
                            "description": "Information extracted 0.01-1.0 (default: 1.0).",
                        },
                    },
                    "required": ["image"],
                },
            },
        },
        "required": ["prompt"],
    },
}

NOVELAI_STATUS_SCHEMA: dict[str, Any] = {
    "name": "novelai_status",
    "description": "Check the connected NovelAI account subscription tier and remaining Anlas balance.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

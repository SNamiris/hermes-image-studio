"""Constants, model catalog, presets, and prompt guidance for the NovelAI plugin."""

from __future__ import annotations

from typing import Any

GENERATE_URL = "https://image.novelai.net/ai/generate-image"
ENCODE_VIBE_URL = "https://image.novelai.net/ai/encode-vibe"
SUBSCRIPTION_URL = "https://image.novelai.net/user/subscription"

DEFAULT_MODEL = "nai-diffusion-5-full"
DEFAULT_SAMPLER = "k_euler_ancestral"
DEFAULT_NOISE_SCHEDULE = "karras"
DEFAULT_STEPS = 23
DEFAULT_SCALE = 7.0
DEFAULT_CFG_RESCALE = 0.0
DEFAULT_UC_PRESET = "heavy"
DEFAULT_TIMEOUT = 120.0
MAX_BATCH_COUNT = 8

MODELS: dict[str, dict[str, Any]] = {
    "nai-diffusion-5-full": {
        "display": "NAI Diffusion V5 Full",
        "speed": "~6-12s",
        "strengths": "Latest flagship V5 model with highest anime/illustration fidelity, multi-character prompts, and Precise Reference.",
    },
    "nai-diffusion-5-curated": {
        "display": "NAI Diffusion V5 Curated",
        "speed": "~6-12s",
        "strengths": "Curated V5 model with clean aesthetic, strong consistency, multi-character prompts, and Precise Reference.",
    },
    "nai-diffusion-4-5-full": {
        "display": "NAI Diffusion V4.5 Full",
        "speed": "~6-12s",
        "strengths": "Best overall V4.5 anime/illustration quality, multi-character prompts, Precise Reference (character/style).",
    },
    "nai-diffusion-4-5-curated": {
        "display": "NAI Diffusion V4.5 Curated",
        "speed": "~6-12s",
        "strengths": "Cleaner aesthetic, strong consistency, multi-character prompts, Precise Reference.",
    },
    "nai-diffusion-4-full": {
        "display": "NAI Diffusion V4 Full",
        "speed": "~6-12s",
        "strengths": "Strong natural-language + Danbooru hybrid adherence and multi-character support.",
    },
    "nai-diffusion-4-curated-preview": {
        "display": "NAI Diffusion V4 Curated",
        "speed": "~6-12s",
        "strengths": "Curated V4 anime style with multi-character support.",
    },
    "nai-diffusion-3": {
        "display": "NAI Diffusion V3",
        "speed": "~5-10s",
        "strengths": "Classic Danbooru-tag anime model.",
    },
    "nai-diffusion-furry-3": {
        "display": "NAI Diffusion Furry V3",
        "speed": "~5-10s",
        "strengths": "Furry/anthro specialized V3 model.",
    },
}

ASPECT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "portrait": (832, 1216),
    "landscape": (1216, 832),
    "square": (1024, 1024),
    "large_portrait": (1024, 1536),
    "large_landscape": (1536, 1024),
    "large_square": (1472, 1472),
    "wallpaper_portrait": (1088, 1920),
    "wallpaper_landscape": (1920, 1088),
    "small_portrait": (512, 768),
    "small_landscape": (768, 512),
    "small_square": (640, 640),
}

VALID_SAMPLERS = (
    "k_euler_ancestral",
    "k_euler",
    "k_dpmpp_2s_ancestral",
    "k_dpmpp_2m_sde",
    "k_dpmpp_2m",
    "k_dpmpp_sde",
    "ddim_v3",
)

VALID_NOISE_SCHEDULES = ("karras", "native", "exponential", "polyexponential")

QUALITY_SUFFIXES: dict[str, str] = {
    "nai-diffusion-5-full": "very aesthetic, masterpiece, no text",
    "nai-diffusion-5-curated": "very aesthetic, amazing quality, no text",
    "nai-diffusion-4-5-full": "very aesthetic, masterpiece, no text",
    "nai-diffusion-4-5-curated": "rating:general, amazing quality, very aesthetic, absurdres",
    "nai-diffusion-4-full": "no text, best quality, very aesthetic, absurdres",
    "nai-diffusion-4-curated-preview": "rating:general, amazing quality, very aesthetic, absurdres",
    "nai-diffusion-3": "best quality, amazing quality, very aesthetic, absurdres",
    "nai-diffusion-furry-3": "{best quality}, {amazing quality}",
}

UC_PRESETS_V45_FULL: dict[str, tuple[int, str]] = {
    "heavy": (
        0,
        "lowres, artistic error, film grain, scan artifacts, worst quality, bad quality, "
        "jpeg artifacts, very displeasing, chromatic aberration, dithering, halftone, screentone, "
        "multiple views, logo, too many watermarks, negative space, blank page",
    ),
    "light": (
        1,
        "lowres, artistic error, scan artifacts, worst quality, bad quality, jpeg artifacts, "
        "multiple views, very displeasing, too many watermarks, negative space, blank page",
    ),
    "furry_focus": (
        2,
        "{worst quality}, distracting watermark, unfinished, bad quality, {widescreen}, upscale, "
        "{sequence}, {{grandfathered content}}, blurred foreground, chromatic aberration, blank page, "
        "error, missing fingers, bad anatomy",
    ),
    "human_focus": (
        3,
        "lowres, artistic error, film grain, scan artifacts, worst quality, bad quality, "
        "jpeg artifacts, very displeasing, chromatic aberration, dithering, halftone, screentone, "
        "multiple views, logo, too many watermarks, negative space, blank page, @_@, "
        "mismatched pupils, glowing eyes, bad anatomy",
    ),
    "none": (4, ""),
}

UC_PRESETS_V4: dict[str, tuple[int, str]] = {
    "heavy": (
        0,
        "blurry, lowres, upscaled, artistic error, film grain, scan artifacts, bad anatomy, "
        "bad hands, worst quality, bad quality, jpeg artifacts, very displeasing, "
        "chromatic aberration, halftone, multiple views, logo, too many watermarks, "
        "negative space, blank page",
    ),
    "light": (
        1,
        "blurry, lowres, upscaled, artistic error, film grain, scan artifacts, jpeg artifacts, logo, "
        "too many watermarks, negative space, blank page",
    ),
    "furry_focus": UC_PRESETS_V45_FULL["furry_focus"],
    "human_focus": UC_PRESETS_V45_FULL["human_focus"],
    "none": (2, ""),
}

UC_PRESETS_V3: dict[str, tuple[int, str]] = {
    "heavy": (
        0,
        "lowres, {bad}, error, fewer, extra, missing, worst quality, jpeg artifacts, "
        "bad quality, watermark, unfinished, displeasing, chromatic aberration, signature, "
        "extra digits, artistic error, username, scan, [abstract]",
    ),
    "light": (
        1,
        "lowres, jpeg artifacts, worst quality, watermark, blurry, very displeasing",
    ),
    "human_focus": (
        2,
        "lowres, {bad}, error, fewer, extra, missing, worst quality, jpeg artifacts, "
        "bad quality, watermark, unfinished, displeasing, chromatic aberration, signature, "
        "extra digits, artistic error, username, scan, [abstract], bad anatomy, bad hands, "
        "@_@, mismatched pupils, heart-shaped pupils, glowing eyes",
    ),
    "none": (3, ""),
}

DIRECTOR_REF_MODES = {"character&style", "character", "style", "outfit"}

TIER_NAMES: dict[int, str] = {
    0: "Paper (Free)",
    1: "Tablet",
    2: "Scroll",
    3: "Opus",
}

SYSTEM_PROMPT_GUIDANCE = """## NovelAI Image Generation

NovelAI is configured as your image generation backend (default: `nai-diffusion-5-full`, steps=23, scale=7.0, sampler=k_euler_ancestral, noise_schedule=karras, cfg_rescale=0.0).
- Use `image_generate` for quick standard requests (text-to-image or simple edit/reference); it automatically delivers the image on Telegram.
- Use `novelai_generate` when the user wants full NovelAI control: batch generation (`count` 1-8, serial to preserve Opus free tier and avoid 429), negative prompts (UC), multi-character prompts/positions (`characters`), fixed `seed`, custom `width`/`height`/`steps`/`scale`/`sampler`, `variety_boost`, img2img `strength`/`noise`, Precise Reference (`character_references`), or Vibe Transfer (`vibe_references`).
- IMPORTANT: After calling `novelai_generate`, ALWAYS include every returned `MEDIA:/abs/path/to/file.png` line from `media_tag` / `media_tags` on its own line in your final reply so Telegram attaches and sends all generated images.
- Use `novelai_status` if the user asks about their NovelAI subscription tier or remaining Anlas.
- Write NovelAI prompts in English combining clean Danbooru tags and concise natural scene descriptions (V5 / V4.5 excel at both). Keep default resolutions at `832x1216`, `1216x832`, or `1024x1024` and `steps <= 28` unless larger sizes are requested (stays within Opus free-generation limits).
"""

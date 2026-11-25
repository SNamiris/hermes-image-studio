"""NovelAI image generation backend plugin for Hermes Agent.

Provides:
1. ``ImageGenProvider`` implementation (``provider: novelai``) powering built-in ``image_generate``.
2. ``novelai_generate`` tool (in ``image_gen`` toolset) exposing full NovelAI controls:
   - NAI Diffusion 4.5 / 4 / 3 models
   - Custom negative prompt & UC presets
   - Multi-character prompts with optional spatial coordinates (V4 / V4.5)
   - Sampler, noise schedule, steps, CFG scale, CFG rescale, seed, Variety+
   - Image-to-Image (strength, noise)
   - Precise / Character Reference (V4.5 director_reference_*)
   - Vibe Transfer (with V4/V4.5 /ai/encode-vibe + local cache)
3. ``novelai_status`` tool to inspect NovelAI subscription tier and remaining Anlas.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import random
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import requests
from PIL import Image

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    normalize_reference_images,
    resolve_aspect_ratio,
    save_b64_image,
    success_response,
)

logger = logging.getLogger(__name__)

GENERATE_URL = "https://image.novelai.net/ai/generate-image"
ENCODE_VIBE_URL = "https://image.novelai.net/ai/encode-vibe"
SUBSCRIPTION_URL = "https://image.novelai.net/user/subscription"

DEFAULT_MODEL = "nai-diffusion-4-5-full"
DEFAULT_SAMPLER = "k_euler_ancestral"
DEFAULT_NOISE_SCHEDULE = "karras"
DEFAULT_STEPS = 28
DEFAULT_SCALE = 5.0
DEFAULT_CFG_RESCALE = 0.0
DEFAULT_UC_PRESET = "heavy"
DEFAULT_TIMEOUT = 120.0

MODELS: dict[str, dict[str, Any]] = {
    "nai-diffusion-4-5-full": {
        "display": "NAI Diffusion V4.5 Full",
        "speed": "~6-12s",
        "strengths": "Best overall anime/illustration quality, multi-character prompts, Precise Reference (character/style).",
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

DIRECTOR_REF_MODES = {"character&style", "character", "style"}

SYSTEM_PROMPT_GUIDANCE = """## NovelAI Image Generation

NovelAI is configured as your image generation backend (default: `nai-diffusion-4-5-full`).
- Use `image_generate` for quick standard requests (text-to-image or simple edit/reference); it automatically delivers the image on Telegram.
- Use `novelai_generate` when the user wants full NovelAI control: negative prompts (UC), multi-character prompts/positions (`characters`), fixed `seed`, custom `width`/`height`/`steps`/`scale`/`sampler`, `variety_boost`, img2img `strength`/`noise`, V4.5 Precise Reference (`character_references`), or Vibe Transfer (`vibe_references`).
- IMPORTANT: After calling `novelai_generate`, ALWAYS include the returned `media_tag` (exact `MEDIA:/abs/path/to/file.png` on its own line) in your final reply so Telegram attaches and sends the generated image.
- Use `novelai_status` if the user asks about their NovelAI subscription tier or remaining Anlas.
- Write NovelAI prompts in English combining clean Danbooru tags and concise natural scene descriptions (V4.5 excels at both). Keep default resolutions at `832x1216`, `1216x832`, or `1024x1024` and `steps <= 28` unless larger sizes are requested (stays within Opus free-generation limits).
"""


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes").expanduser()


def _load_novelai_config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        ig = cfg.get("image_gen") if isinstance(cfg, dict) else None
        sub = ig.get("novelai") if isinstance(ig, dict) else None
        return sub if isinstance(sub, dict) else {}
    except Exception as exc:
        logger.debug("Could not load image_gen.novelai config: %s", exc)
        return {}


def _get_api_key() -> str:
    for var in ("NOVELAI_API_KEY", "NAI_API_KEY", "NOVELAI_TOKEN"):
        raw = os.environ.get(var, "").strip()
        if raw:
            if raw.lower().startswith("bearer "):
                raw = raw[7:].strip()
            return raw.strip("\"'")
    return ""


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }


def _is_v45(model: str) -> bool:
    return "4-5" in model


def _is_v4_family(model: str) -> bool:
    return "nai-diffusion-4" in model


def _align_64(value: int, *, minimum: int = 64, maximum: int = 2048) -> int:
    clamped = max(minimum, min(maximum, int(value)))
    return max(minimum, (clamped // 64) * 64)


def _resolve_dimensions(
    aspect_ratio: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    source_pil: Optional[Image.Image] = None,
) -> tuple[int, int, str]:
    if width and height:
        w = _align_64(width)
        h = _align_64(height)
        ratio_label = "square" if w == h else ("landscape" if w > h else "portrait")
        return w, h, ratio_label

    if isinstance(aspect_ratio, str) and aspect_ratio.strip().lower() in ASPECT_DIMENSIONS:
        key = aspect_ratio.strip().lower()
        w, h = ASPECT_DIMENSIONS[key]
        return w, h, key

    if source_pil is not None:
        sw, sh = source_pil.size
        if sw > sh * 1.15:
            return 1216, 832, "landscape"
        if sh > sw * 1.15:
            return 832, 1216, "portrait"
        return 1024, 1024, "square"

    ar = resolve_aspect_ratio(aspect_ratio or DEFAULT_ASPECT_RATIO)
    w, h = ASPECT_DIMENSIONS.get(ar, (832, 1216))
    return w, h, ar


def _apply_quality_tags(prompt: str, model: str, enabled: bool) -> str:
    clean = prompt.strip()
    if not enabled:
        return clean
    suffix = QUALITY_SUFFIXES.get(model, QUALITY_SUFFIXES[DEFAULT_MODEL])
    lower = clean.lower()
    if "very aesthetic" in lower or "masterpiece" in lower or "amazing quality" in lower:
        return clean
    return f"{clean}, {suffix}" if clean else suffix


def _resolve_negative_prompt(
    negative_prompt: Optional[str],
    uc_preset: str,
    model: str,
    cfg: dict[str, Any],
) -> tuple[int, str]:
    preset_key = (uc_preset or DEFAULT_UC_PRESET).strip().lower()
    if _is_v45(model):
        table = UC_PRESETS_V45_FULL
    elif _is_v4_family(model):
        table = UC_PRESETS_V4
    else:
        table = UC_PRESETS_V3

    if preset_key not in table:
        preset_key = "heavy"
    preset_idx, preset_text = table[preset_key]

    parts: list[str] = []
    if preset_text:
        parts.append(preset_text)

    default_extra = str(cfg.get("default_negative_prompt") or "").strip()
    if default_extra and preset_key != "none":
        parts.append(default_extra)

    user_neg = (negative_prompt or "").strip()
    if user_neg:
        parts.append(user_neg)

    merged = ", ".join(p.strip(", ") for p in parts if p.strip(", "))
    return preset_idx, merged


def _load_image_from_ref(ref: str, timeout: float = 30.0) -> tuple[Image.Image, bytes]:
    """Load an image from a local file path, file:// URI, data: URI, or http(s) URL."""
    raw = ref.strip()
    if raw.startswith("data:"):
        _, b64 = raw.split(",", 1)
        data = base64.b64decode(b64)
    elif raw.startswith(("http://", "https://")):
        resp = requests.get(raw, timeout=timeout)
        resp.raise_for_status()
        data = resp.content
    else:
        if raw.startswith("file://"):
            parsed = urlparse(raw)
            path_str = unquote(parsed.path)
        else:
            path_str = raw
        p = Path(path_str).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"Image file not found: {p}")
        data = p.read_bytes()

    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    return img, data


def _pil_to_png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _fit_cover(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Aspect-preserving center crop + resize for img2img."""
    src = img.convert("RGB")
    sw, sh = src.size
    if (sw, sh) == (target_w, target_h):
        return src
    scale = max(target_w / sw, target_h / sh)
    nw, nh = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - target_w) // 2)
    top = max(0, (nh - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _pad_director_reference(img: Image.Image) -> Image.Image:
    """Letterbox a reference image onto NovelAI's required V4.5 Precise Reference canvas."""
    src = img.convert("RGB")
    sw, sh = src.size
    if sh > sw * 1.15:
        canvas_w, canvas_h = 1024, 1536
    elif sw > sh * 1.15:
        canvas_w, canvas_h = 1536, 1024
    else:
        canvas_w, canvas_h = 1472, 1472

    scale = min(canvas_w / sw, canvas_h / sh)
    nw, nh = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    canvas.paste(resized, ((canvas_w - nw) // 2, (canvas_h - nh) // 2))
    return canvas


def _encode_vibe_v4(
    api_key: str,
    img: Image.Image,
    raw_bytes: bytes,
    model: str,
    information_extracted: float,
    timeout: float,
) -> str:
    """Encode a Vibe Transfer image for V4/V4.5 via /ai/encode-vibe with disk cache (saves 2 Anlas/reuse)."""
    info_val = max(0.01, min(1.0, float(information_extracted)))
    cache_dir = _hermes_home() / "cache" / "novelai_vibes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(
        raw_bytes + f"|{model}|{info_val:.4f}".encode("utf-8")
    ).hexdigest()
    cache_file = cache_dir / f"{digest}.b64"
    if cache_file.is_file():
        cached = cache_file.read_text(encoding="utf-8").strip()
        if cached:
            return cached

    payload = {
        "image": _pil_to_png_b64(img),
        "information_extracted": info_val,
        "model": model,
    }
    resp = requests.post(
        ENCODE_VIBE_URL,
        headers=_auth_headers(api_key),
        json=payload,
        timeout=timeout,
    )
    if not resp.ok:
        raise RuntimeError(
            f"NovelAI /ai/encode-vibe failed ({resp.status_code}): {_extract_http_error(resp)}"
        )
    encoded = base64.b64encode(resp.content).decode("ascii")
    try:
        cache_file.write_text(encoded, encoding="utf-8")
    except OSError:
        pass
    return encoded


def _extract_http_error(resp: Optional[requests.Response]) -> str:
    if resp is None:
        return "No response received"
    try:
        data = resp.json()
        if isinstance(data, dict):
            msg = data.get("message") or data.get("error") or data.get("detail")
            if msg:
                return str(msg)
    except Exception:
        pass
    text = (resp.text or "").strip()
    return text[:400] if text else f"HTTP {resp.status_code}"


def _extract_image_from_zip(content: bytes) -> tuple[bytes, str]:
    """Unpack the first image from NovelAI's ZIP response (or handle raw PNG bytes)."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return content, "png"
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for name in zf.namelist():
            lower = name.lower()
            if lower.endswith((".png", ".webp", ".jpg", ".jpeg")):
                ext = "jpg" if lower.endswith(".jpeg") else lower.rsplit(".", 1)[-1]
                return zf.read(name), ext
        names = zf.namelist()
        if names:
            return zf.read(names[0]), "png"
    raise ValueError("NovelAI returned an empty archive with no image.")


def _normalize_characters(
    characters: Optional[list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Build v4_prompt.char_captions, v4_negative_prompt.char_captions, characterPrompts, use_coords."""
    if not characters:
        return [], [], [], False

    pos_captions: list[dict[str, Any]] = []
    neg_captions: list[dict[str, Any]] = []
    legacy_chars: list[dict[str, Any]] = []
    explicit_coords = False

    for entry in characters[:6]:
        if not isinstance(entry, dict):
            continue
        cprompt = str(entry.get("prompt") or "").strip()
        if not cprompt:
            continue
        cneg = str(entry.get("negative_prompt") or entry.get("uc") or "").strip()
        center_raw = entry.get("center")
        if isinstance(center_raw, dict) and ("x" in center_raw or "y" in center_raw):
            cx = max(0.0, min(1.0, float(center_raw.get("x", 0.5))))
            cy = max(0.0, min(1.0, float(center_raw.get("y", 0.5))))
            explicit_coords = True
        else:
            cx, cy = 0.5, 0.5
        center = {"x": round(cx, 3), "y": round(cy, 3)}
        pos_captions.append({"char_caption": cprompt, "centers": [center]})
        neg_captions.append({"char_caption": cneg, "centers": [center]})
        legacy_chars.append(
            {"prompt": cprompt, "uc": cneg, "center": center, "enabled": True}
        )

    return pos_captions, neg_captions, legacy_chars, explicit_coords


def _generate_novelai(
    *,
    prompt: str,
    negative_prompt: Optional[str] = None,
    uc_preset: Optional[str] = None,
    model: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    characters: Optional[list[dict[str, Any]]] = None,
    steps: Optional[int] = None,
    scale: Optional[float] = None,
    cfg_rescale: Optional[float] = None,
    sampler: Optional[str] = None,
    noise_schedule: Optional[str] = None,
    seed: Optional[int] = None,
    quality_tags: Optional[bool] = None,
    variety_boost: Optional[bool] = None,
    source_image: Optional[str] = None,
    strength: Optional[float] = None,
    noise: Optional[float] = None,
    character_references: Optional[list[dict[str, Any]]] = None,
    vibe_references: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Execute a full NovelAI image generation request and save the result to Hermes image cache."""
    cfg = _load_novelai_config()
    api_key = _get_api_key()
    model_id = (
        (model or "").strip()
        or os.environ.get("NOVELAI_IMAGE_MODEL", "").strip()
        or str(cfg.get("model") or DEFAULT_MODEL).strip()
    )

    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        return error_response(
            error="Prompt is required and must be a non-empty string.",
            error_type="invalid_input",
            provider="novelai",
            model=model_id,
            prompt=str(prompt or ""),
        )

    if not api_key:
        return error_response(
            error="NOVELAI_API_KEY is not set. Add your NovelAI Persistent API Token to ~/.hermes/.env.",
            error_type="auth_error",
            provider="novelai",
            model=model_id,
            prompt=prompt,
        )

    timeout = float(cfg.get("timeout") or DEFAULT_TIMEOUT)
    use_quality = bool(cfg.get("quality_tags", True) if quality_tags is None else quality_tags)
    use_variety = bool(cfg.get("variety_boost", False) if variety_boost is None else variety_boost)
    resolved_sampler = str(sampler or cfg.get("sampler") or DEFAULT_SAMPLER).strip()
    if resolved_sampler not in VALID_SAMPLERS:
        resolved_sampler = DEFAULT_SAMPLER
    resolved_schedule = str(noise_schedule or cfg.get("noise_schedule") or DEFAULT_NOISE_SCHEDULE).strip()
    if resolved_schedule not in VALID_NOISE_SCHEDULES:
        resolved_schedule = DEFAULT_NOISE_SCHEDULE

    resolved_steps = max(1, min(50, int(steps if steps is not None else cfg.get("steps", DEFAULT_STEPS))))
    resolved_scale = max(0.0, min(15.0, float(scale if scale is not None else cfg.get("scale", DEFAULT_SCALE))))
    resolved_rescale = max(
        0.0, min(1.0, float(cfg_rescale if cfg_rescale is not None else cfg.get("cfg_rescale", DEFAULT_CFG_RESCALE)))
    )
    resolved_seed = int(seed) if seed is not None and int(seed) >= 0 else random.randint(0, 2**32 - 1)

    source_pil: Optional[Image.Image] = None
    if source_image:
        try:
            source_pil, _ = _load_image_from_ref(source_image, timeout=30.0)
        except Exception as exc:
            return error_response(
                error=f"Failed to load source_image: {exc}",
                error_type="invalid_input",
                provider="novelai",
                model=model_id,
                prompt=prompt,
            )

    w, h, ratio_label = _resolve_dimensions(
        aspect_ratio=aspect_ratio, width=width, height=height, source_pil=source_pil
    )

    final_prompt = _apply_quality_tags(prompt, model_id, use_quality)
    uc_idx, final_negative = _resolve_negative_prompt(
        negative_prompt,
        uc_preset if uc_preset is not None else str(cfg.get("uc_preset") or DEFAULT_UC_PRESET),
        model_id,
        cfg,
    )

    is_v45 = _is_v45(model_id)
    is_v4 = _is_v4_family(model_id)

    action = "img2img" if source_pil is not None else "generate"

    if is_v4:
        pos_chars, neg_chars, legacy_chars, use_coords = _normalize_characters(characters)
        skip_cfg = (58.0 if is_v45 else 19.0) if use_variety else None
        parameters: dict[str, Any] = {
            "params_version": 3,
            "width": w,
            "height": h,
            "scale": resolved_scale,
            "sampler": resolved_sampler,
            "steps": resolved_steps,
            "n_samples": 1,
            "ucPreset": uc_idx,
            "qualityToggle": use_quality,
            "autoSmea": False,
            "dynamic_thresholding": False,
            "controlnet_strength": 1,
            "legacy": False,
            "add_original_image": True,
            "cfg_rescale": resolved_rescale,
            "noise_schedule": resolved_schedule,
            "legacy_v3_extend": False,
            "skip_cfg_above_sigma": skip_cfg,
            "use_coords": use_coords,
            "legacy_uc": False,
            "normalize_reference_strength_multiple": True,
            "inpaintImg2ImgStrength": 1,
            "seed": resolved_seed,
            "characterPrompts": legacy_chars,
            "v4_prompt": {
                "caption": {
                    "base_caption": final_prompt,
                    "char_captions": pos_chars,
                },
                "use_coords": use_coords,
                "use_order": True,
            },
            "v4_negative_prompt": {
                "caption": {
                    "base_caption": final_negative,
                    "char_captions": neg_chars,
                },
                "legacy_uc": False,
            },
            "negative_prompt": final_negative,
            "deliberate_euler_ancestral_bug": False,
            "prefer_brownian": True,
        }
    else:
        parameters = {
            "params_version": 1,
            "width": w,
            "height": h,
            "scale": resolved_scale,
            "sampler": resolved_sampler,
            "steps": resolved_steps,
            "n_samples": 1,
            "ucPreset": uc_idx,
            "qualityToggle": use_quality,
            "sm": False,
            "sm_dyn": False,
            "dynamic_thresholding": False,
            "controlnet_strength": 1,
            "legacy": False,
            "add_original_image": True,
            "uncond_scale": 1.0,
            "cfg_rescale": resolved_rescale,
            "noise_schedule": resolved_schedule,
            "seed": resolved_seed,
            "negative_prompt": final_negative,
        }

    # Img2Img parameters
    if source_pil is not None:
        fitted = _fit_cover(source_pil, w, h)
        parameters["image"] = _pil_to_png_b64(fitted)
        parameters["strength"] = max(0.01, min(0.99, float(0.7 if strength is None else strength)))
        parameters["noise"] = max(0.0, min(0.99, float(0.0 if noise is None else noise)))
        parameters["extra_noise_seed"] = resolved_seed

    # V4.5 Precise / Character Reference
    if character_references:
        if not is_v45:
            return error_response(
                error="character_references (Precise Reference) requires a V4.5 model (nai-diffusion-4-5-full or nai-diffusion-4-5-curated).",
                error_type="invalid_input",
                provider="novelai",
                model=model_id,
                prompt=prompt,
                aspect_ratio=ratio_label,
            )
        dir_imgs: list[str] = []
        dir_descs: list[dict[str, Any]] = []
        dir_strengths: list[float] = []
        dir_sec_strengths: list[float] = []
        dir_info: list[float] = []

        for ref_item in character_references[:4]:
            if isinstance(ref_item, str):
                ref_item = {"image": ref_item}
            if not isinstance(ref_item, dict) or not ref_item.get("image"):
                continue
            try:
                ref_pil, _ = _load_image_from_ref(str(ref_item["image"]), timeout=30.0)
            except Exception as exc:
                return error_response(
                    error=f"Failed to load character reference image: {exc}",
                    error_type="invalid_input",
                    provider="novelai",
                    model=model_id,
                    prompt=prompt,
                    aspect_ratio=ratio_label,
                )
            mode = str(ref_item.get("mode") or "character&style").strip().lower()
            if mode not in DIRECTOR_REF_MODES:
                mode = "character&style"
            ref_strength = max(0.0, min(1.0, float(ref_item.get("strength", 1.0))))
            fidelity = max(0.0, min(1.0, float(ref_item.get("fidelity", 1.0))))
            sec_strength = round(1.0 - fidelity, 4)

            padded = _pad_director_reference(ref_pil)
            dir_imgs.append(_pil_to_png_b64(padded))
            dir_descs.append(
                {
                    "caption": {"base_caption": mode, "char_captions": []},
                    "legacy_uc": False,
                }
            )
            dir_strengths.append(ref_strength)
            dir_sec_strengths.append(sec_strength)
            dir_info.append(1.0)

        if dir_imgs:
            parameters["director_reference_images"] = dir_imgs
            parameters["director_reference_descriptions"] = dir_descs
            parameters["director_reference_strength_values"] = dir_strengths
            parameters["director_reference_secondary_strength_values"] = dir_sec_strengths
            parameters["director_reference_information_extracted"] = dir_info

    # Vibe Transfer
    if vibe_references:
        vibe_imgs: list[str] = []
        vibe_strengths: list[float] = []
        vibe_infos: list[float] = []
        for vibe_item in vibe_references[:4]:
            if isinstance(vibe_item, str):
                vibe_item = {"image": vibe_item}
            if not isinstance(vibe_item, dict) or not vibe_item.get("image"):
                continue
            try:
                vibe_pil, vibe_raw = _load_image_from_ref(str(vibe_item["image"]), timeout=30.0)
            except Exception as exc:
                return error_response(
                    error=f"Failed to load vibe reference image: {exc}",
                    error_type="invalid_input",
                    provider="novelai",
                    model=model_id,
                    prompt=prompt,
                    aspect_ratio=ratio_label,
                )
            v_strength = max(0.0, min(1.0, float(vibe_item.get("strength", 0.6))))
            v_info = max(0.01, min(1.0, float(vibe_item.get("information_extracted", 1.0))))
            if is_v4:
                try:
                    encoded_vibe = _encode_vibe_v4(api_key, vibe_pil, vibe_raw, model_id, v_info, timeout)
                except Exception as exc:
                    return error_response(
                        error=str(exc),
                        error_type="api_error",
                        provider="novelai",
                        model=model_id,
                        prompt=prompt,
                        aspect_ratio=ratio_label,
                    )
                vibe_imgs.append(encoded_vibe)
                vibe_strengths.append(v_strength)
            else:
                vibe_imgs.append(_pil_to_png_b64(vibe_pil))
                vibe_strengths.append(v_strength)
                vibe_infos.append(v_info)

        if vibe_imgs:
            parameters["reference_image_multiple"] = vibe_imgs
            parameters["reference_strength_multiple"] = vibe_strengths
            if not is_v4 and vibe_infos:
                parameters["reference_information_extracted_multiple"] = vibe_infos

    payload = {
        "input": final_prompt,
        "model": model_id,
        "action": action,
        "parameters": parameters,
    }

    try:
        resp = requests.post(
            GENERATE_URL,
            headers=_auth_headers(api_key),
            json=payload,
            timeout=timeout,
        )
    except requests.Timeout:
        return error_response(
            error=f"NovelAI image generation timed out after {int(timeout)}s.",
            error_type="timeout",
            provider="novelai",
            model=model_id,
            prompt=prompt,
            aspect_ratio=ratio_label,
        )
    except requests.RequestException as exc:
        return error_response(
            error=f"NovelAI connection error: {exc}",
            error_type="connection_error",
            provider="novelai",
            model=model_id,
            prompt=prompt,
            aspect_ratio=ratio_label,
        )

    if not resp.ok:
        detail = _extract_http_error(resp)
        if resp.status_code == 401:
            err_type = "auth_error"
            msg = f"NovelAI authentication failed (401): {detail}. Check NOVELAI_API_KEY."
        elif resp.status_code == 402:
            err_type = "quota_error"
            msg = f"NovelAI insufficient Anlas / subscription required (402): {detail}"
        elif resp.status_code == 429:
            err_type = "rate_limit"
            msg = f"NovelAI rate limit exceeded (429): {detail}. Wait a moment and retry."
        else:
            err_type = "api_error"
            msg = f"NovelAI image generation failed ({resp.status_code}): {detail}"
        return error_response(
            error=msg,
            error_type=err_type,
            provider="novelai",
            model=model_id,
            prompt=prompt,
            aspect_ratio=ratio_label,
        )

    try:
        img_bytes, ext = _extract_image_from_zip(resp.content)
        b64_img = base64.b64encode(img_bytes).decode("ascii")
        prefix = f"novelai_{model_id.replace('-', '_')}"
        saved_path = save_b64_image(b64_img, prefix=prefix, extension=ext)
    except Exception as exc:
        return error_response(
            error=f"Failed to decode or save NovelAI image response: {exc}",
            error_type="invalid_response",
            provider="novelai",
            model=model_id,
            prompt=prompt,
            aspect_ratio=ratio_label,
        )

    modality = "image" if (source_pil is not None or character_references or vibe_references) else "text"
    return success_response(
        image=str(saved_path),
        model=model_id,
        prompt=final_prompt,
        aspect_ratio=ratio_label,
        provider="novelai",
        modality=modality,
        extra={
            "media_tag": f"MEDIA:{saved_path}",
            "width": w,
            "height": h,
            "seed": resolved_seed,
            "steps": resolved_steps,
            "scale": resolved_scale,
            "sampler": resolved_sampler,
            "noise_schedule": resolved_schedule,
            "negative_prompt": final_negative,
            "action": action,
        },
    )


class NovelAIImageGenProvider(ImageGenProvider):
    """Standard Hermes ImageGenProvider backed by NovelAI."""

    @property
    def name(self) -> str:
        return "novelai"

    def is_available(self) -> bool:
        return bool(_get_api_key())

    def default_model(self) -> str:
        cfg = _load_novelai_config()
        return (
            os.environ.get("NOVELAI_IMAGE_MODEL", "").strip()
            or str(cfg.get("model") or DEFAULT_MODEL).strip()
        )

    def list_models(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for mid, meta in MODELS.items():
            rows.append(
                {
                    "id": mid,
                    "display": meta["display"],
                    "speed": meta.get("speed", ""),
                    "strengths": meta.get("strengths", ""),
                }
            )
        return rows

    def capabilities(self) -> dict[str, Any]:
        return {
            "modalities": ["text", "image"],
            "max_reference_images": 4,
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        *,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        model = kwargs.get("model")
        model_id = str(model or self.default_model())
        refs = normalize_reference_images(reference_image_urls) or []

        char_refs: Optional[list[dict[str, Any]]] = None
        vibe_refs: Optional[list[dict[str, Any]]] = None
        if refs:
            if _is_v45(model_id):
                char_refs = [
                    {"image": u, "mode": "character&style", "strength": 1.0, "fidelity": 1.0}
                    for u in refs
                ]
            else:
                vibe_refs = [{"image": u, "strength": 0.6, "information_extracted": 1.0} for u in refs]

        return _generate_novelai(
            prompt=prompt,
            model=model_id,
            aspect_ratio=aspect_ratio,
            source_image=image_url,
            strength=0.65 if image_url else None,
            character_references=char_refs,
            vibe_references=vibe_refs,
        )


NOVELAI_GENERATE_SCHEMA: dict[str, Any] = {
    "name": "novelai_generate",
    "description": (
        "Generate anime/illustration images via NovelAI with full parameter control: "
        "NAI Diffusion 4.5 / 4 / 3 models, custom negative prompts & UC presets, "
        "multi-character prompts with spatial coordinates (V4/V4.5), custom resolution/steps/CFG/sampler/seed, "
        "Variety+ boost, img2img (strength/noise), V4.5 Precise Reference (character/style), and Vibe Transfer. "
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
                "description": "NovelAI diffusion model (default: configured model, usually 'nai-diffusion-4-5-full').",
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
                "description": "V4 / V4.5 multi-character prompt list (up to 6 characters). Each character can have its own prompt, negative_prompt, and optional position center {x, y} in [0..1].",
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
                "description": "Sampling steps (1-50, default 28; keep <= 28 for Opus free tier).",
            },
            "scale": {
                "type": "number",
                "description": "Prompt Guidance / CFG scale (0-15, default 5.0).",
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
                "description": "Fixed RNG seed for reproducibility. Omit for random seed.",
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
                "description": "V4.5 Precise Reference images (up to 4) for character identity and/or art style consistency.",
                "items": {
                    "type": "object",
                    "properties": {
                        "image": {"type": "string", "description": "Local file path or URL of reference image."},
                        "mode": {
                            "type": "string",
                            "enum": ["character&style", "character", "style"],
                            "description": "Reference mode (default: 'character&style').",
                        },
                        "strength": {"type": "number", "description": "Reference strength 0.0-1.0 (default: 1.0)."},
                        "fidelity": {
                            "type": "number",
                            "description": "Reference fidelity 0.0-1.0 (default: 1.0; higher = stricter match).",
                        },
                    },
                    "required": ["image"],
                },
            },
            "vibe_references": {
                "type": "array",
                "description": "Vibe Transfer style/mood reference images (up to 4). Note: encoding a new vibe on V4/V4.5 costs 2 Anlas once and is cached locally.",
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


def _handle_novelai_generate(args: dict[str, Any], **kwargs: Any) -> str:
    result = _generate_novelai(
        prompt=args.get("prompt", ""),
        negative_prompt=args.get("negative_prompt"),
        uc_preset=args.get("uc_preset"),
        model=args.get("model"),
        aspect_ratio=args.get("aspect_ratio"),
        width=args.get("width"),
        height=args.get("height"),
        characters=args.get("characters"),
        steps=args.get("steps"),
        scale=args.get("scale"),
        cfg_rescale=args.get("cfg_rescale"),
        sampler=args.get("sampler"),
        noise_schedule=args.get("noise_schedule"),
        seed=args.get("seed"),
        quality_tags=args.get("quality_tags"),
        variety_boost=args.get("variety_boost"),
        source_image=args.get("source_image"),
        strength=args.get("strength"),
        noise=args.get("noise"),
        character_references=args.get("character_references"),
        vibe_references=args.get("vibe_references"),
    )
    if result.get("success"):
        result["delivery_instruction"] = (
            f"Include `{result['media_tag']}` on its own line in your final response to send this image."
        )
    return json.dumps(result, ensure_ascii=False)


def _handle_novelai_status(args: dict[str, Any], **kwargs: Any) -> str:
    api_key = _get_api_key()
    if not api_key:
        return json.dumps({"success": False, "error": "NOVELAI_API_KEY is not set."}, ensure_ascii=False)

    tier_names = {0: "Paper (Free)", 1: "Tablet", 2: "Scroll", 3: "Opus"}
    try:
        resp = requests.get(
            SUBSCRIPTION_URL,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=15,
        )
        if not resp.ok:
            return json.dumps(
                {"success": False, "error": f"NovelAI API error ({resp.status_code}): {_extract_http_error(resp)}"},
                ensure_ascii=False,
            )
        data = resp.json()
        tier_num = data.get("tier")
        steps_left = data.get("trainingStepsLeft") or {}
        fixed_anlas = int(steps_left.get("fixedTrainingStepsLeft") or 0)
        purchased_anlas = int(steps_left.get("purchasedTrainingSteps") or 0)
        return json.dumps(
            {
                "success": True,
                "active": bool(data.get("active")),
                "tier_code": tier_num,
                "tier": tier_names.get(tier_num, f"Tier {tier_num}"),
                "subscription_anlas": fixed_anlas,
                "paid_anlas": purchased_anlas,
                "total_anlas": fixed_anlas + purchased_anlas,
                "opus_free_generation": bool(data.get("active") and tier_num == 3),
                "default_model": NovelAIImageGenProvider().default_model(),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": f"Failed to query NovelAI status: {exc}"}, ensure_ascii=False)


def _check_novelai_available() -> bool:
    return bool(_get_api_key())


def register(ctx: Any) -> None:
    """Register the NovelAI ImageGenProvider, full-featured tools, and system prompt guidance."""
    ctx.register_image_gen_provider(NovelAIImageGenProvider())
    ctx.register_tool(
        name="novelai_generate",
        toolset="novelai",
        schema=NOVELAI_GENERATE_SCHEMA,
        handler=_handle_novelai_generate,
        check_fn=_check_novelai_available,
        requires_env=["NOVELAI_API_KEY"],
        is_async=False,
        emoji="🎨",
    )
    ctx.register_tool(
        name="novelai_status",
        toolset="novelai",
        schema=NOVELAI_STATUS_SCHEMA,
        handler=_handle_novelai_status,
        check_fn=_check_novelai_available,
        requires_env=["NOVELAI_API_KEY"],
        is_async=False,
        emoji="💎",
    )
    try:
        ctx.register_system_prompt_section(
            id="novelai_image_gen",
            content=SYSTEM_PROMPT_GUIDANCE,
            position="after_memory",
        )
    except Exception as exc:
        logger.debug("Skipping novelai system prompt section registration: %s", exc)

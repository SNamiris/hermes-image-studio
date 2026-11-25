"""NovelAI configuration helpers, model capability checks, and request payload builders."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from agent.image_gen_provider import DEFAULT_ASPECT_RATIO, error_response, resolve_aspect_ratio

from .constants import (
    ASPECT_DIMENSIONS,
    DEFAULT_MODEL,
    DEFAULT_UC_PRESET,
    DIRECTOR_REF_MODES,
    QUALITY_SUFFIXES,
    UC_PRESETS_V3,
    UC_PRESETS_V4,
    UC_PRESETS_V45_FULL,
)
from .media import encode_vibe_v4, load_image_from_ref, pad_director_reference, pil_to_png_b64

logger = logging.getLogger(__name__)


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes").expanduser()


def load_novelai_config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        ig = cfg.get("image_gen") if isinstance(cfg, dict) else None
        sub = ig.get("novelai") if isinstance(ig, dict) else None
        return sub if isinstance(sub, dict) else {}
    except Exception as exc:
        logger.debug("Could not load image_gen.novelai config: %s", exc)
        return {}


def get_api_key() -> str:
    for var in ("NOVELAI_API_KEY", "NAI_API_KEY", "NOVELAI_TOKEN"):
        raw = os.environ.get(var, "").strip()
        if raw:
            if raw.lower().startswith("bearer "):
                raw = raw[7:].strip()
            return raw.strip("\"'")
    return ""


def auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }


def is_v5(model: str) -> bool:
    return "nai-diffusion-5" in model


def is_v45(model: str) -> bool:
    return "4-5" in model


def is_v4_family(model: str) -> bool:
    return "nai-diffusion-4" in model


def supports_v4_prompt(model: str) -> bool:
    return is_v5(model) or is_v4_family(model)


def supports_director_ref(model: str) -> bool:
    return is_v5(model) or is_v45(model)


def resolve_default_model(cfg: Optional[dict[str, Any]] = None) -> str:
    resolved_cfg = load_novelai_config() if cfg is None else cfg
    return (
        os.environ.get("NOVELAI_IMAGE_MODEL", "").strip()
        or str(resolved_cfg.get("model") or DEFAULT_MODEL).strip()
    )


def align_64(value: int, *, minimum: int = 64, maximum: int = 2048) -> int:
    clamped = max(minimum, min(maximum, int(value)))
    return max(minimum, (clamped // 64) * 64)


def resolve_dimensions(
    aspect_ratio: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    source_pil: Optional[Image.Image] = None,
) -> tuple[int, int, str]:
    if width and height:
        w = align_64(width)
        h = align_64(height)
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


def apply_quality_tags(prompt: str, model: str, enabled: bool) -> str:
    clean = prompt.strip()
    if not enabled:
        return clean
    suffix = QUALITY_SUFFIXES.get(model, QUALITY_SUFFIXES[DEFAULT_MODEL])
    lower = clean.lower()
    if "very aesthetic" in lower or "masterpiece" in lower or "amazing quality" in lower:
        return clean
    return f"{clean}, {suffix}" if clean else suffix


def resolve_negative_prompt(
    negative_prompt: Optional[str],
    uc_preset: str,
    model: str,
    cfg: dict[str, Any],
) -> tuple[int, str]:
    preset_key = (uc_preset or DEFAULT_UC_PRESET).strip().lower()
    if supports_director_ref(model):
        table = UC_PRESETS_V45_FULL
    elif is_v4_family(model):
        table = UC_PRESETS_V4
    elif "furry" in model:
        table = {
            "heavy": (0, UC_PRESETS_V45_FULL["furry_focus"][1]),
            "light": UC_PRESETS_V3["light"],
            "none": (2, ""),
        }
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


def normalize_characters(
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
        if isinstance(center_raw, dict) and (center_raw.get("x") is not None or center_raw.get("y") is not None):
            raw_x = center_raw.get("x")
            raw_y = center_raw.get("y")
            cx = max(0.0, min(1.0, float(0.5 if raw_x is None else raw_x)))
            cy = max(0.0, min(1.0, float(0.5 if raw_y is None else raw_y)))
            explicit_coords = True
        else:
            cx, cy = 0.5, 0.5
        center = {"x": round(cx, 3), "y": round(cy, 3)}
        pos_captions.append({"char_caption": cprompt, "centers": [center]})
        neg_captions.append({"char_caption": cneg, "centers": [center]})
        legacy_chars.append({"prompt": cprompt, "uc": cneg, "center": center, "enabled": True})

    return pos_captions, neg_captions, legacy_chars, explicit_coords


def build_base_parameters(
    *,
    model_id: str,
    width: int,
    height: int,
    scale: float,
    sampler: str,
    steps: int,
    uc_idx: int,
    use_quality: bool,
    cfg_rescale: float,
    noise_schedule: str,
    seed: int,
    final_prompt: str,
    final_negative: str,
    characters: Optional[list[dict[str, Any]]],
    use_variety: bool,
) -> dict[str, Any]:
    if supports_v4_prompt(model_id):
        pos_chars, neg_chars, legacy_chars, use_coords = normalize_characters(characters)
        skip_cfg = (58.0 if supports_director_ref(model_id) else 19.0) if use_variety else None
        return {
            "params_version": 4 if is_v5(model_id) else 3,
            "width": width,
            "height": height,
            "scale": scale,
            "sampler": sampler,
            "steps": steps,
            "n_samples": 1,
            "ucPreset": uc_idx,
            "qualityToggle": use_quality,
            "autoSmea": False,
            "dynamic_thresholding": False,
            "controlnet_strength": 1,
            "legacy": False,
            "add_original_image": True,
            "cfg_rescale": cfg_rescale,
            "noise_schedule": noise_schedule,
            "legacy_v3_extend": False,
            "skip_cfg_above_sigma": skip_cfg,
            "use_coords": use_coords,
            "legacy_uc": False,
            "normalize_reference_strength_multiple": True,
            "inpaintImg2ImgStrength": 1,
            "seed": seed,
            "characterPrompts": legacy_chars,
            "v4_prompt": {
                "caption": {"base_caption": final_prompt, "char_captions": pos_chars},
                "use_coords": use_coords,
                "use_order": True,
            },
            "v4_negative_prompt": {
                "caption": {"base_caption": final_negative, "char_captions": neg_chars},
                "legacy_uc": False,
            },
            "negative_prompt": final_negative,
            "deliberate_euler_ancestral_bug": False,
            "prefer_brownian": True,
        }

    return {
        "params_version": 1,
        "width": width,
        "height": height,
        "scale": scale,
        "sampler": sampler,
        "steps": steps,
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
        "cfg_rescale": cfg_rescale,
        "noise_schedule": noise_schedule,
        "skip_cfg_above_sigma": 19.0 if use_variety else None,
        "seed": seed,
        "negative_prompt": final_negative,
    }


def apply_character_references(
    parameters: dict[str, Any],
    character_references: list[dict[str, Any]],
    *,
    model_id: str,
    prompt: str,
    ratio_label: str,
) -> Optional[dict[str, Any]]:
    if not supports_director_ref(model_id):
        return error_response(
            error="character_references (Precise Reference) requires a V5 or V4.5 model.",
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
            ref_pil, _ = load_image_from_ref(str(ref_item["image"]), timeout=30.0)
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
        if mode not in DIRECTOR_REF_MODES or (mode == "outfit" and not is_v5(model_id)):
            mode = "character&style"
        max_strength = 5.0 if is_v5(model_id) else 1.0
        raw_strength = ref_item.get("strength")
        ref_strength = max(0.0, min(max_strength, float(1.0 if raw_strength is None else raw_strength)))
        if is_v5(model_id):
            sec_strength = 0.0
        else:
            raw_fidelity = ref_item.get("fidelity")
            fidelity = max(0.0, min(1.0, float(1.0 if raw_fidelity is None else raw_fidelity)))
            sec_strength = round(1.0 - fidelity, 4)

        dir_imgs.append(pil_to_png_b64(pad_director_reference(ref_pil)))
        dir_descs.append({"caption": {"base_caption": mode, "char_captions": []}, "legacy_uc": False})
        dir_strengths.append(ref_strength)
        dir_sec_strengths.append(sec_strength)
        dir_info.append(1.0)

    if dir_imgs:
        parameters["director_reference_images"] = dir_imgs
        parameters["director_reference_descriptions"] = dir_descs
        parameters["director_reference_strength_values"] = dir_strengths
        parameters["director_reference_secondary_strength_values"] = dir_sec_strengths
        parameters["director_reference_information_extracted"] = dir_info
    return None


def apply_vibe_references(
    parameters: dict[str, Any],
    vibe_references: list[dict[str, Any]],
    *,
    api_key: str,
    model_id: str,
    prompt: str,
    ratio_label: str,
    timeout: float,
) -> Optional[dict[str, Any]]:
    if is_v5(model_id):
        return error_response(
            error=(
                "Vibe Transfer is not supported on V5 models. Use character_references (Precise Reference, "
                "mode='style'/'character'/'outfit') on V5, or switch model to nai-diffusion-4-5-full / 4 / 3."
            ),
            error_type="invalid_input",
            provider="novelai",
            model=model_id,
            prompt=prompt,
            aspect_ratio=ratio_label,
        )
    uses_v4 = supports_v4_prompt(model_id)
    vibe_imgs: list[str] = []
    vibe_strengths: list[float] = []
    vibe_infos: list[float] = []
    cache_dir = hermes_home() / "cache" / "novelai_vibes"

    for vibe_item in vibe_references[:4]:
        if isinstance(vibe_item, str):
            vibe_item = {"image": vibe_item}
        if not isinstance(vibe_item, dict) or not vibe_item.get("image"):
            continue
        try:
            vibe_pil, vibe_raw = load_image_from_ref(str(vibe_item["image"]), timeout=30.0)
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
        if uses_v4:
            try:
                encoded = encode_vibe_v4(
                    headers=auth_headers(api_key),
                    cache_dir=cache_dir,
                    img=vibe_pil,
                    raw_bytes=vibe_raw,
                    model=model_id,
                    information_extracted=v_info,
                    timeout=timeout,
                )
            except Exception as exc:
                return error_response(
                    error=str(exc),
                    error_type="api_error",
                    provider="novelai",
                    model=model_id,
                    prompt=prompt,
                    aspect_ratio=ratio_label,
                )
            vibe_imgs.append(encoded)
            vibe_strengths.append(v_strength)
        else:
            vibe_imgs.append(pil_to_png_b64(vibe_pil))
            vibe_strengths.append(v_strength)
            vibe_infos.append(v_info)

    if vibe_imgs:
        parameters["reference_image_multiple"] = vibe_imgs
        parameters["reference_strength_multiple"] = vibe_strengths
        if not uses_v4 and vibe_infos:
            parameters["reference_information_extracted_multiple"] = vibe_infos
    return None

"""NovelAI HTTP execution: image generation and subscription status lookup."""

from __future__ import annotations

import base64
import random
from typing import Any, Optional

import requests
from PIL import Image

from agent.image_gen_provider import error_response, save_b64_image, success_response

from .constants import (
    DEFAULT_CFG_RESCALE,
    DEFAULT_NOISE_SCHEDULE,
    DEFAULT_SAMPLER,
    DEFAULT_SCALE,
    DEFAULT_STEPS,
    DEFAULT_TIMEOUT,
    DEFAULT_UC_PRESET,
    GENERATE_URL,
    SUBSCRIPTION_URL,
    TIER_NAMES,
    VALID_NOISE_SCHEDULES,
    VALID_SAMPLERS,
)
from .media import extract_http_error, extract_image_from_zip, fit_cover, load_image_from_ref, pil_to_png_b64
from .payload import (
    apply_character_references,
    apply_quality_tags,
    apply_vibe_references,
    auth_headers,
    build_base_parameters,
    get_api_key,
    load_novelai_config,
    resolve_default_model,
    resolve_dimensions,
    resolve_negative_prompt,
)


def generate_novelai(
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
    """Execute a NovelAI generation request and save the result into Hermes's image cache."""
    cfg = load_novelai_config()
    api_key = get_api_key()
    model_id = (model or "").strip() or resolve_default_model(cfg)

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
            source_pil, _ = load_image_from_ref(source_image, timeout=30.0)
        except Exception as exc:
            return error_response(
                error=f"Failed to load source_image: {exc}",
                error_type="invalid_input",
                provider="novelai",
                model=model_id,
                prompt=prompt,
            )

    w, h, ratio_label = resolve_dimensions(
        aspect_ratio=aspect_ratio, width=width, height=height, source_pil=source_pil
    )
    final_prompt = apply_quality_tags(prompt, model_id, use_quality)
    uc_idx, final_negative = resolve_negative_prompt(
        negative_prompt,
        uc_preset if uc_preset is not None else str(cfg.get("uc_preset") or DEFAULT_UC_PRESET),
        model_id,
        cfg,
    )

    parameters = build_base_parameters(
        model_id=model_id,
        width=w,
        height=h,
        scale=resolved_scale,
        sampler=resolved_sampler,
        steps=resolved_steps,
        uc_idx=uc_idx,
        use_quality=use_quality,
        cfg_rescale=resolved_rescale,
        noise_schedule=resolved_schedule,
        seed=resolved_seed,
        final_prompt=final_prompt,
        final_negative=final_negative,
        characters=characters,
        use_variety=use_variety,
    )

    action = "img2img" if source_pil is not None else "generate"
    if source_pil is not None:
        parameters["image"] = pil_to_png_b64(fit_cover(source_pil, w, h))
        parameters["strength"] = max(0.01, min(0.99, float(0.7 if strength is None else strength)))
        parameters["noise"] = max(0.0, min(0.99, float(0.0 if noise is None else noise)))
        parameters["extra_noise_seed"] = resolved_seed

    if character_references and vibe_references:
        return error_response(
            error="character_references (Precise Reference) and vibe_references (Vibe Transfer) cannot be used together.",
            error_type="invalid_input",
            provider="novelai",
            model=model_id,
            prompt=prompt,
            aspect_ratio=ratio_label,
        )

    if character_references:
        err = apply_character_references(
            parameters, character_references, model_id=model_id, prompt=prompt, ratio_label=ratio_label
        )
        if err:
            return err

    if vibe_references:
        err = apply_vibe_references(
            parameters,
            vibe_references,
            api_key=api_key,
            model_id=model_id,
            prompt=prompt,
            ratio_label=ratio_label,
            timeout=timeout,
        )
        if err:
            return err

    payload = {"input": final_prompt, "model": model_id, "action": action, "parameters": parameters}

    try:
        resp = requests.post(GENERATE_URL, headers=auth_headers(api_key), json=payload, timeout=timeout)
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
        detail = extract_http_error(resp)
        err_map = {
            401: ("auth_error", f"NovelAI authentication failed (401): {detail}. Check NOVELAI_API_KEY."),
            402: ("quota_error", f"NovelAI insufficient Anlas / subscription required (402): {detail}"),
            429: ("rate_limit", f"NovelAI rate limit exceeded (429): {detail}. Wait a moment and retry."),
        }
        err_type, msg = err_map.get(
            resp.status_code, ("api_error", f"NovelAI image generation failed ({resp.status_code}): {detail}")
        )
        return error_response(
            error=msg,
            error_type=err_type,
            provider="novelai",
            model=model_id,
            prompt=prompt,
            aspect_ratio=ratio_label,
        )

    try:
        img_bytes, ext = extract_image_from_zip(resp.content)
        b64_img = base64.b64encode(img_bytes).decode("ascii")
        saved_path = save_b64_image(b64_img, prefix=f"novelai_{model_id.replace('-', '_')}", extension=ext)
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


def fetch_subscription_status() -> dict[str, Any]:
    """Query NovelAI subscription tier and remaining Anlas balance."""
    api_key = get_api_key()
    if not api_key:
        return {"success": False, "error": "NOVELAI_API_KEY is not set."}

    try:
        resp = requests.get(
            SUBSCRIPTION_URL,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=15,
        )
        if not resp.ok:
            return {"success": False, "error": f"NovelAI API error ({resp.status_code}): {extract_http_error(resp)}"}
        data = resp.json()
        tier_num = data.get("tier")
        steps_left = data.get("trainingStepsLeft") or {}
        fixed_anlas = int(steps_left.get("fixedTrainingStepsLeft") or 0)
        purchased_anlas = int(steps_left.get("purchasedTrainingSteps") or 0)
        return {
            "success": True,
            "active": bool(data.get("active")),
            "tier_code": tier_num,
            "tier": TIER_NAMES.get(tier_num, f"Tier {tier_num}"),
            "subscription_anlas": fixed_anlas,
            "paid_anlas": purchased_anlas,
            "total_anlas": fixed_anlas + purchased_anlas,
            "opus_free_generation": bool(data.get("active") and tier_num == 3),
            "default_model": resolve_default_model(),
        }
    except Exception as exc:
        return {"success": False, "error": f"Failed to query NovelAI status: {exc}"}

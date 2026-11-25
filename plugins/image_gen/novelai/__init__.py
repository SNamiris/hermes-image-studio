"""NovelAI image generation backend plugin for Hermes Agent.

Registers:
1. ``NovelAIImageGenProvider`` (``provider: novelai``) powering built-in ``image_generate``.
2. ``novelai_generate`` tool (toolset ``novelai``) with full NovelAI parameter controls.
3. ``novelai_status`` tool (toolset ``novelai``) to inspect subscription tier and Anlas.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    normalize_reference_images,
)

from .client import fetch_subscription_status, generate_novelai
from .constants import MODELS, SYSTEM_PROMPT_GUIDANCE
from .payload import get_api_key, resolve_default_model, supports_director_ref
from .schemas import NOVELAI_GENERATE_SCHEMA, NOVELAI_STATUS_SCHEMA

logger = logging.getLogger(__name__)


class NovelAIImageGenProvider(ImageGenProvider):
    """Standard Hermes ImageGenProvider backed by NovelAI."""

    @property
    def name(self) -> str:
        return "novelai"

    def is_available(self) -> bool:
        return bool(get_api_key())

    def default_model(self) -> str:
        return resolve_default_model()

    def list_models(self) -> list[dict[str, Any]]:
        return [
            {
                "id": mid,
                "display": meta["display"],
                "speed": meta.get("speed", ""),
                "strengths": meta.get("strengths", ""),
            }
            for mid, meta in MODELS.items()
        ]

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
        model_id = str(kwargs.get("model") or self.default_model())
        refs = normalize_reference_images(reference_image_urls) or []

        char_refs: Optional[list[dict[str, Any]]] = None
        vibe_refs: Optional[list[dict[str, Any]]] = None
        if refs:
            if supports_director_ref(model_id):
                char_refs = [
                    {"image": u, "mode": "character&style", "strength": 1.0, "fidelity": 1.0}
                    for u in refs
                ]
            else:
                vibe_refs = [{"image": u, "strength": 0.6, "information_extracted": 1.0} for u in refs]

        return generate_novelai(
            prompt=prompt,
            model=model_id,
            aspect_ratio=aspect_ratio,
            source_image=image_url,
            strength=0.65 if image_url else None,
            character_references=char_refs,
            vibe_references=vibe_refs,
        )


def _handle_novelai_generate(args: dict[str, Any], **kwargs: Any) -> str:
    result = generate_novelai(
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
    return json.dumps(fetch_subscription_status(), ensure_ascii=False)


def _check_novelai_available() -> bool:
    return bool(get_api_key())


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

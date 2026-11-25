"""ComfyUI API workflow image generation plugin for Hermes Agent.

Registers:
1. ``ComfyUIImageGenProvider`` (``provider: comfyui``) for optional ``image_generate`` routing.
2. ``comfyui_generate`` tool (toolset ``comfyui``) for on-demand API workflow execution.
3. ``comfyui_status`` tool (toolset ``comfyui``) for liveness probe & workflow listing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agent.image_gen_provider import DEFAULT_ASPECT_RATIO, ImageGenProvider

from .client import check_comfyui_status, generate_comfyui
from .constants import SYSTEM_PROMPT_GUIDANCE
from .schemas import COMFYUI_GENERATE_SCHEMA, COMFYUI_STATUS_SCHEMA
from .workflow import get_base_url, list_workflows, resolve_default_workflow

logger = logging.getLogger(__name__)


class ComfyUIImageGenProvider(ImageGenProvider):
    """Standard Hermes ImageGenProvider backed by a remote/local ComfyUI server."""

    @property
    def name(self) -> str:
        return "comfyui"

    def is_available(self) -> bool:
        return bool(get_base_url())

    def default_model(self) -> str:
        return resolve_default_workflow()

    def list_models(self) -> list[dict[str, Any]]:
        workflows = list_workflows() or [resolve_default_workflow()]
        return [
            {
                "id": wf,
                "display": f"ComfyUI Workflow: {wf}",
                "speed": "local GPU",
                "strengths": "Custom ComfyUI API workflow",
            }
            for wf in workflows
        ]

    def capabilities(self) -> dict[str, Any]:
        return {
            "modalities": ["text"],
            "max_reference_images": 0,
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
        workflow = kwargs.get("model") or kwargs.get("workflow")
        return generate_comfyui(
            prompt=prompt,
            workflow=str(workflow) if workflow else None,
            aspect_ratio=aspect_ratio,
        )


def _handle_comfyui_generate(args: dict[str, Any], **kwargs: Any) -> str:
    result = generate_comfyui(
        prompt=args.get("prompt", ""),
        negative_prompt=args.get("negative_prompt"),
        workflow=args.get("workflow"),
        aspect_ratio=args.get("aspect_ratio"),
        width=args.get("width"),
        height=args.get("height"),
        steps=args.get("steps"),
        cfg=args.get("cfg"),
        seed=args.get("seed"),
    )
    if result.get("success"):
        result["delivery_instruction"] = (
            f"Include `{result['media_tag']}` on its own line in your final response to send this image."
        )
    return json.dumps(result, ensure_ascii=False)


def _handle_comfyui_status(args: dict[str, Any], **kwargs: Any) -> str:
    return json.dumps(check_comfyui_status(), ensure_ascii=False)


def register(ctx: Any) -> None:
    """Register the ComfyUI provider, on-demand workflow tools, and prompt guidance."""
    ctx.register_image_gen_provider(ComfyUIImageGenProvider())
    ctx.register_tool(
        name="comfyui_generate",
        toolset="comfyui",
        schema=COMFYUI_GENERATE_SCHEMA,
        handler=_handle_comfyui_generate,
        is_async=False,
        emoji="🖥️",
    )
    ctx.register_tool(
        name="comfyui_status",
        toolset="comfyui",
        schema=COMFYUI_STATUS_SCHEMA,
        handler=_handle_comfyui_status,
        is_async=False,
        emoji="📡",
    )
    try:
        ctx.register_system_prompt_section(
            id="comfyui_image_gen",
            content=SYSTEM_PROMPT_GUIDANCE,
            position="after_memory",
        )
    except Exception as exc:
        logger.debug("Skipping comfyui system prompt section registration: %s", exc)

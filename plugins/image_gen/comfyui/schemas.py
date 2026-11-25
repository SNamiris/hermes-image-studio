"""JSON tool schemas exposed by the ComfyUI Hermes plugin."""

from __future__ import annotations

from typing import Any

from .constants import ASPECT_DIMENSIONS

COMFYUI_GENERATE_SCHEMA: dict[str, Any] = {
    "name": "comfyui_generate",
    "description": (
        "Generate an image using a ComfyUI API workflow running on the user's remote/Tailscale GPU machine. "
        "Injects the positive prompt and optional key overrides (negative_prompt, workflow, aspect_ratio/width/height, "
        "steps, cfg, seed) while preserving all other nodes and defaults inside the workflow JSON. "
        "IMPORTANT: Always include the returned `media_tag` (`MEDIA:/abs/path/to/image.png`) on its own line "
        "in your reply so Telegram sends the image."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Positive prompt to inject into the workflow's positive text node.",
            },
            "negative_prompt": {
                "type": "string",
                "description": "Optional negative prompt override. Omit to keep the workflow's built-in negative prompt.",
            },
            "workflow": {
                "type": "string",
                "description": "Workflow name (filename stem under workflows/, e.g. 'default'). Omit to use the configured default workflow.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": list(ASPECT_DIMENSIONS.keys()),
                "description": "Optional canvas preset: portrait (832x1216), landscape (1216x832), square (1024x1024), tall (768x1344), wide (1344x768). Omit to keep the workflow's original size.",
            },
            "width": {
                "type": "integer",
                "description": "Optional custom width in pixels (aligned to multiple of 16). Must be paired with height.",
            },
            "height": {
                "type": "integer",
                "description": "Optional custom height in pixels (aligned to multiple of 16). Must be paired with width.",
            },
            "steps": {
                "type": "integer",
                "description": "Optional sampling steps override. Omit to keep the workflow's default steps.",
            },
            "cfg": {
                "type": "number",
                "description": "Optional CFG / guidance scale override. Omit to keep the workflow's default CFG.",
            },
            "seed": {
                "type": "integer",
                "description": "Optional fixed seed for reproducibility (increments by +1 per run when count > 1). Omit to generate fresh random seeds.",
            },
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 8,
                "description": "Number of images to generate sequentially with the same prompt (1-8, default 1; runs serially to avoid GPU VRAM spikes).",
            },
        },
        "required": ["prompt"],
    },
}

COMFYUI_STATUS_SCHEMA: dict[str, Any] = {
    "name": "comfyui_status",
    "description": "Check if the remote/Tailscale ComfyUI server is online, show GPU VRAM summary, and list available API workflows.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

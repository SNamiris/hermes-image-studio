"""Constants, defaults, aspect presets, and prompt guidance for the ComfyUI plugin."""

from __future__ import annotations

DEFAULT_WORKFLOW = "default"
DEFAULT_PROBE_TIMEOUT = 3.0
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_GENERATION_TIMEOUT = 180.0

ASPECT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "portrait": (832, 1216),
    "landscape": (1216, 832),
    "square": (1024, 1024),
    "tall": (768, 1344),
    "wide": (1344, 768),
}

SAMPLER_CLASS_TYPES = frozenset({
    "KSampler",
    "KSamplerAdvanced",
    "SamplerCustom",
    "SamplerCustomAdvanced",
})

LATENT_CLASS_TYPES = frozenset({
    "EmptyLatentImage",
    "EmptySD3LatentImage",
    "EmptyFlux2LatentImage",
})

TEXT_NODE_CLASS_TYPES = frozenset({
    "CLIPTextEncode",
    "CLIPTextEncodeFlux",
    "CLIPTextEncodeSDXL",
    "CLIPTextEncodeSD3",
    "BNK_CLIPTextEncodeAdvanced",
    "Text Multiline",
    "PrimitiveNode",
    "StringConstant",
    "StringConstantMultiline",
})

SYSTEM_PROMPT_GUIDANCE = """## ComfyUI Local/Remote Image Generation

ComfyUI is available as an on-demand backend tool (`comfyui_generate` and `comfyui_status`).
- Keep using `image_generate` / `novelai_generate` (NAI V5 Full) for default requests unless the user explicitly asks to use ComfyUI / local GPU / a specific ComfyUI workflow.
- Use `comfyui_status` to check whether the user's ComfyUI machine is online (via Tailscale) and list available API workflows.
- Use `comfyui_generate` to run an API workflow JSON with a custom `prompt` and optional `negative_prompt`, `workflow`, `aspect_ratio` / `width` / `height`, `steps`, `cfg`, and `seed`. Omit optional parameters to preserve the workflow's original defaults.
- IMPORTANT: After calling `comfyui_generate`, ALWAYS include the returned `media_tag` (`MEDIA:/abs/path/to/file.png`) on its own line in your final reply so Telegram attaches and sends the generated image.
"""

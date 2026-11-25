---
name: comfyui-workflow
description: Guide for invoking the user's remote/Tailscale ComfyUI API workflows via comfyui_generate and comfyui_status alongside NovelAI.
---

# ComfyUI API Workflow Guide

## When to Use ComfyUI vs. NovelAI

- **Default**: Use `image_generate` / `novelai_generate` (NAI V5 Full) for general anime/illustration requests.
- **ComfyUI (`comfyui_generate`)**: Use when the user explicitly asks for local GPU generation, ComfyUI, a specific local checkpoint/LoRA workflow, or calls a workflow by name.
- **Status check (`comfyui_status`)**: Use when the user asks if their PC/ComfyUI is online, wants to check GPU VRAM, or wants to see available workflows.

## Calling `comfyui_generate`

- Pass `prompt` in English matching the workflow's checkpoint style (Danbooru tags for SDXL/Illustrious/Pony, natural language for Flux/Qwen-Image).
- **Preserve workflow defaults**: Only pass `negative_prompt`, `aspect_ratio`/`width`/`height`, `steps`, `cfg`, or `seed` when the user asks to override them. Leaving them omitted preserves the tuned defaults inside the exported workflow JSON.
- **Batch generation**: Pass `count` (1–8) to run the same prompt sequentially with distinct seeds (increments by +1 when a fixed `seed` is given) without increasing GPU VRAM usage.
- If the user doesn't specify a workflow name and multiple workflows exist, call `comfyui_status` first or omit `workflow` to use the configured default.
- **Mandatory Telegram delivery rule**: When `comfyui_generate` succeeds, ALWAYS include every `MEDIA:/absolute/path/to/image.png` line from `media_tag` / `media_tags` on its own line in your final reply so Telegram sends all generated images.
- If ComfyUI is offline, tell the user their local ComfyUI/Tailscale node is unreachable and offer to generate with NovelAI instead.

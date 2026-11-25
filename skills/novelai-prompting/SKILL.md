---
name: novelai-prompting
description: Guide for generating high-quality anime and illustration images using the NovelAI plugin (NAI Diffusion 5 / 4.5 / 4 / 3), including Danbooru tag craft, multi-character prompts, img2img, Precise Character/Style Reference, and Vibe Transfer.
---

# NovelAI Prompting & Generation Guide

## Choosing the Right Tool

1. **Quick everyday image (`image_generate`)**:
   - Use for simple text-to-image requests where default V5 Full settings (`nai-diffusion-5-full`, steps=23, scale=7.0, `k_euler_ancestral`, `karras`, `cfg_rescale=0.0`) and standard aspect ratios (`portrait`, `landscape`, `square`) are enough.
   - Telegram delivers the output image automatically.

2. **Full control (`novelai_generate`)**:
   - Use whenever the user specifies or benefits from:
     - Multiple distinct characters with separate appearances or positions (`characters`)
     - Custom negative prompts (`negative_prompt`, `uc_preset`)
     - Fixed seed replay (`seed`), custom dimensions (`width`, `height`), `steps`, `scale`, `cfg_rescale`, `sampler`, or `variety_boost`
     - Image-to-image editing with controlled `strength` / `noise` (`source_image`)
     - V5 / V4.5 Precise Reference for keeping a character's identity or art style (`character_references`)
     - Vibe Transfer (`vibe_references`)
   - **Mandatory Telegram delivery rule**: When `novelai_generate` succeeds, always include its `media_tag` (`MEDIA:/absolute/path/to/image.png`) on its own line in your reply.

3. **Account balance (`novelai_status`)**:
   - Use when the user asks about their NovelAI tier or remaining Anlas.

## Prompt Craft for NAI Diffusion 5 / 4.5

- **Language**: Always translate Chinese or other requests into English tags + concise natural English scene phrasing.
- **Structure**:
  1. Subject count & gender: `1girl, solo` or `2girls` (with `characters` list for multi-character scenes).
  2. Character traits (when single-character): hair/eyes, outfit, expression, pose.
  3. Scene & composition: setting, camera framing (`upper body`, `cowboy shot`, `wide shot`, `dutch angle`), lighting (`golden hour`, `rim lighting`, `soft shadows`), atmosphere.
  4. Style cues (only when requested): e.g. `painterly`, `cel shading`, `watercolor (medium)`, `anime coloring`.
- **Weighting syntax**:
  - V4.5 numeric emphasis: `1.2::silver hair::` (boost) or `0.7::background crowd::` (reduce).
  - Classic braces/brackets also work: `{tag}` (~1.05x), `[tag]` (~0.95x).
- **Avoid redundant quality spam**: `quality_tags: true` already appends NAI's recommended quality tags for the selected model.

## Multi-Character Layout (`characters`)

For 2+ characters on V4 / V4.5, put the global scene and count (`2girls, sunset rooftop, wind`) in `prompt`, and put each character's own appearance/outfit/action in `characters`:
- Omit `center` to let the model auto-compose naturally (`use_coords: false`).
- Provide `center: {x, y}` (`x` left->right `0.15..0.85`, `y` top->bottom `0.2..0.8`) when the user specifies positions like "left girl / right boy".

## Opus Free-Tier Friendly Defaults

- Free unlimited generations on Opus apply when `width * height <= 1,048,576` (`832x1216`, `1216x832`, `1024x1024`) and `steps <= 28` (and without paid extras like large canvases or new vibe encodings).
- Default to `portrait` (`832x1216`) for characters, `landscape` (`1216x832`) for scenes/multi-character, `square` (`1024x1024`) for avatars/icons.
- Always report the `seed` briefly if the user might want to iterate on the image.

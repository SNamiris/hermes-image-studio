---
name: prompt-craft
description: Roll anime illustration prompts from local wildcard pools, refine individual slots, and use artist presets and tag guides with NovelAI or ComfyUI.
---

# Prompt Craft

Use this skill for random image ideas, rolls from specific wildcard pools, artist presets, or tag guides.

Run `python3 "<skill_dir>/scripts/prompt_kit.py"` with the `skill_dir` returned by `skill_view`. The default install path is `~/.hermes/plugins/hermes-image-studio/skills/prompt-craft/scripts/prompt_kit.py`.

1. **List pools if needed.** Run `list` when the user's pool names are unclear or when they mention newly added files. Use `guides list` or `artists search --query <term>` to find a guide or preset.
2. **Roll the slots.** For a general roll, run `roll --target nai`. For specific pools, run `roll -f hair_eyes,outfit -f accessories:2,scene --target nai` with the requested pool names. Use `--target comfyui` for ComfyUI. Use `--lock 'slot=value'` for fixed requirements, `--exclude slot1,slot2` to skip slots, and `--with-artist` when the user asks for a preset. Keep `roll_seed` for replay and read any `warnings` before using the draft.
3. **Refine the draft.** Edit the slots the user asked to change and keep the other rolled values. Make the smallest adjustment needed to resolve conflicts, such as replacing an aerial shot with a wide interior shot for a café. Resolve any outstanding wildcard references before generation. For tag order and emphasis, load `references/tag-guide.md` using `skill_view(name="hermes-image-studio:prompt-craft", file_path="references/tag-guide.md")`. For artist preset fields, consult `references/artist-guide.md`. Use `guides show <name>` for personal guides.
4. **Generate and report.** For a request to make an image, pass the refined prompt to `novelai_generate`, or to `comfyui_generate` for a requested ComfyUI workflow. Report the recipe or selected pools, the main rolled and edited slots, the roll seed, and the image seed returned by the backend. In Telegram, put every returned `MEDIA:/absolute/path/to/image.png` on its own line. For a request for prompt ideas, return the refined prompt and roll seed.

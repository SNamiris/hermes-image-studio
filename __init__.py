"""Hermes plugin entry point for the image studio."""

from pathlib import Path

import yaml


def register(ctx) -> None:
    if __package__:
        from .plugins.image_gen import comfyui, novelai
    else:
        from plugins.image_gen import comfyui, novelai

    novelai.register(ctx)
    comfyui.register(ctx)

    if hasattr(ctx, "register_skill"):
        skills_dir = Path(__file__).resolve().parent / "skills"
        for name in ("prompt-craft", "novelai-prompting", "comfyui-workflow"):
            skill_md = skills_dir / name / "SKILL.md"
            document = skill_md.read_text(encoding="utf-8")
            frontmatter = document.removeprefix("---\n").split("\n---\n", 1)[0]
            ctx.register_skill(name, skill_md, description=yaml.safe_load(frontmatter)["description"])

    if hasattr(ctx, "register_system_prompt_section"):
        ctx.register_system_prompt_section(
            id="prompt_craft_guidance",
            content=(
                "For random image ideas, rolls from wildcard files, artist presets, or tag guides, "
                "load hermes-image-studio:prompt-craft and run its scripts/prompt_kit.py."
            ),
            position="after_memory",
        )

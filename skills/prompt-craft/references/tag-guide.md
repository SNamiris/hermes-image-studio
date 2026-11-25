# Tag guide

For NovelAI illustrations, start with the subject count and character traits, then add clothing, pose and expression. Follow with location, lighting and framing. Add style cues that fit the request. For a multi-character NovelAI prompt, keep shared scene cues in the base prompt and place appearance and clothing details in the individual character prompts.

- NovelAI numeric emphasis uses `1.2::silver hair::`. NovelAI also supports `{tag}` and `[tag]` for emphasis. The wildcard parser treats a brace group containing `|` as a choice.
- ComfyUI weighted syntax uses `(silver hair:1.2)` with compatible text encoders. Follow the selected workflow's conventions for tag lists or natural language.
- Check for incompatible directions, crops or lighting before sending the prompt. Use a single cue where multiple tags describe the same feature.
- When NovelAI's `quality_tags` is enabled, it appends model-specific quality tags. Reserve the prompt for subject, composition and style.

Keep personal tag collections in `~/painting/guides/` and open them with `guides show <name>`.

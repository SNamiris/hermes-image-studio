# Artist presets

Put preset files in `~/painting/artists/`. Each preset needs an `id` and `prompt`. The `name`, `styles`, `engines`, `negative_prompt`, and `notes` fields are optional.

```yaml
artists:
  - id: warm_painterly
    name: Warm painterly illustration
    styles: [painterly, warm]
    engines: [nai-v5, nai-v4.5]
    prompt: "artist:your_artist_tag, 0.8::artist:your_second_tag::"
    negative_prompt: ""
    notes: Use with soft window light and portraits.
```

Use the prompt kit to find and apply presets.

```text
artists list --engine nai
artists search --style painterly --query warm
artists roll --engine nai-v5
roll --with-artist --artist-style painterly --target nai
roll --artist-id warm_painterly --target nai
```

The roll appends the selected positive prompt to `draft_prompt` and includes the full preset in `artist`. Review an optional `negative_prompt` against the image request before passing it to the backend.

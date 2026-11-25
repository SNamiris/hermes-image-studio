# Wildcard workflow

Run these subcommands with `python3 <skill_dir>/scripts/prompt_kit.py`.

```text
list --kind wildcards
roll --target nai --seed 42
roll --recipe scene_cinematic --count 2 --target comfyui
roll -f hair_eyes.txt -f "outfit/*,accessories:2,scene" --target nai
roll -f hair_eyes,accessories:2 --lock "scene=snowy night shrine" --exclude expression
```

Globs add each matching pool in sorted order within that selector. A per-file count samples entries without replacement. If a pool has too few eligible entries, the roll returns the available entries with a warning. Slot order comes from the recipe or the order of the selectors. An excluded slot is omitted even when a lock is supplied.

Suppose `hair_eyes` rolled silver hair and amber eyes, `scene` rolled an outdoor market, `lighting` rolled overcast light, and `camera` rolled an aerial wide shot. If the user asks for black hair inside a café, update the hair and scene, keep the amber eyes and overcast light, and adjust the camera to a wide interior shot. The roll seed replays the original slot selection. The image seed is reported by the generator.

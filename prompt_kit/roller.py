"""Roll ordered slots from a recipe, the top-level pools, or explicit selectors."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from random import Random, SystemRandom

from .catalog import find_artists, load_recipe, pick_artist
from .parser import Entry, expand_entry, pick_index, read_entries
from .paths import Pool, discover_pools, resolve_within, select_pools
from .target_adapter import adapt_prompt


@dataclass(frozen=True)
class Slot:
    name: str
    pool: Pool
    count: int = 1


def _file_slots(data_dir: Path, pools: list[Pool], files: list[str]) -> list[Slot]:
    selections = {}
    for spec in files:
        selector, colon, picks = spec.rpartition(":")
        selector, count = (selector, int(picks)) if colon and picks.lstrip("+-").isdecimal() else (spec, 1)
        if count < 1:
            raise ValueError(f"Pick count must be positive in {spec!r}")
        for pool in select_pools(data_dir, pools, selector):
            selections[pool] = count
    return _pool_slots(selections)


def _pool_slots(selections: dict[Pool, int]) -> list[Slot]:
    counts = Counter(pool.name for pool in selections)
    return [
        Slot(pool.name if counts[pool.name] == 1 else pool.filename, pool, count)
        for pool, count in selections.items()
    ]


def _recipe_slots(data_dir: Path, pools: list[Pool], slots: dict) -> list[Slot]:
    result = []
    for name, spec in slots.items():
        if isinstance(spec, str):
            selector, count = spec, 1
        elif isinstance(spec, dict) and "pool" in spec:
            selector, count = spec["pool"], int(spec.get("count", 1))
        else:
            raise ValueError(f"Recipe slot {name!r} needs a pool name or a mapping with 'pool' and optional 'count'")
        matches = select_pools(data_dir, pools, selector)
        if len(matches) != 1 or count < 1:
            raise ValueError(f"Recipe slot {name!r} needs one wildcard pool and a positive pick count")
        result.append(Slot(name, matches[0], count))
    return result


def _roll_slot(slot: Slot, entries: list[Entry], rng: Random, load_nested, warnings: list[str]) -> str:
    remaining = entries.copy()
    selected = []
    for _ in range(min(slot.count, len(remaining))):
        entry = remaining.pop(pick_index(remaining, rng))
        selected.append(expand_entry(entry.text, rng, load_nested, warnings))
    if len(selected) < slot.count:
        warnings.append(f"Pool {slot.pool.filename!r} has {len(selected)} eligible entries for {slot.count} picks")
    return ", ".join(selected)


def roll(
    data_dir: Path,
    *,
    recipe: str = "default",
    files: list[str] | None = None,
    count: int = 1,
    seed: int | None = None,
    locks: dict[str, str] | None = None,
    exclude: set[str] | None = None,
    with_artist: bool = False,
    artist_style: str | None = None,
    artist_id: str | None = None,
    target: str = "raw",
) -> dict:
    if not 1 <= count <= 10:
        raise ValueError("Roll count must be between 1 and 10")
    locks, exclude = locks or {}, exclude or set()
    pools = discover_pools(data_dir)
    selected_recipe = None
    if files:
        mode, slots = "files", _file_slots(data_dir, pools, files)
    else:
        recipe_data = load_recipe(data_dir, recipe)
        if recipe_data is not None:
            mode, slots = "recipe", _recipe_slots(data_dir, pools, recipe_data["slots"])
            selected_recipe = recipe
        elif recipe == "default":
            mode = "auto"
            slots = _pool_slots({pool: 1 for pool in pools if "/" not in pool.filename})
        else:
            raise ValueError(f"Recipe {recipe!r} was not found under recipes/")

    warnings = []
    if not slots and not locks:
        warnings.append("No wildcard slots found. Add pools under wildcards/ or run init.")
    use_artist = with_artist or artist_style is not None or artist_id is not None
    artists = find_artists(
        data_dir, style=artist_style, engine=None if target == "raw" else target, artist_id=artist_id,
    ) if use_artist else []
    cache = {}

    def load_entries(pool: Pool) -> list[Entry]:
        if pool not in cache:
            cache[pool] = read_entries(resolve_within(data_dir, pool.relative_path))
        return cache[pool]

    def load_nested(selector: str) -> list[Entry]:
        matches = select_pools(data_dir, pools, selector)
        if len(matches) != 1:
            raise ValueError("A nested reference needs exactly one wildcard pool")
        return load_entries(matches[0])

    roll_seed = seed if seed is not None else SystemRandom().getrandbits(32)
    seed_rng = Random(roll_seed)
    results = []
    for index in range(count):
        item_seed = roll_seed if index == 0 else seed_rng.getrandbits(32)
        rng = Random(item_seed)
        values, sources = {}, {}
        for slot in slots:
            # A slot's draws stay stable when another slot is locked or excluded.
            slot_seed = rng.getrandbits(64)
            if slot.name in exclude:
                continue
            if slot.name in locks:
                values[slot.name] = locks[slot.name]
                sources[slot.name] = None
            else:
                values[slot.name] = _roll_slot(slot, load_entries(slot.pool), Random(slot_seed), load_nested, warnings)
                sources[slot.name] = slot.pool.relative_path
        for name, value in locks.items():
            if name not in exclude and name not in values:
                values[name], sources[name] = value, None

        values = {name: adapt_prompt(value, target) for name, value in values.items()}
        artist = pick_artist(artists, rng, warnings) if use_artist else None
        parts = list(values.values())
        if artist:
            parts.append(adapt_prompt(artist["prompt"], target))
        results.append({
            "index": index,
            "seed": item_seed,
            "slots": values,
            "sources": sources,
            "artist": artist,
            "draft_prompt": ", ".join(part for part in parts if part),
        })
    return {
        "ok": True,
        "mode": mode,
        "recipe": selected_recipe,
        "target": target,
        "data_dir": str(data_dir),
        "roll_seed": roll_seed,
        "requested_files": files or [],
        "results": results,
        "warnings": list(dict.fromkeys(warnings)),
    }

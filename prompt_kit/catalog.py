"""List local assets, find artist presets, and copy the seed library."""

from pathlib import Path
from random import Random
import shutil

import yaml

from .parser import read_entries
from .paths import REPO_ROOT, YAML_EXTENSIONS, discover_pools, resolve_within


REFERENCES = REPO_ROOT / "skills" / "prompt-craft" / "references"
SEED_LIBRARY = REPO_ROOT / "assets" / "painting_seed"
KINDS = ("wildcards", "recipes", "artists", "guides")


def _files(data_dir: Path, folder: str, extensions: tuple[str, ...]) -> list[Path]:
    directory = resolve_within(data_dir, folder)
    return [
        path for path in sorted(directory.iterdir())
        if path.suffix.lower() in extensions and path.is_file()
    ] if directory.is_dir() else []


def read_recipe(data_dir: Path, path: Path) -> dict:
    recipe = yaml.safe_load(resolve_within(data_dir, path).read_text(encoding="utf-8-sig"))
    if not isinstance(recipe, dict) or not isinstance(recipe.get("slots"), dict):
        raise ValueError(f"Recipe {path.name!r} needs a 'slots' mapping")
    return recipe


def load_recipe(data_dir: Path, name: str) -> dict | None:
    path = Path("recipes") / name
    candidates = [path] if path.suffix.lower() in YAML_EXTENSIONS else [
        path.parent / (path.name + suffix) for suffix in YAML_EXTENSIONS
    ]
    for candidate in candidates:
        resolved = resolve_within(data_dir, candidate)
        if resolved.is_file():
            return read_recipe(data_dir, resolved)
    return None


def find_artists(
    data_dir: Path,
    *,
    style: str | None = None,
    engine: str | None = None,
    query: str | None = None,
    artist_id: str | None = None,
) -> list[dict]:
    artists = []
    for path in _files(data_dir, "artists", (*YAML_EXTENSIONS, ".json")):
        document = yaml.safe_load(resolve_within(data_dir, path).read_text(encoding="utf-8-sig"))
        entries = document.get("artists", []) if isinstance(document, dict) else document or []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("id") or not entry.get("prompt"):
                raise ValueError(f"Each artist preset in {path.name!r} needs an 'id' and a 'prompt'")
            styles = entry.get("styles") or []
            engines = entry.get("engines") or []
            if artist_id and entry["id"] != artist_id:
                continue
            if style and style.casefold() not in {value.casefold() for value in styles}:
                continue
            if engine and engines and not any(_matches_engine(engine, value) for value in engines):
                continue
            if query and not any(query.casefold() in str(value).casefold() for value in entry.values()):
                continue
            artists.append(entry)
    return artists


def _matches_engine(engine: str, preset_engine: str) -> bool:
    engine, preset_engine = engine.casefold(), preset_engine.casefold()
    return (
        engine == preset_engine
        or preset_engine.startswith(engine + "-")
        or engine.startswith(preset_engine + "-")
    )


def pick_artist(artists: list[dict], rng: Random, warnings: list[str]) -> dict | None:
    if artists:
        return rng.choice(artists)
    warnings.append("No matching artist presets. Add presets under artists/ or try different filters.")
    return None


def _guide_paths(data_dir: Path) -> dict[str, tuple[Path, str]]:
    guides = {path.stem: (path, "bundled") for path in REFERENCES.glob("*.md")}
    for path in _files(data_dir, "guides", (".md",)):
        guides[path.stem] = (resolve_within(data_dir, path), "user")
    return dict(sorted(guides.items()))


def guide_list(data_dir: Path) -> list[dict]:
    return [
        {"name": name, "source": source, "path": str(path)}
        for name, (path, source) in _guide_paths(data_dir).items()
    ]


def show_guide(data_dir: Path, name: str) -> dict:
    guides = _guide_paths(data_dir)
    requested = Path(name)
    resolve_within(data_dir, Path("guides") / requested)
    if requested.suffix.lower() == ".md":
        name = str(requested.with_suffix(""))
    if name not in guides:
        raise ValueError(f"Guide {name!r} was not found. Available guides: {', '.join(guides)}")
    path, source = guides[name]
    return {"name": name, "source": source, "path": str(path), "content": path.read_text(encoding="utf-8-sig")}


def list_catalog(data_dir: Path, kind: str) -> dict:
    result = {}
    if kind in ("all", "wildcards"):
        pools = discover_pools(data_dir)
        result["wildcards"] = [
            {
                "name": pool.name,
                "rel_path": pool.relative_path,
                "entry_count": len(read_entries(resolve_within(data_dir, pool.relative_path))),
                "format": "txt" if pool.filename.lower().endswith(".txt") else "yaml",
            }
            for pool in pools
        ]
    if kind in ("all", "recipes"):
        result["recipes"] = []
        for path in _files(data_dir, "recipes", YAML_EXTENSIONS):
            recipe = read_recipe(data_dir, path)
            result["recipes"].append({
                "name": path.stem,
                "description": recipe.get("description", ""),
                "slots": list(recipe["slots"]),
            })
    if kind in ("all", "artists"):
        artists = find_artists(data_dir)
        styles = sorted({style for artist in artists for style in artist.get("styles") or []})
        result["artists"] = {"count": len(artists), "styles": styles}
    if kind in ("all", "guides"):
        result["guides"] = guide_list(data_dir)
    return result


def init_library(data_dir: Path, overwrite: bool) -> dict:
    copied, skipped = [], []
    for source in sorted(SEED_LIBRARY.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(SEED_LIBRARY)
        destination = resolve_within(data_dir, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with source.open("rb") as seed, destination.open("wb" if overwrite else "xb") as target:
                shutil.copyfileobj(seed, target)
        except FileExistsError:
            skipped.append(relative.as_posix())
        else:
            copied.append(relative.as_posix())
    return {"copied": copied, "skipped": skipped}

"""Command-line entry for the prompt kit."""

import argparse
import json
from random import Random
import sys

import yaml

from .catalog import KINDS, find_artists, guide_list, init_library, list_catalog, pick_artist, show_guide
from .paths import get_data_dir
from .roller import roll
from .target_adapter import TARGETS


def _data_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", default=argparse.SUPPRESS, help="Painting data directory")


def _command(subparsers, name: str, help_text: str, *, group: bool = False) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name, help=help_text)
    _data_arg(parser)
    if not group:
        parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Roll and inspect local painting prompts.")
    _data_arg(parser)
    commands = parser.add_subparsers(dest="command", required=True)

    listing = _command(commands, "list", "List painting assets")
    listing.add_argument("--kind", choices=("all", *KINDS), default="all")

    rolling = _command(commands, "roll", "Roll prompt slots")
    rolling.add_argument("-f", "--files", action="append", help="Pool selectors, comma-separated or repeated")
    rolling.add_argument("--recipe", default="default")
    rolling.add_argument("--count", type=int, choices=range(1, 11), default=1)
    rolling.add_argument("--seed", type=int)
    rolling.add_argument("--lock", action="append", default=[], metavar="SLOT=VALUE")
    rolling.add_argument("--exclude", action="append", metavar="SLOT[,SLOT]")
    rolling.add_argument("--with-artist", action="store_true")
    rolling.add_argument("--artist-style")
    rolling.add_argument("--artist-id")
    rolling.add_argument("--target", choices=TARGETS, default="raw")

    artists = _command(commands, "artists", "Browse and sample artist presets", group=True)
    artist_commands = artists.add_subparsers(dest="action", required=True)
    for action in ("list", "search", "roll"):
        artist_command = _command(artist_commands, action, f"{action.capitalize()} artist presets")
        artist_command.add_argument("--style")
        artist_command.add_argument("--engine")
        artist_command.add_argument("--query")

    guides = _command(commands, "guides", "Find tag and workflow guides", group=True)
    guide_commands = guides.add_subparsers(dest="action", required=True)
    _command(guide_commands, "list", "List guides")
    show = _command(guide_commands, "show", "Read a guide")
    show.add_argument("name")

    init = _command(commands, "init", "Copy the bundled seed library")
    init.add_argument("--overwrite", action="store_true", help="Replace existing files with bundled versions")
    return parser


def _csv(values: list[str] | None) -> list[str]:
    return [item.strip() for value in values or [] for item in value.split(",") if item.strip()]


def _locks(items: list[str]) -> dict[str, str]:
    locks = {}
    for item in items:
        slot, equals, value = item.partition("=")
        if not equals or not slot.strip():
            raise ValueError(f"Invalid lock {item!r}. Use --lock slot=value.")
        locks[slot.strip()] = value.strip()
    return locks


def _run(args: argparse.Namespace) -> dict:
    data_dir = get_data_dir(getattr(args, "data_dir", None))
    result = {"ok": True, "data_dir": str(data_dir)}
    if args.command == "roll":
        files = _csv(args.files)
        if args.files and not files:
            raise ValueError("Supply at least one pool selector with --files")
        return roll(
            data_dir, recipe=args.recipe, files=files, count=args.count, seed=args.seed, locks=_locks(args.lock),
            exclude=set(_csv(args.exclude)), with_artist=args.with_artist, artist_style=args.artist_style,
            artist_id=args.artist_id, target=args.target,
        )
    if args.command == "list":
        result.update(list_catalog(data_dir, args.kind))
    elif args.command == "artists":
        artists = find_artists(data_dir, style=args.style, engine=args.engine, query=args.query)
        if args.action == "roll":
            result["warnings"] = []
            result["artist"] = pick_artist(artists, Random(), result["warnings"])
        else:
            result["artists"] = artists
    elif args.command == "guides":
        if args.action == "show":
            result["guide"] = show_guide(data_dir, args.name)
        else:
            result["guides"] = guide_list(data_dir)
    else:
        result.update(init_library(data_dir, args.overwrite))
    return result


def _print_text(result: dict) -> None:
    if "results" in result:
        print(f"Mode: {result['mode']} | Roll seed: {result['roll_seed']}")
        for item in result["results"]:
            print(f"[{item['index']}] Seed {item['seed']}: {item['draft_prompt']}")
    elif "guide" in result:
        print(result["guide"]["content"], end="" if result["guide"]["content"].endswith("\n") else "\n")
    else:
        print(f"Data directory: {result['data_dir']}")
        for key, value in result.items():
            if key not in ("ok", "data_dir", "warnings"):
                print(f"{key.capitalize()}:")
                items = value if isinstance(value, list) else [value]
                for item in items:
                    print("  " + (json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)))
                if not items:
                    print("  (none)")
    for warning in result.get("warnings", []):
        print(f"Warning: {warning}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        if args.format == "json":
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_text(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

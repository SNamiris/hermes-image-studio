"""Parse wildcard pools and expand selected entries."""

from dataclasses import dataclass
from pathlib import Path
from random import Random
import re
from typing import Callable, Iterator

import yaml


_WEIGHT = re.compile(r"^(?:w=)?(\d+(?:\.\d+)?)::(.+)$")
_NAI_EMPHASIS_PREFIX = re.compile(r"^\d+(?:\.\d+)?::[^:]+::(?=$|[\s,}\]])")
_CHOICE_TOKEN = re.compile(r"[{}|]")
_REFERENCE = re.compile(r"__(.+?)__")


@dataclass(frozen=True)
class Entry:
    text: str
    weight: float = 1.0


def parse_entry(text: str) -> Entry:
    text = text.strip()
    match = _WEIGHT.match(text)
    if match:
        body = match[2].strip()
        is_nai_prefix = bool(_NAI_EMPHASIS_PREFIX.match(text)) or (
            text.endswith("::") and not _WEIGHT.match(body)
        )
        if text.startswith("w=") or not is_nai_prefix:
            return Entry(body, float(match[1]))
    return Entry(text)


def _yaml_entries(value) -> Iterator[str]:
    if isinstance(value, dict):
        value = value.values()
    elif value is None:
        return
    elif not isinstance(value, list):
        yield str(value)
        return
    for item in value:
        yield from _yaml_entries(item)


def read_entries(path: Path) -> list[Entry]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines() if path.suffix.lower() == ".txt" else _yaml_entries(yaml.safe_load(text))
    entries = (parse_entry(line) for line in lines if line.strip() and not line.lstrip().startswith("#"))
    return [entry for entry in entries if entry.weight > 0]


def pick_index(entries: list[Entry], rng: Random) -> int:
    return rng.choices(range(len(entries)), weights=[entry.weight for entry in entries])[0]


def expand_choices(text: str, rng: Random) -> str:
    """Split only at the current brace level, then expand the selected branch."""
    depth = 0
    cursor = 0
    parts = []
    for match in _CHOICE_TOKEN.finditer(text):
        index = match.start()
        if match[0] == "{":
            if depth == 0:
                start = index
                splits = [start]
            depth += 1
        elif depth == 1 and match[0] == "|":
            splits.append(index)
        elif depth and match[0] == "}":
            depth -= 1
            if depth:
                continue
            parts.append(text[cursor:start])
            if len(splits) == 1:
                parts.extend(("{", expand_choices(text[start + 1:index], rng), "}"))
            else:
                options = [
                    parse_entry(text[left + 1:right])
                    for left, right in zip(splits, splits[1:] + [index])
                ]
                eligible = [option for option in options if option.weight > 0]
                choice = eligible[pick_index(eligible, rng)].text if eligible else text[start:index + 1]
                parts.append(expand_choices(choice, rng) if eligible else choice)
            cursor = index + 1
    parts.append(text[cursor:])
    return "".join(parts)


def expand_entry(
    text: str,
    rng: Random,
    load_pool: Callable[[str], list[Entry]],
    warnings: list[str],
    *,
    max_depth: int = 8,
) -> str:
    def expand(value: str, depth: int) -> str:
        def replace(match: re.Match) -> str:
            name = match[1]
            if depth >= max_depth:
                warnings.append(f"Wildcard reference {name!r} reached the maximum depth ({max_depth})")
                return match[0]
            try:
                entries = load_pool(name)
            except ValueError as exc:
                warnings.append(f"Nested wildcard {name!r}: {exc}")
                return match[0]
            if not entries:
                warnings.append(f"Nested wildcard {name!r} has no eligible entries")
                return match[0]
            return expand(entries[pick_index(entries, rng)].text, depth + 1)

        return _REFERENCE.sub(replace, expand_choices(value, rng))

    return expand(text, 0)

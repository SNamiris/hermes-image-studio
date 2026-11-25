"""Locate painting data and resolve wildcard selectors."""

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
WILDCARD_EXTENSIONS = (".txt", ".yaml", ".yml")
YAML_EXTENSIONS = (".yaml", ".yml")


def get_data_dir(value: str | Path | None = None) -> Path:
    return Path(value or os.getenv("HERMES_PAINTING_DIR") or "~/painting").expanduser().resolve()


def resolve_within(base: Path, path: str | Path) -> Path:
    base = base.resolve()
    resolved = (base / path).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"Path {str(path)!r} is outside the data directory {base}")
    return resolved


@dataclass(frozen=True)
class Pool:
    relative_path: str
    filename: str

    @property
    def name(self) -> str:
        return str(PurePosixPath(self.filename).with_suffix(""))


def discover_pools(data_dir: Path) -> list[Pool]:
    wildcards = data_dir / "wildcards"
    pools = {}
    for folder, pattern in ((data_dir, "*"), (wildcards, "**/*")):
        resolve_within(data_dir, folder)
        for path in sorted(folder.glob(pattern)):
            if path.suffix.lower() in WILDCARD_EXTENSIONS and path.is_file():
                filename = path.relative_to(folder).as_posix()
                pools[filename] = Pool(path.relative_to(data_dir).as_posix(), filename)
    return sorted(pools.values(), key=lambda pool: pool.filename)


def select_pools(data_dir: Path, pools: list[Pool], selector: str) -> list[Pool]:
    selector = selector.strip().replace("\\", "/")
    path = Path(selector)
    wildcard = re.search(r"[*?\[]", selector)
    if wildcard:
        if ".." in path.parts:
            raise ValueError(f"Parent paths are not supported in wildcard patterns: {selector!r}")
        literal = selector[:wildcard.start()]
        resolve_within(data_dir, literal if literal.endswith("/") else Path(literal).parent)
        filename = path.as_posix()
    else:
        resolved = resolve_within(data_dir, path if path.is_absolute() or ".." in path.parts else path.parent)
        filename = (resolved.relative_to(data_dir.resolve()) if path.is_absolute() else path).as_posix()
    if filename.startswith("wildcards/"):
        pools = [pool for pool in pools if pool.relative_path.startswith("wildcards/")]
        filename = filename.removeprefix("wildcards/")
    elif path.is_absolute():
        pools = [pool for pool in pools if pool.relative_path == pool.filename]

    if wildcard:
        pattern = PurePosixPath(filename)
        matches = [
            pool for pool in pools
            if len(PurePosixPath(pool.filename).parts) == len(pattern.parts)
            and PurePosixPath(pool.filename).match(filename)
        ]
        if matches:
            return matches
    else:
        exact = [pool for pool in pools if pool.filename == filename]
        if exact:
            return exact
        matches = [pool for pool in pools if pool.name == filename]
        if not matches and "/" not in filename:
            matches = [
                pool for pool in pools
                if filename in (PurePosixPath(pool.name).name, PurePosixPath(pool.filename).name)
            ]
        if len(matches) == 1:
            return matches
        if matches:
            choices = ", ".join(pool.filename for pool in matches)
            raise ValueError(f"Ambiguous wildcard pool {selector!r}. Matches: {choices}. {available_pools(pools)}")
        children = [pool for pool in pools if PurePosixPath(pool.filename).parent.as_posix() == filename]
        if children:
            return children

    raise ValueError(f"Wildcard pool {selector!r} was not found. {available_pools(pools)}")


def available_pools(pools: list[Pool]) -> str:
    return "Available pools: " + (", ".join(pool.filename for pool in pools) or "(none)")

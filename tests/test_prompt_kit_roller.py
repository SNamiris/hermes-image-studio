from pathlib import Path

import pytest

from prompt_kit.paths import resolve_within
from prompt_kit.roller import roll


def write(root: Path, name: str, text: str):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def data_dir(tmp_path):
    write(tmp_path, "wildcards/hair_eyes.txt", "1.2::silver hair::")
    write(tmp_path, "hair_eyes.txt", "shadowed root hair pool")
    write(tmp_path, "wildcards/outfit/casual.txt", "{knit sweater|0::hoodie}")
    write(tmp_path, "wildcards/outfit/winter.yml", "coats: [puffer jacket]")
    write(tmp_path, "wildcards/layers/winter.txt", "scarf")
    write(tmp_path, "wildcards/accessories.txt", "glasses\nribbon\npin")
    write(tmp_path, "scene.yaml", "- moonlit forest")
    return tmp_path


def test_default_recipe_preserves_slot_order_and_counts(data_dir):
    write(data_dir, "recipes/default.yaml", (
        "description: test recipe\nslots:\n  scene: scene\n"
        "  details: {pool: accessories, count: 2}\n  clothing: outfit/casual\n"
    ))
    result = roll(data_dir, seed=17)
    assert (result["mode"], result["recipe"], result["requested_files"]) == ("recipe", "default", [])
    item = result["results"][0]
    assert list(item["slots"]) == ["scene", "details", "clothing"]
    assert item["slots"]["clothing"] == "knit sweater"
    assert len(set(item["slots"]["details"].split(", "))) == 2
    assert item["sources"]["details"] == "wildcards/accessories.txt"


def test_yml_recipe_and_missing_named_recipe(data_dir):
    write(data_dir, "recipes/evening.yml", "slots: {scene: scene}")
    assert roll(data_dir, recipe="evening", seed=17)["recipe"] == "evening"
    with pytest.raises(ValueError, match="Recipe.*was not found"):
        roll(data_dir, recipe="unknown")


def test_auto_fallback_uses_top_level_pools_and_prefers_wildcards(data_dir):
    result = roll(data_dir, seed=42)
    assert (result["mode"], result["recipe"]) == ("auto", None)
    item = result["results"][0]
    assert list(item["slots"]) == ["accessories", "hair_eyes", "scene"]
    assert item["slots"]["hair_eyes"] == "1.2::silver hair::"
    assert item["sources"]["hair_eyes"] == "wildcards/hair_eyes.txt"
    assert item["sources"]["scene"] == "scene.yaml"


def test_explicit_order_glob_output_and_per_file_count(data_dir):
    result = roll(data_dir, files=["hair_eyes.txt", "outfit/*", "accessories:2", "scene"], seed=9)
    assert result["mode"] == "files"
    assert result["requested_files"] == ["hair_eyes.txt", "outfit/*", "accessories:2", "scene"]
    item = result["results"][0]
    assert list(item["slots"]) == ["hair_eyes", "outfit/casual", "outfit/winter", "accessories", "scene"]
    assert len(set(item["slots"]["accessories"].split(", "))) == 2
    assert item["slots"]["outfit/winter"] == "puffer jacket"
    assert not result["warnings"]


def test_nested_file_references_reuse_pool_selection(data_dir):
    write(data_dir, "wildcards/mix.txt", "wearing __outfit/casual__ in __scene__")
    item = roll(data_dir, files=["mix"], seed=2)["results"][0]
    assert item["draft_prompt"] == "wearing knit sweater in moonlit forest"


def test_single_pool_stem_lookup_and_clear_errors(data_dir):
    assert roll(data_dir, files=["casual"], seed=1)["results"][0]["slots"] == {"outfit/casual": "knit sweater"}
    with pytest.raises(ValueError, match=r"Ambiguous.*layers/winter.txt.*outfit/winter.yml.*Available pools"):
        roll(data_dir, files=["winter"])
    with pytest.raises(ValueError, match=r"not found.*Available pools:.*outfit/casual.txt"):
        roll(data_dir, files=["missing"])
    with pytest.raises(ValueError, match="Pick count must be positive"):
        roll(data_dir, files=["scene:0"])


def test_insufficient_entries_warn_and_return_available_values(data_dir):
    result = roll(data_dir, files=["scene:3"], seed=2)
    assert result["results"][0]["slots"] == {"scene": "moonlit forest"}
    assert result["warnings"] == ["Pool 'scene.yaml' has 1 eligible entries for 3 picks"]


def test_locks_exclusions_replay_and_target(data_dir):
    options = {
        "files": ["hair_eyes", "accessories", "scene"], "seed": 152, "count": 3,
        "locks": {"accessories": "satchel", "lighting": "(twilight:1.2)", "scene": "snow"},
        "exclude": {"scene"}, "target": "nai",
    }
    result = roll(data_dir, **options)
    assert roll(data_dir, **options) == result
    assert result["roll_seed"] == 152
    assert len({item["seed"] for item in result["results"]}) == 3
    for index, item in enumerate(result["results"]):
        assert item["index"] == index
        assert item["slots"] == {
            "hair_eyes": "1.2::silver hair::", "accessories": "satchel", "lighting": "1.2::twilight::",
        }
        assert list(item["slots"]) == ["hair_eyes", "accessories", "lighting"]
        assert item["sources"] == {"hair_eyes": "wildcards/hair_eyes.txt", "accessories": None, "lighting": None}
    with pytest.raises(ValueError, match="between 1 and 10"):
        roll(data_dir, count=11)


def test_random_seed_is_emitted_and_can_be_replayed(data_dir):
    result = roll(data_dir, count=2)
    assert result["results"][0]["seed"] == result["roll_seed"]
    assert roll(data_dir, count=2, seed=result["roll_seed"]) == result


def test_locks_and_exclusions_keep_the_other_rolls(data_dir):
    files = ["hair_eyes", "accessories:2", "scene"]
    baseline = roll(data_dir, files=files, seed=3)["results"][0]
    edited = roll(data_dir, files=files, seed=3, locks={"hair_eyes": "red hair"}, exclude={"scene"})["results"][0]
    assert edited["slots"] == {"hair_eyes": "red hair", "accessories": baseline["slots"]["accessories"]}


def test_path_escape_rejected_for_pool_recipe_and_nested_reference(data_dir):
    for selector in ("../outside.txt", str(data_dir.parent / "outside.txt")):
        with pytest.raises(ValueError, match="outside the data directory"):
            resolve_within(data_dir, selector)
        with pytest.raises(ValueError, match="outside the data directory"):
            roll(data_dir, files=[selector])
    with pytest.raises(ValueError, match="outside the data directory"):
        roll(data_dir, recipe="../../outside")
    write(data_dir, "wildcards/mix.txt", "__../outside__")
    result = roll(data_dir, files=["mix"], seed=1)
    assert "outside the data directory" in result["warnings"][0]

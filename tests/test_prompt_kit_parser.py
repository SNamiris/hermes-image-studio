from random import Random

import pytest

from prompt_kit.parser import Entry, expand_choices, expand_entry, parse_entry, read_entries
from prompt_kit.target_adapter import adapt_prompt


def test_text_weights_and_novelai_emphasis(tmp_path):
    pool = tmp_path / "hair.txt"
    pool.write_text(
        "\ufeff  # comment\n\n3::silver hair\nw=2.5::black hair\n"
        "1.2::violet eyes::\nblue hair # hue\n0::disabled\n",
        encoding="utf-8",
    )
    assert read_entries(pool) == [
        Entry("silver hair", 3),
        Entry("black hair", 2.5),
        Entry("1.2::violet eyes::"),
        Entry("blue hair # hue"),
    ]
    assert parse_entry("1.2::silver hair:: ") == Entry("1.2::silver hair::")
    assert parse_entry("1.2::silver hair::, blue eyes") == Entry("1.2::silver hair::, blue eyes")
    assert parse_entry("3::1.2::silver hair::, blue eyes") == Entry("1.2::silver hair::, blue eyes", 3)
    assert parse_entry("3::1.2::silver hair::") == Entry("1.2::silver hair::", 3)


@pytest.mark.parametrize("extension", ["yaml", "yml"])
def test_yaml_groups_are_flattened_in_order(tmp_path, extension):
    pool = tmp_path / f"outfit.{extension}"
    pool.write_text("casual:\n  - sweater\n  - 'w=2::jacket'\nformal:\n  day: [vest, suit]\n", encoding="utf-8")
    assert read_entries(pool) == [Entry("sweater"), Entry("jacket", 2), Entry("vest"), Entry("suit")]


def test_inline_choices_select_only_the_chosen_branch():
    assert expand_choices("{0::red|3::{blue|0::gold}} eyes, {silver hair}", Random(3)) == (
        "blue eyes, {silver hair}"
    )
    assert expand_choices("a {red|blue} scarf", Random(0)) == "a blue scarf"
    assert expand_choices("{light {0::red|blue}}", Random(0)) == "{light blue}"
    assert expand_choices("1.2::{red|0::blue}::", Random(3)) == "1.2::red::"


def test_nested_pool_expansion_and_missing_warning():
    pools = {
        "outfit/casual": [Entry("__fabric__ jacket")],
        "fabric": [Entry("{linen|0::wool}")],
    }

    def lookup(name):
        if name not in pools:
            raise ValueError("pool was not found")
        return pools[name]

    warnings = []
    assert expand_entry("wearing __outfit/casual__", Random(3), lookup, warnings) == "wearing linen jacket"
    assert warnings == []
    assert expand_entry("__missing__ nearby", Random(3), lookup, warnings) == "__missing__ nearby"
    assert "missing" in warnings[0] and "was not found" in warnings[0]


def test_nested_cycle_stops_after_eight_lookups():
    lookups = []

    def lookup(name):
        lookups.append(name)
        return [Entry("__cycle__")]

    warnings = []
    assert expand_entry("__cycle__", Random(0), lookup, warnings) == "__cycle__"
    assert lookups == ["cycle"] * 8
    assert "maximum depth (8)" in warnings[0]


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("raw", "1.2::silver hair::, (warm light:0.8), {glow}, [moon]"),
        ("nai", "1.2::silver hair::, 0.8::warm light::, {glow}, [moon]"),
        ("comfyui", "(silver hair:1.2), (warm light:0.8), {glow}, [moon]"),
    ],
)
def test_target_adapter(target, expected):
    prompt = "1.2::silver hair::, (warm light:0.8), {glow}, [moon]"
    assert adapt_prompt(prompt, target) == expected


def test_target_adapter_handles_parenthesized_tag():
    prompt = "1.2::watercolor (medium)::"
    assert adapt_prompt(prompt, "comfyui") == "(watercolor (medium):1.2)"
    assert adapt_prompt(adapt_prompt(prompt, "comfyui"), "nai") == prompt

import json
import subprocess
import sys

from prompt_kit.cli import main
from prompt_kit.paths import REPO_ROOT, get_data_dir


CLI_SCRIPT = REPO_ROOT / "skills" / "prompt-craft" / "scripts" / "prompt_kit.py"


def run_json(capsys, root, *args, status=0):
    assert main(["--data-dir", str(root), *args]) == status
    return json.loads(capsys.readouterr().out)


def test_wrapper_from_another_working_directory(tmp_path):
    output = subprocess.run(
        [sys.executable, "-B", str(CLI_SCRIPT), "roll", "--data-dir", str(tmp_path), "--seed", "8"],
        cwd=tmp_path, capture_output=True, check=True,
    )
    result = json.loads(output.stdout)
    assert result["data_dir"] == str(tmp_path.resolve())
    assert result["mode"] == "auto" and result["roll_seed"] == 8


def test_cli_files_combines_commas_and_repeated_flags(capsys, tmp_path):
    assert main(["init", "--data-dir", str(tmp_path)]) == 0
    capsys.readouterr()
    outfit = tmp_path / "wildcards" / "outfit"
    outfit.mkdir()
    (outfit / "casual.txt").write_text("sweater", encoding="utf-8")
    result = run_json(
        capsys, tmp_path, "roll", "-f", "hair_eyes.txt,scene", "--files", "outfit/casual,accessories:2",
        "--seed", "7", "--count", "2", "--lock", "lighting=twilight", "--lock", "scene=snowy shrine",
        "--exclude", "camera,expression", "--exclude", "lighting",
    )
    assert result["requested_files"] == ["hair_eyes.txt", "scene", "outfit/casual", "accessories:2"]
    assert len(result["results"]) == 2
    for item in result["results"]:
        slots = item["slots"]
        assert list(slots) == ["hair_eyes", "scene", "outfit/casual", "accessories"]
        assert slots["scene"] == "snowy shrine"
        assert slots["outfit/casual"] == "sweater"
        assert len(set(slots["accessories"].split(", "))) == 2


def test_init_skips_existing_files_and_can_overwrite(capsys, tmp_path):
    wildcard = tmp_path / "wildcards" / "hair_eyes.txt"
    wildcard.parent.mkdir()
    wildcard.write_text("my custom entry", encoding="utf-8")
    first = run_json(capsys, tmp_path, "init")
    assert len(first["copied"]) == 12
    assert first["skipped"] == ["wildcards/hair_eyes.txt"]
    assert wildcard.read_text(encoding="utf-8") == "my custom entry"
    second = run_json(capsys, tmp_path, "init")
    assert len(second["skipped"]) == 13 and not second["copied"]
    assert len(run_json(capsys, tmp_path, "init", "--overwrite")["copied"]) == 13
    assert "silver hair" in wildcard.read_text(encoding="utf-8")

    listing = run_json(capsys, tmp_path, "list")
    assert len(listing["wildcards"]) == 9
    assert all(15 <= pool["entry_count"] <= 25 for pool in listing["wildcards"])
    assert [item["name"] for item in listing["recipes"]] == ["default", "scene_cinematic"]
    assert listing["artists"] == {"count": 0, "styles": []}


def test_artists_catalog_search_roll_and_artist_hook(capsys, tmp_path):
    missing = run_json(capsys, tmp_path, "roll", "--with-artist")
    assert missing["results"][0]["artist"] is None
    assert any("No matching artist presets" in warning for warning in missing["warnings"])
    assert run_json(capsys, tmp_path, "artists", "list")["artists"] == []

    artists = tmp_path / "artists"
    artists.mkdir()
    (artists / "presets.yaml").write_text(
        "artists:\n  - id: warm\n    name: 暖色\n    styles: [painterly]\n    engines: [nai-v5]\n"
        "    prompt: '1.2::artist:example::'\n    notes: window lighting\n",
        encoding="utf-8",
    )
    (artists / "local.json").write_text(
        '{"artists":[{"id":"local","engines":["comfyui"],"prompt":"local style"}]}', encoding="utf-8",
    )
    result = run_json(capsys, tmp_path, "artists", "search", "--style", "Painterly", "--engine", "nai",
                      "--query", "window")
    assert [preset["id"] for preset in result["artists"]] == ["warm"]
    assert run_json(capsys, tmp_path, "artists", "roll", "--engine", "comfyui")["artist"]["id"] == "local"
    result = run_json(capsys, tmp_path, "roll", "--artist-id", "warm", "--lock", "subject=solo", "--target", "nai")
    assert result["results"][0]["artist"]["id"] == "warm"
    assert result["results"][0]["draft_prompt"] == "solo, 1.2::artist:example::"


def test_guides_merge_and_user_file_takes_priority(capsys, tmp_path):
    assert run_json(capsys, tmp_path, "guides", "show", "tag-guide")["guide"]["source"] == "bundled"
    guides = tmp_path / "guides"
    guides.mkdir()
    (guides / "tag-guide.md").write_text("# Personal tags\n", encoding="utf-8")
    listing = run_json(capsys, tmp_path, "guides", "list")["guides"]
    assert {item["name"]: item["source"] for item in listing} == {
        "artist-guide": "bundled", "tag-guide": "user", "wildcard-workflow": "bundled",
    }
    assert main(["guides", "show", "tag-guide.md", "--format", "text", "--data-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "# Personal tags\n"
    result = run_json(capsys, tmp_path, "guides", "show", "../../outside.md", status=1)
    assert not result["ok"] and "outside the data directory" in result["error"]


def test_data_dir_precedence_and_clear_cli_errors(capsys, tmp_path, monkeypatch):
    monkeypatch.delenv("HERMES_PAINTING_DIR", raising=False)
    assert get_data_dir().name == "painting"
    monkeypatch.setenv("HERMES_PAINTING_DIR", str(tmp_path / "env-data"))
    assert main(["list", "--kind", "wildcards"]) == 0
    assert json.loads(capsys.readouterr().out)["data_dir"] == str(tmp_path / "env-data")
    assert run_json(capsys, tmp_path, "list")["data_dir"] == str(tmp_path)
    result = run_json(capsys, tmp_path, "roll", "-f", "unknown", status=1)
    assert not result["ok"] and "Available pools:" in result["error"]
    result = run_json(capsys, tmp_path, "roll", "--lock", "unassigned", status=1)
    assert "Use --lock slot=value" in result["error"]

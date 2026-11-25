from importlib import import_module, util
from pathlib import Path
import sys
from types import ModuleType

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


class RecordingContext:
    def __init__(self):
        self.providers = []
        self.tools = {}
        self.sections = {}

    def register_image_gen_provider(self, provider):
        self.providers.append(provider.name)

    def register_tool(self, name, **tool):
        self.tools[name] = tool

    def register_system_prompt_section(self, id, **section):
        self.sections[id] = section


class SkillContext(RecordingContext):
    def __init__(self):
        super().__init__()
        self.skills = {}

    def register_skill(self, name, path, *, description):
        self.skills[name] = (path, description)


@pytest.fixture
def hermes_provider_api(monkeypatch):
    # The providers use this host module. Import and register the real plugin backends.
    provider_api = ModuleType("agent.image_gen_provider")
    provider_api.DEFAULT_ASPECT_RATIO = "landscape"
    provider_api.ImageGenProvider = object
    for name in ("error_response", "normalize_reference_images", "resolve_aspect_ratio", "save_b64_image",
                 "success_response"):
        setattr(provider_api, name, object())
    monkeypatch.setitem(sys.modules, provider_api.__name__, provider_api)


@pytest.mark.parametrize("load_as_package", [True, False])
def test_register_with_hermes_loader_and_plain_import(monkeypatch, hermes_provider_api, load_as_package):
    if load_as_package:
        spec = util.spec_from_file_location(
            "hermes_validate_probe_plugin", REPO_ROOT / "__init__.py",
            submodule_search_locations=[str(REPO_ROOT)],
        )
        plugin = util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, plugin)
        spec.loader.exec_module(plugin)
        ctx = SkillContext()
    else:
        plugin = import_module("__init__")
        ctx = RecordingContext()

    plugin.register(ctx)
    manifest = yaml.safe_load((REPO_ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    assert ctx.providers == ["novelai", "comfyui"]
    assert set(ctx.tools) == set(manifest["provides_tools"])
    for name, tool in ctx.tools.items():
        assert tool["toolset"] == name.rsplit("_", 1)[0]
        assert callable(tool["handler"])
    assert ctx.sections["prompt_craft_guidance"]["position"] == "after_memory"
    assert "hermes-image-studio:prompt-craft" in ctx.sections["prompt_craft_guidance"]["content"]
    if load_as_package:
        assert list(ctx.skills) == ["prompt-craft", "novelai-prompting", "comfyui-workflow"]
        for name, (path, description) in ctx.skills.items():
            assert path == REPO_ROOT / "skills" / name / "SKILL.md"
            frontmatter = path.read_text(encoding="utf-8").split("---", 2)[1]
            assert description == yaml.safe_load(frontmatter)["description"]

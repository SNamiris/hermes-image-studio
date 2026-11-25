"""ComfyUI configuration helpers, workflow discovery, and API-graph parameter injection."""

from __future__ import annotations

import copy
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from .constants import (
    ASPECT_DIMENSIONS,
    DEFAULT_WORKFLOW,
    LATENT_CLASS_TYPES,
    SAMPLER_CLASS_TYPES,
    TEXT_NODE_CLASS_TYPES,
)

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TEXT_FIELDS = ("text", "clip_l", "t5xxl", "prompt", "string", "value")


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes").expanduser()


def load_comfyui_config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        ig = cfg.get("image_gen") if isinstance(cfg, dict) else None
        sub = ig.get("comfyui") if isinstance(ig, dict) else None
        return sub if isinstance(sub, dict) else {}
    except Exception as exc:
        logger.debug("Could not load image_gen.comfyui config: %s", exc)
        return {}


def get_base_url(cfg: Optional[dict[str, Any]] = None) -> str:
    resolved = load_comfyui_config() if cfg is None else cfg
    raw = (
        os.environ.get("COMFYUI_BASE_URL", "").strip()
        or str(resolved.get("base_url") or "").strip()
    )
    return raw.rstrip("/")


def get_workflows_dir(cfg: Optional[dict[str, Any]] = None) -> Path:
    resolved = load_comfyui_config() if cfg is None else cfg
    raw = (
        os.environ.get("COMFYUI_WORKFLOWS_DIR", "").strip()
        or str(resolved.get("workflows_dir") or "").strip()
    )
    if raw:
        return Path(raw).expanduser()
    return hermes_home() / "comfyui" / "workflows"


def list_workflows(cfg: Optional[dict[str, Any]] = None) -> list[str]:
    wf_dir = get_workflows_dir(cfg)
    if not wf_dir.is_dir():
        return []
    names: list[str] = []
    for p in sorted(wf_dir.glob("*.json")):
        if p.name.endswith(".meta.json"):
            continue
        names.append(p.stem)
    return names


def resolve_default_workflow(cfg: Optional[dict[str, Any]] = None) -> str:
    resolved = load_comfyui_config() if cfg is None else cfg
    configured = (
        os.environ.get("COMFYUI_DEFAULT_WORKFLOW", "").strip()
        or str(resolved.get("default_workflow") or "").strip()
    )
    if configured:
        return configured
    available = list_workflows(resolved)
    if DEFAULT_WORKFLOW in available:
        return DEFAULT_WORKFLOW
    return available[0] if available else DEFAULT_WORKFLOW


def load_workflow(
    workflow_name: Optional[str] = None,
    cfg: Optional[dict[str, Any]] = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Load an API workflow JSON and optional mapping metadata.

    Returns ``(resolved_name, workflow_graph, explicit_mapping)``.
    """
    resolved_cfg = load_comfyui_config() if cfg is None else cfg
    name = (workflow_name or "").strip() or resolve_default_workflow(resolved_cfg)
    if name.endswith(".json"):
        name = name[:-5]
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(f"Invalid workflow name: {name!r}")

    wf_dir = get_workflows_dir(resolved_cfg)
    wf_path = wf_dir / f"{name}.json"
    if not wf_path.is_file():
        available = list_workflows(resolved_cfg)
        hint = f" Available: {', '.join(available)}" if available else f" Place API workflow JSON files in {wf_dir}."
        raise FileNotFoundError(f"ComfyUI workflow '{name}' not found at {wf_path}.{hint}")

    raw = json.loads(wf_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"Workflow '{name}' must be a non-empty JSON object in ComfyUI API format.")
    if "nodes" in raw and isinstance(raw.get("nodes"), list):
        raise ValueError(
            f"Workflow '{name}' looks like a ComfyUI UI graph (contains 'nodes' list), not API format. "
            "In ComfyUI, enable Dev Mode and use 'Export (API)'."
        )

    mapping: dict[str, Any] = {}
    meta_path = wf_dir / f"{name}.meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if isinstance(meta, dict):
            mapping.update(meta.get("inputs") if isinstance(meta.get("inputs"), dict) else meta)

    cfg_workflows = resolved_cfg.get("workflows")
    if isinstance(cfg_workflows, dict) and isinstance(cfg_workflows.get(name), dict):
        mapping.update(cfg_workflows[name])

    return name, raw, mapping


def _is_link(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], (str, int))


def _follow_upstream(
    graph: dict[str, Any],
    start_ref: Any,
    predicate: Any,
    *,
    max_depth: int = 12,
) -> Optional[tuple[str, dict[str, Any]]]:
    """Walk upstream node links from ``start_ref`` until ``predicate(node_id, node)`` matches."""
    if not _is_link(start_ref):
        return None
    queue: list[tuple[str, int]] = [(str(start_ref[0]), 0)]
    visited: set[str] = set()
    while queue:
        nid, depth = queue.pop(0)
        if nid in visited or depth > max_depth:
            continue
        visited.add(nid)
        node = graph.get(nid)
        if not isinstance(node, dict):
            continue
        if predicate(nid, node):
            return nid, node
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for val in inputs.values():
            if _is_link(val):
                queue.append((str(val[0]), depth + 1))
    return None


def _is_text_node(nid: str, node: dict[str, Any]) -> bool:
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return False
    ctype = str(node.get("class_type") or "")
    if ctype in TEXT_NODE_CLASS_TYPES:
        return any(isinstance(inputs.get(f), str) for f in _TEXT_FIELDS)
    return "text" in inputs and isinstance(inputs["text"], str)


def _set_text_on_node(node: dict[str, Any], value: str) -> Optional[str]:
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return None
    for field in ("text", "prompt", "string", "value"):
        if field in inputs and isinstance(inputs[field], str):
            inputs[field] = value
            return field
    # CLIPTextEncodeFlux uses clip_l + t5xxl
    updated: list[str] = []
    for field in ("clip_l", "t5xxl"):
        if field in inputs and isinstance(inputs[field], str):
            inputs[field] = value
            updated.append(field)
    return "+".join(updated) if updated else None


def _apply_explicit_target(graph: dict[str, Any], target_spec: Any, value: Any) -> bool:
    """Apply value to one or more ``'node_id.field'`` targets."""
    specs = [target_spec] if isinstance(target_spec, str) else list(target_spec) if isinstance(target_spec, list) else []
    applied = False
    for spec in specs:
        if not isinstance(spec, str) or "." not in spec:
            continue
        nid, field = spec.split(".", 1)
        node = graph.get(nid.strip())
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
            node["inputs"][field.strip()] = value
            applied = True
    return applied


def _align_8(value: int, *, minimum: int = 64, maximum: int = 2048) -> int:
    clamped = max(minimum, min(maximum, int(value)))
    return max(minimum, (clamped // 8) * 8)


def _find_samplers(graph: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    exact = [
        (nid, node)
        for nid, node in graph.items()
        if isinstance(node, dict) and str(node.get("class_type") or "") in SAMPLER_CLASS_TYPES
    ]
    if exact:
        return exact
    # Fallback: any node whose class_type contains KSampler or has both steps & cfg inputs
    fallback: list[tuple[str, dict[str, Any]]] = []
    for nid, node in graph.items():
        if not isinstance(node, dict):
            continue
        ctype = str(node.get("class_type") or "")
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if "KSampler" in ctype or ("steps" in inputs and ("seed" in inputs or "noise_seed" in inputs)):
            fallback.append((nid, node))
    return fallback


def _inject_prompt_text(
    graph: dict[str, Any],
    samplers: list[tuple[str, dict[str, Any]]],
    *,
    role: str,
    text: str,
    explicit_mapping: dict[str, Any],
) -> bool:
    if role in explicit_mapping and _apply_explicit_target(graph, explicit_mapping[role], text):
        return True

    for _, sampler in samplers:
        inputs = sampler.get("inputs") if isinstance(sampler.get("inputs"), dict) else {}
        # Standard KSampler: inputs["positive"] / inputs["negative"]
        start = inputs.get(role)
        # SamplerCustomAdvanced: inputs["guider"] -> CFGGuider/BasicGuider -> positive/negative/conditioning
        if start is None and "guider" in inputs:
            guider = _follow_upstream(
                graph,
                inputs.get("guider"),
                lambda _id, n: isinstance(n.get("inputs"), dict)
                and (role in n["inputs"] or (role == "positive" and "conditioning" in n["inputs"])),
                max_depth=4,
            )
            if guider is not None:
                g_inputs = guider[1]["inputs"]
                start = g_inputs.get(role) or (g_inputs.get("conditioning") if role == "positive" else None)

        hit = _follow_upstream(graph, start, _is_text_node)
        if hit is not None and _set_text_on_node(hit[1], text):
            return True
    return False


def _inject_sampler_scalar(
    graph: dict[str, Any],
    samplers: list[tuple[str, dict[str, Any]]],
    *,
    key: str,
    value: Any,
    explicit_mapping: dict[str, Any],
    node_fields: tuple[str, ...],
    upstream_link_keys: tuple[str, ...] = (),
) -> bool:
    if key in explicit_mapping and _apply_explicit_target(graph, explicit_mapping[key], value):
        return True

    applied = False
    for _, sampler in samplers:
        inputs = sampler.get("inputs") if isinstance(sampler.get("inputs"), dict) else {}
        matched_direct = False
        for field in node_fields:
            if field in inputs and not _is_link(inputs[field]):
                inputs[field] = value
                applied = True
                matched_direct = True
                break
        if matched_direct:
            continue
        for link_key in upstream_link_keys:
            if link_key not in inputs:
                continue
            hit = _follow_upstream(
                graph,
                inputs[link_key],
                lambda _id, n: isinstance(n.get("inputs"), dict)
                and any(f in n["inputs"] and not _is_link(n["inputs"][f]) for f in node_fields),
                max_depth=5,
            )
            if hit is not None:
                h_inputs = hit[1]["inputs"]
                for field in node_fields:
                    if field in h_inputs and not _is_link(h_inputs[field]):
                        h_inputs[field] = value
                        applied = True
                        break
    return applied


def inject_workflow_params(
    workflow: dict[str, Any],
    *,
    prompt: str,
    negative_prompt: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    steps: Optional[int] = None,
    cfg: Optional[float] = None,
    seed: Optional[int] = None,
    explicit_mapping: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(mutated_workflow_copy, applied_params_summary)``."""
    graph = copy.deepcopy(workflow)
    mapping = explicit_mapping or {}
    samplers = _find_samplers(graph)
    applied: dict[str, Any] = {}

    if not _inject_prompt_text(graph, samplers, role="positive", text=prompt, explicit_mapping=mapping):
        raise ValueError(
            "Could not locate a positive prompt node in this workflow. "
            "Add an explicit mapping (e.g. `positive: \"6.text\"`) in <workflow>.meta.json or config.yaml."
        )
    applied["prompt"] = prompt

    if negative_prompt is not None and negative_prompt.strip():
        if _inject_prompt_text(
            graph, samplers, role="negative", text=negative_prompt.strip(), explicit_mapping=mapping
        ):
            applied["negative_prompt"] = negative_prompt.strip()

    if seed is not None:
        if _inject_sampler_scalar(
            graph,
            samplers,
            key="seed",
            value=int(seed),
            explicit_mapping=mapping,
            node_fields=("seed", "noise_seed"),
            upstream_link_keys=("noise",),
        ):
            applied["seed"] = int(seed)

    if steps is not None:
        clamped_steps = max(1, min(150, int(steps)))
        if _inject_sampler_scalar(
            graph,
            samplers,
            key="steps",
            value=clamped_steps,
            explicit_mapping=mapping,
            node_fields=("steps",),
            upstream_link_keys=("sigmas",),
        ):
            applied["steps"] = clamped_steps

    if cfg is not None:
        clamped_cfg = max(0.0, min(30.0, float(cfg)))
        if _inject_sampler_scalar(
            graph,
            samplers,
            key="cfg",
            value=clamped_cfg,
            explicit_mapping=mapping,
            node_fields=("cfg", "guidance"),
            upstream_link_keys=("guider",),
        ):
            applied["cfg"] = clamped_cfg

    target_w: Optional[int] = None
    target_h: Optional[int] = None
    if width and height:
        target_w, target_h = _align_8(width), _align_8(height)
    elif isinstance(aspect_ratio, str) and aspect_ratio.strip().lower() in ASPECT_DIMENSIONS:
        target_w, target_h = ASPECT_DIMENSIONS[aspect_ratio.strip().lower()]

    if target_w and target_h:
        w_ok = "width" in mapping and _apply_explicit_target(graph, mapping["width"], target_w)
        h_ok = "height" in mapping and _apply_explicit_target(graph, mapping["height"], target_h)
        if not (w_ok and h_ok):
            for node in graph.values():
                if not isinstance(node, dict):
                    continue
                ctype = str(node.get("class_type") or "")
                inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
                if ctype in LATENT_CLASS_TYPES and "width" in inputs and "height" in inputs:
                    if not w_ok and not _is_link(inputs["width"]):
                        inputs["width"] = target_w
                        w_ok = True
                    if not h_ok and not _is_link(inputs["height"]):
                        inputs["height"] = target_h
                        h_ok = True
                    if w_ok and h_ok:
                        break
        if w_ok and h_ok:
            applied["width"] = target_w
            applied["height"] = target_h

    return graph, applied

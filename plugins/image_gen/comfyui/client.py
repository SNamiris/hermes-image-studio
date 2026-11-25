"""ComfyUI HTTP client: status probe, prompt submission, history polling, and image download."""

from __future__ import annotations

import base64
import random
import time
import uuid
from typing import Any, Optional

import requests

from agent.image_gen_provider import DEFAULT_ASPECT_RATIO, error_response, save_b64_image, success_response

from .constants import (
    DEFAULT_GENERATION_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PROBE_TIMEOUT,
    DEFAULT_REQUEST_TIMEOUT,
)
from .workflow import (
    get_base_url,
    get_workflows_dir,
    inject_workflow_params,
    list_workflows,
    load_comfyui_config,
    load_workflow,
    resolve_default_workflow,
)


def _extract_http_error(resp: Optional[requests.Response]) -> str:
    if resp is None:
        return "No response received"
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error")
            node_errors = data.get("node_errors")
            parts: list[str] = []
            if isinstance(err, dict):
                parts.append(str(err.get("message") or err.get("details") or err))
            elif err:
                parts.append(str(err))
            if isinstance(node_errors, dict) and node_errors:
                summary = ", ".join(f"node {k}: {v}" for k, v in list(node_errors.items())[:3])
                parts.append(summary)
            if parts:
                return " | ".join(parts)[:500]
    except Exception:
        pass
    text = (resp.text or "").strip()
    return text[:400] if text else f"HTTP {resp.status_code}"


def _probe_system_stats(base_url: str, timeout: float = DEFAULT_PROBE_TIMEOUT) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    try:
        resp = requests.get(f"{base_url}/system_stats", timeout=timeout)
        if not resp.ok:
            return None, f"ComfyUI /system_stats returned HTTP {resp.status_code}: {_extract_http_error(resp)}"
        return resp.json(), None
    except requests.Timeout:
        return None, f"ComfyUI at {base_url} did not respond within {timeout:.0f}s (is your PC / ComfyUI running and Tailscale connected?)."
    except requests.RequestException as exc:
        return None, f"Could not reach ComfyUI at {base_url}: {exc}"


def _extract_history_error(entry: dict[str, Any]) -> Optional[str]:
    status = entry.get("status")
    if not isinstance(status, dict) or status.get("status_str") != "error":
        return None
    messages = status.get("messages") or []
    for msg in messages:
        if isinstance(msg, list) and len(msg) >= 2 and msg[0] == "execution_error" and isinstance(msg[1], dict):
            info = msg[1]
            node_type = info.get("node_type") or info.get("node_id") or "unknown"
            exc_msg = info.get("exception_message") or info.get("exception_type") or "execution error"
            return f"ComfyUI execution error in {node_type}: {str(exc_msg).strip()}"
    return "ComfyUI workflow execution failed."


def _pick_output_image(entry: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Prefer the last ``type == 'output'`` image (final SaveImage node); fall back to temp previews."""
    outputs = entry.get("outputs")
    if not isinstance(outputs, dict):
        return None

    output_images: list[dict[str, Any]] = []
    temp_images: list[dict[str, Any]] = []
    for node_out in outputs.values():
        if not isinstance(node_out, dict):
            continue
        for img in node_out.get("images") or []:
            if not isinstance(img, dict) or not img.get("filename"):
                continue
            if img.get("type", "output") == "output":
                output_images.append(img)
            else:
                temp_images.append(img)

    if output_images:
        return output_images[-1]
    return temp_images[-1] if temp_images else None


def check_comfyui_status() -> dict[str, Any]:
    """Probe ComfyUI online status, GPU summary, and available API workflows."""
    cfg = load_comfyui_config()
    base_url = get_base_url(cfg)
    wf_dir = get_workflows_dir(cfg)
    workflows = list_workflows(cfg)
    default_wf = resolve_default_workflow(cfg)

    if not base_url:
        return {
            "success": True,
            "online": False,
            "configured": False,
            "error": "COMFYUI_BASE_URL is not configured. Set COMFYUI_BASE_URL (e.g. http://<tailscale-ip>:8188) in ~/.hermes/.env or image_gen.comfyui.base_url in ~/.hermes/config.yaml.",
            "workflows_dir": str(wf_dir),
            "workflows": workflows,
            "default_workflow": default_wf,
        }

    probe_timeout = float(cfg.get("probe_timeout") or DEFAULT_PROBE_TIMEOUT)
    stats, err = _probe_system_stats(base_url, timeout=probe_timeout)
    if err or stats is None:
        return {
            "success": True,
            "online": False,
            "configured": True,
            "base_url": base_url,
            "error": err,
            "workflows_dir": str(wf_dir),
            "workflows": workflows,
            "default_workflow": default_wf,
        }

    devices = [
        {
            "name": d.get("name"),
            "type": d.get("type"),
            "vram_free_mb": round(int(d.get("vram_free") or 0) / (1024 * 1024)),
            "vram_total_mb": round(int(d.get("vram_total") or 0) / (1024 * 1024)),
        }
        for d in (stats.get("devices") or [])
        if isinstance(d, dict)
    ]
    system = stats.get("system") if isinstance(stats.get("system"), dict) else {}
    return {
        "success": True,
        "online": True,
        "configured": True,
        "base_url": base_url,
        "comfyui_version": system.get("comfyui_version"),
        "devices": devices,
        "workflows_dir": str(wf_dir),
        "workflows": workflows,
        "default_workflow": default_wf,
    }


def generate_comfyui(
    *,
    prompt: str,
    negative_prompt: Optional[str] = None,
    workflow: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    steps: Optional[int] = None,
    cfg: Optional[float] = None,
    seed: Optional[int] = None,
) -> dict[str, Any]:
    """Run a ComfyUI API workflow and save the generated image to Hermes's cache."""
    conf = load_comfyui_config()
    base_url = get_base_url(conf)
    wf_label = (workflow or "").strip() or resolve_default_workflow(conf)

    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        return error_response(
            error="Prompt is required and must be a non-empty string.",
            error_type="invalid_input",
            provider="comfyui",
            model=wf_label,
            prompt=str(prompt or ""),
        )
    if not base_url:
        return error_response(
            error=(
                "COMFYUI_BASE_URL is not configured. Set COMFYUI_BASE_URL=http://<tailscale-ip>:8188 "
                "in ~/.hermes/.env or image_gen.comfyui.base_url in ~/.hermes/config.yaml."
            ),
            error_type="config_error",
            provider="comfyui",
            model=wf_label,
            prompt=prompt,
        )

    try:
        wf_name, raw_graph, explicit_mapping = load_workflow(workflow, conf)
    except Exception as exc:
        return error_response(
            error=str(exc),
            error_type="invalid_input",
            provider="comfyui",
            model=wf_label,
            prompt=prompt,
        )

    resolved_seed = int(seed) if seed is not None and int(seed) >= 0 else random.randint(1, 2**32 - 1)
    try:
        graph, applied = inject_workflow_params(
            raw_graph,
            prompt=prompt.strip(),
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            seed=resolved_seed,
            explicit_mapping=explicit_mapping,
        )
    except Exception as exc:
        return error_response(
            error=str(exc),
            error_type="invalid_input",
            provider="comfyui",
            model=wf_name,
            prompt=prompt,
        )

    # Fast liveness probe so offline PC fails immediately instead of waiting for generation timeout
    probe_timeout = float(conf.get("probe_timeout") or DEFAULT_PROBE_TIMEOUT)
    _, probe_err = _probe_system_stats(base_url, timeout=probe_timeout)
    if probe_err:
        return error_response(
            error=probe_err,
            error_type="connection_error",
            provider="comfyui",
            model=wf_name,
            prompt=prompt,
        )

    client_id = uuid.uuid4().hex
    req_timeout = float(conf.get("request_timeout") or DEFAULT_REQUEST_TIMEOUT)
    try:
        submit = requests.post(
            f"{base_url}/prompt",
            json={"prompt": graph, "client_id": client_id},
            timeout=req_timeout,
        )
        if not submit.ok:
            return error_response(
                error=f"ComfyUI rejected workflow '{wf_name}' ({submit.status_code}): {_extract_http_error(submit)}",
                error_type="api_error",
                provider="comfyui",
                model=wf_name,
                prompt=prompt,
            )
        submit_body = submit.json()
        if isinstance(submit_body, dict) and submit_body.get("node_errors"):
            return error_response(
                error=f"ComfyUI workflow '{wf_name}' has node validation errors: {_extract_http_error(submit)}",
                error_type="api_error",
                provider="comfyui",
                model=wf_name,
                prompt=prompt,
            )
        prompt_id = submit_body.get("prompt_id") if isinstance(submit_body, dict) else None
        if not prompt_id:
            return error_response(
                error=f"ComfyUI did not return a prompt_id: {submit_body}",
                error_type="invalid_response",
                provider="comfyui",
                model=wf_name,
                prompt=prompt,
            )
    except requests.RequestException as exc:
        return error_response(
            error=f"Failed to submit workflow to ComfyUI: {exc}",
            error_type="connection_error",
            provider="comfyui",
            model=wf_name,
            prompt=prompt,
        )

    # Poll /history/{prompt_id}
    gen_timeout = float(conf.get("timeout") or DEFAULT_GENERATION_TIMEOUT)
    poll_interval = max(0.3, float(conf.get("poll_interval") or DEFAULT_POLL_INTERVAL))
    deadline = time.monotonic() + gen_timeout
    chosen_image: Optional[dict[str, Any]] = None
    last_http_error: Optional[str] = None

    while time.monotonic() < deadline:
        remaining = max(1.0, deadline - time.monotonic())
        try:
            hist_resp = requests.get(f"{base_url}/history/{prompt_id}", timeout=min(req_timeout, remaining))
            if hist_resp.ok:
                last_http_error = None
                hist = hist_resp.json()
                entry = hist.get(prompt_id) if isinstance(hist, dict) else None
                if isinstance(entry, dict):
                    exec_err = _extract_history_error(entry)
                    if exec_err:
                        return error_response(
                            error=exec_err,
                            error_type="api_error",
                            provider="comfyui",
                            model=wf_name,
                            prompt=prompt,
                        )
                    chosen_image = _pick_output_image(entry)
                    if chosen_image is not None:
                        break
                    status = entry.get("status")
                    if isinstance(status, dict) and status.get("completed") is True:
                        return error_response(
                            error=f"ComfyUI workflow '{wf_name}' completed but produced no image output (ensure it has a SaveImage node).",
                            error_type="empty_response",
                            provider="comfyui",
                            model=wf_name,
                            prompt=prompt,
                        )
            elif hist_resp.status_code != 404:
                last_http_error = f"HTTP {hist_resp.status_code}: {_extract_http_error(hist_resp)}"
        except requests.RequestException as exc:
            return error_response(
                error=f"Lost connection to ComfyUI while waiting for result: {exc}",
                error_type="connection_error",
                provider="comfyui",
                model=wf_name,
                prompt=prompt,
            )
        sleep_for = min(poll_interval, max(0.0, deadline - time.monotonic()))
        if sleep_for > 0:
            time.sleep(sleep_for)

    if chosen_image is None:
        detail = f" Last polling error: {last_http_error}" if last_http_error else ""
        return error_response(
            error=f"ComfyUI generation timed out after {int(gen_timeout)}s (prompt_id={prompt_id}).{detail}",
            error_type="timeout",
            provider="comfyui",
            model=wf_name,
            prompt=prompt,
        )

    # Download image via /view
    filename = str(chosen_image["filename"])
    view_params = {
        "filename": filename,
        "subfolder": str(chosen_image.get("subfolder") or ""),
        "type": str(chosen_image.get("type") or "output"),
    }
    try:
        view_resp = requests.get(f"{base_url}/view", params=view_params, timeout=req_timeout)
        if not view_resp.ok or not view_resp.content:
            return error_response(
                error=f"Failed to download image from ComfyUI /view ({view_resp.status_code}).",
                error_type="api_error",
                provider="comfyui",
                model=wf_name,
                prompt=prompt,
            )
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
        if ext not in ("png", "jpg", "jpeg", "webp"):
            ext = "png"
        if ext == "jpeg":
            ext = "jpg"
        b64_img = base64.b64encode(view_resp.content).decode("ascii")
        saved_path = save_b64_image(b64_img, prefix=f"comfyui_{wf_name}", extension=ext)
    except Exception as exc:
        return error_response(
            error=f"Failed to fetch or save ComfyUI image: {exc}",
            error_type="invalid_response",
            provider="comfyui",
            model=wf_name,
            prompt=prompt,
        )

    ratio_label = aspect_ratio or DEFAULT_ASPECT_RATIO
    if "width" in applied and "height" in applied:
        w, h = applied["width"], applied["height"]
        ratio_label = "square" if w == h else ("landscape" if w > h else "portrait")

    return success_response(
        image=str(saved_path),
        model=wf_name,
        prompt=prompt.strip(),
        aspect_ratio=ratio_label,
        provider="comfyui",
        modality="text",
        extra={
            "media_tag": f"MEDIA:{saved_path}",
            "workflow": wf_name,
            "prompt_id": prompt_id,
            **{k: v for k, v in applied.items() if k != "prompt"},
        },
    )

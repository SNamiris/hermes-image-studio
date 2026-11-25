"""Image I/O, preprocessing, ZIP extraction, and Vibe encoding helpers for NovelAI."""

from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

import requests
from PIL import Image

from .constants import ENCODE_VIBE_URL


def extract_http_error(resp: Optional[requests.Response]) -> str:
    if resp is None:
        return "No response received"
    try:
        data = resp.json()
        if isinstance(data, dict):
            msg = data.get("message") or data.get("error") or data.get("detail")
            if msg:
                return str(msg)
    except Exception:
        pass
    text = (resp.text or "").strip()
    return text[:400] if text else f"HTTP {resp.status_code}"


def load_image_from_ref(ref: str, timeout: float = 30.0) -> tuple[Image.Image, bytes]:
    """Load an image from a local file path, file:// URI, data: URI, or http(s) URL."""
    raw = ref.strip()
    if raw.startswith("data:"):
        _, b64 = raw.split(",", 1)
        data = base64.b64decode(b64)
    elif raw.startswith(("http://", "https://")):
        resp = requests.get(raw, timeout=timeout)
        resp.raise_for_status()
        data = resp.content
    else:
        path_str = unquote(urlparse(raw).path) if raw.startswith("file://") else raw
        p = Path(path_str).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"Image file not found: {p}")
        data = p.read_bytes()

    img = Image.open(io.BytesIO(data))
    img.load()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    return img, data


def pil_to_png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def fit_cover(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Aspect-preserving center crop before resize for img2img (low memory footprint)."""
    src = img.convert("RGB")
    sw, sh = src.size
    if (sw, sh) == (target_w, target_h):
        return src
    target_ratio = target_w / target_h
    src_ratio = sw / sh
    if src_ratio > target_ratio:
        crop_w = max(1, int(round(sh * target_ratio)))
        left = (sw - crop_w) // 2
        cropped = src.crop((left, 0, left + crop_w, sh))
    else:
        crop_h = max(1, int(round(sw / target_ratio)))
        top = (sh - crop_h) // 2
        cropped = src.crop((0, top, sw, top + crop_h))
    return cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)


def pad_director_reference(img: Image.Image) -> Image.Image:
    """Letterbox a reference image onto NovelAI's required Precise Reference canvas."""
    src = img.convert("RGB")
    sw, sh = src.size
    if sh > sw * 1.15:
        canvas_w, canvas_h = 1024, 1536
    elif sw > sh * 1.15:
        canvas_w, canvas_h = 1536, 1024
    else:
        canvas_w, canvas_h = 1472, 1472

    scale = min(canvas_w / sw, canvas_h / sh)
    nw, nh = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    canvas.paste(resized, ((canvas_w - nw) // 2, (canvas_h - nh) // 2))
    return canvas


def extract_image_from_zip(content: bytes) -> tuple[bytes, str]:
    """Unpack the first image from NovelAI's ZIP response (or handle raw PNG bytes)."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return content, "png"
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for name in zf.namelist():
            lower = name.lower()
            if lower.endswith((".png", ".webp", ".jpg", ".jpeg")):
                ext = "jpg" if lower.endswith(".jpeg") else lower.rsplit(".", 1)[-1]
                return zf.read(name), ext
        names = zf.namelist()
        if names:
            return zf.read(names[0]), "png"
    raise ValueError("NovelAI returned an empty archive with no image.")


def encode_vibe_v4(
    *,
    headers: dict[str, str],
    cache_dir: Path,
    img: Image.Image,
    raw_bytes: bytes,
    model: str,
    information_extracted: float,
    timeout: float,
) -> str:
    """Encode a Vibe Transfer image for V4/V5 via /ai/encode-vibe with disk cache."""
    info_val = max(0.01, min(1.0, float(information_extracted)))
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(
        raw_bytes + f"|{model}|{info_val:.4f}".encode("utf-8")
    ).hexdigest()
    cache_file = cache_dir / f"{digest}.b64"
    if cache_file.is_file():
        cached = cache_file.read_text(encoding="utf-8").strip()
        if cached:
            return cached

    payload = {
        "image": pil_to_png_b64(img),
        "information_extracted": info_val,
        "model": model,
    }
    resp = requests.post(
        ENCODE_VIBE_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    if not resp.ok:
        raise RuntimeError(
            f"NovelAI /ai/encode-vibe failed ({resp.status_code}): {extract_http_error(resp)}"
        )
    encoded = base64.b64encode(resp.content).decode("ascii")
    try:
        tmp_file = cache_file.with_suffix(".b64.tmp")
        tmp_file.write_text(encoded, encoding="utf-8")
        tmp_file.replace(cache_file)
    except OSError:
        pass
    return encoded

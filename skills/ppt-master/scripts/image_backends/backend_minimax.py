#!/usr/bin/env python3
"""
MiniMax image generation backend.

Configuration keys:
  MINIMAX_API_KEY   (required)
  MINIMAX_BASE_URL  (optional)
  MINIMAX_MODEL     (optional)

Supported models:
  - image-01        (default, supports aspect_ratio or width+height)
  - image-01-live   (supports style guidance)
"""

import sys

if __name__ == "__main__" and any(arg in {"-h", "--help", "help"} for arg in sys.argv[1:]):
    print(__doc__)
    print("Use via: python3 skills/ppt-master/scripts/image_gen.py \"prompt\" --backend minimax")
    raise SystemExit(0)

import base64
import os
import time

import requests

from image_backends.backend_common import (
    MAX_RETRIES,
    detect_image_extension,
    http_error,
    is_rate_limit_error,
    require_api_key,
    resolve_output_path,
    retry_delay,
    save_image_bytes,
)


DEFAULT_ENDPOINT = "https://api.minimaxi.com/v1/image_generation"
DEFAULT_MODEL = "image-01"

# Valid aspect ratio strings accepted by the MiniMax API
VALID_ASPECT_RATIOS = {"1:1", "16:9", "4:3", "3:2", "2:3", "3:4", "9:16", "21:9"}


def _resolve_url(base_url: str) -> str:
    """Resolve the MiniMax image generation endpoint.

    Accepts three forms of MINIMAX_BASE_URL:
      - Full endpoint:  https://api.minimax.io/v1/image_generation  -> used as-is
      - Versioned base: https://api.minimax.io/v1                   -> appends /image_generation
      - Root base:      https://api.minimax.io                      -> appends /v1/image_generation
    """
    base = base_url.rstrip("/")
    if base.endswith("/image_generation"):
        return base
    if base.endswith("/v1"):
        return base + "/image_generation"
    return base + "/v1/image_generation"


def _extract_image_bytes(payload: dict) -> bytes | None:
    """Extract image bytes from a MiniMax response payload."""
    data = payload.get("data") or {}
    image_base64 = data.get("image_base64") or []
    if image_base64:
        return base64.b64decode(image_base64[0])
    return None


def _generate_image(api_key: str, prompt: str,
                    aspect_ratio: str = "1:1", image_size: str = "1K",
                    output_dir: str = None, filename: str = None,
                    model: str = DEFAULT_MODEL, base_url: str = DEFAULT_ENDPOINT) -> str:
    """Generate one image with the MiniMax backend."""
    url = _resolve_url(base_url)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "response_format": "base64",
        "n": 1,
    }

    print("[MiniMax Image]")
    print(f"  Model:        {model}")
    print(f"  Prompt:       {prompt[:120]}{'...' if len(prompt) > 120 else ''}")
    print(f"  Aspect Ratio: {aspect_ratio}")
    print()
    print("  [..] Generating...", end="", flush=True)
    start = time.time()
    response = requests.post(url, headers=headers, json=payload, timeout=300)
    elapsed = time.time() - start
    print(f"\n  [DONE] Response received ({elapsed:.1f}s)")

    if response.status_code != 200:
        raise http_error(response, "MiniMax image generation")

    data = response.json()
    base_resp = data.get("base_resp") or {}
    if base_resp.get("status_code") not in (None, 0, "0"):
        raise RuntimeError(f"MiniMax image generation failed: {data}")

    image_bytes = _extract_image_bytes(data)
    if not image_bytes:
        raise RuntimeError(f"MiniMax response missing image data: {data}")

    ext = detect_image_extension(image_bytes) or ".jpeg"
    path = resolve_output_path(prompt, output_dir, filename, ext)
    return save_image_bytes(image_bytes, path)


def generate(prompt: str,
             aspect_ratio: str = "1:1", image_size: str = "1K",
             output_dir: str = None, filename: str = None,
             model: str = None, max_retries: int = MAX_RETRIES) -> str:
    """Generate an image with retries using the MiniMax backend."""
    api_key = require_api_key(
        "MINIMAX_API_KEY",
        message="No API key found. Set MINIMAX_API_KEY in the current environment or a .env file.",
    )
    base_url = os.environ.get("MINIMAX_BASE_URL") or DEFAULT_ENDPOINT
    resolved_model = model or os.environ.get("MINIMAX_MODEL") or DEFAULT_MODEL

    if aspect_ratio not in VALID_ASPECT_RATIOS:
        raise ValueError(
            f"Unsupported aspect ratio '{aspect_ratio}' for MiniMax backend. "
            f"Supported: {sorted(VALID_ASPECT_RATIOS)}"
        )

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return _generate_image(
                api_key=api_key,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                output_dir=output_dir,
                filename=filename,
                model=resolved_model,
                base_url=base_url,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            limited = is_rate_limit_error(exc)
            delay = retry_delay(attempt, rate_limited=limited)
            label = "Rate limit hit" if limited else f"Error: {exc}"
            print(f"\n  [WARN] {label}. Retrying in {delay}s...")
            time.sleep(delay)

    raise RuntimeError(f"Failed after {max_retries + 1} attempts. Last error: {last_error}")

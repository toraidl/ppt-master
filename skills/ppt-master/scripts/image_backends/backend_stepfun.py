#!/usr/bin/env python3
"""
StepFun (阶跃星辰) image generation backend.

Configuration keys:
  STEPFUN_API_KEY   (required)
  STEPFUN_BASE_URL  (optional)
  STEPFUN_MODEL     (optional)
"""

import sys

if __name__ == "__main__" and any(arg in {"-h", "--help", "help"} for arg in sys.argv[1:]):
    print(__doc__)
    print("Use via: python3 skills/ppt-master/scripts/image_gen.py \"prompt\" --backend stepfun")
    raise SystemExit(0)

import os
import time

import requests

from image_backends.backend_common import (
    MAX_RETRIES,
    download_image,
    http_error,
    is_rate_limit_error,
    require_api_key,
    resolve_output_path,
    retry_delay,
)


DEFAULT_ENDPOINT = "https://api.stepfun.com/v1/images/generations"
DEFAULT_MODEL = "step-image-edit-2"

# Size map for step-image-edit-2 (recommended model, supports most ratios)
ASPECT_RATIO_SIZE_MAP = {
    "1:1": "1024x1024",
    "2:3": "768x1360",
    "3:2": "1360x768",
    "3:4": "896x1184",
    "4:3": "1184x896",
    "4:5": "896x1184",
    "5:4": "1184x896",
    "9:16": "768x1360",
    "16:9": "1360x768",
    "21:9": "1360x768",
}


def _resolve_url(base_url: str) -> str:
    """Resolve the StepFun generation endpoint."""
    base = base_url.rstrip("/")
    if base.endswith("/images/generations"):
        return base
    return base + "/v1/images/generations"


def _normalize_aspect_ratio(aspect_ratio: str) -> str:
    """Map common custom ratios to supported StepFun ratios."""
    ratio_map = {
        "1.5:1": "3:2",
        "1.54:1": "16:9",
        "1.6:1": "16:9",
        "1.77:1": "16:9",
        "1.8:1": "16:9",
        "2.0:1": "16:9",
        "2.1:1": "21:9",
        "2.16:1": "21:9",
        "6:5": "4:3",
        "5:3": "3:2",
        "7:5": "3:2",
        "8:5": "16:9",
        "16:10": "16:9",
        "3:1": "16:9",
        "1:3": "9:16",
        "2:1": "16:9",
        "1:2": "9:16",
    }
    return ratio_map.get(aspect_ratio, aspect_ratio)


def _resolve_size(aspect_ratio: str, image_size: str) -> str:
    """Resolve the target size for a ratio. image_size is ignored for StepFun (fixed per model)."""
    ratio = _normalize_aspect_ratio(aspect_ratio)
    size = ASPECT_RATIO_SIZE_MAP.get(ratio)
    if not size:
        supported = sorted(ASPECT_RATIO_SIZE_MAP)
        raise ValueError(
            f"Unsupported aspect ratio '{aspect_ratio}' for StepFun backend. "
            f"Supported: {supported}"
        )
    return size


def _generate_image(api_key: str, prompt: str,
                    aspect_ratio: str = "1:1", image_size: str = "1K",
                    output_dir: str = None, filename: str = None,
                    model: str = DEFAULT_MODEL, base_url: str = DEFAULT_ENDPOINT) -> str:
    """Generate one image with the StepFun backend."""
    size = _resolve_size(aspect_ratio, image_size)
    url = _resolve_url(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": "url",
        "n": 1,
    }

    print("[StepFun Image]")
    print(f"  Model:        {model}")
    print(f"  Prompt:       {prompt[:120]}{'...' if len(prompt) > 120 else ''}")
    print(f"  Aspect Ratio: {aspect_ratio}")
    print(f"  Resolution:   {size}")
    print()
    print("  [..] Generating...", end="", flush=True)
    start = time.time()
    response = requests.post(url, headers=headers, json=payload, timeout=300)
    elapsed = time.time() - start
    print(f"\n  [DONE] Response received ({elapsed:.1f}s)")

    if response.status_code != 200:
        raise http_error(response, "StepFun image generation")

    data = response.json()
    items = data.get("data") or []
    if not items:
        raise RuntimeError(f"StepFun response missing image data: {data}")

    finish_reason = items[0].get("finish_reason", "")
    if finish_reason == "content_filtered":
        raise RuntimeError(f"StepFun content filter triggered: {data}")

    image_url = items[0].get("url")
    if not image_url:
        raise RuntimeError(f"StepFun response missing image URL: {data}")

    path = resolve_output_path(prompt, output_dir, filename, ".jpeg")
    return download_image(image_url, path)


def generate(prompt: str,
             aspect_ratio: str = "1:1", image_size: str = "1K",
             output_dir: str = None, filename: str = None,
             model: str = None, max_retries: int = MAX_RETRIES) -> str:
    """Generate an image with retries using the StepFun backend."""
    api_key = require_api_key(
        "STEPFUN_API_KEY",
        message="No API key found. Set STEPFUN_API_KEY in the current environment or a .env file.",
    )
    base_url = os.environ.get("STEPFUN_BASE_URL") or DEFAULT_ENDPOINT
    resolved_model = model or os.environ.get("STEPFUN_MODEL") or DEFAULT_MODEL

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
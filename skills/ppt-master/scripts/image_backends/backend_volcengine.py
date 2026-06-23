#!/usr/bin/env python3
"""
Volcengine Seedream image generation backend.

Configuration keys:
  VOLCENGINE_API_KEY / ARK_API_KEY   (required)
  VOLCENGINE_BASE_URL                (optional)
  VOLCENGINE_MODEL                   (optional)
"""

import sys

if __name__ == "__main__":
    print(__doc__)
    print("Use via: python3 skills/ppt-master/scripts/image_gen.py \"prompt\" --backend volcengine")
    raise SystemExit(0 if any(arg in {"-h", "--help", "help"} for arg in sys.argv[1:]) else 1)

import os
import time

import requests

from image_backends.backend_common import (
    MAX_RETRIES,
    download_image,
    http_error,
    is_rate_limit_error,
    normalize_image_size,
    require_api_key,
    resolve_output_path,
    retry_delay,
)


DEFAULT_ENDPOINT = "https://operator.las.cn-beijing.volces.com/api/v1/images/generations"
DEFAULT_MODEL = "doubao-seedream-4-5-251128"

ASPECT_RATIO_SIZE_MAP = {
    "512px": {
        "1:1": "1024x1024",
        "2:3": "1024x1536",
        "3:2": "1536x1024",
        "3:4": "1024x1365",
        "4:3": "1365x1024",
        "4:5": "1024x1280",
        "5:4": "1280x1024",
        "9:16": "1024x1820",
        "16:9": "1820x1024",
        "21:9": "2048x878",
    },
    "1K": {
        "1:1": "1536x1536",
        "2:3": "1344x2016",
        "3:2": "2016x1344",
        "3:4": "1440x1920",
        "4:3": "1920x1440",
        "4:5": "1536x1920",
        "5:4": "1920x1536",
        "9:16": "1152x2048",
        "16:9": "2048x1152",
        "21:9": "2048x878",
    },
    "2K": {
        "1:1": "1920x1920",
        "2:3": "1568x2352",
        "3:2": "2352x1568",
        "3:4": "1664x2219",
        "4:3": "2219x1664",
        "4:5": "1714x2143",
        "5:4": "2143x1714",
        "9:16": "1440x2560",
        "16:9": "2560x1440",
        "21:9": "3024x1296",
    },
    "4K": {
        "1:1": "1920x1920",
        "2:3": "1568x2352",
        "3:2": "2352x1568",
        "3:4": "1664x2219",
        "4:3": "2219x1664",
        "4:5": "1714x2143",
        "5:4": "2143x1714",
        "9:16": "1440x2560",
        "16:9": "2560x1440",
        "21:9": "3024x1296",
    },
}


def _resolve_url(base_url: str) -> str:
    """Resolve the Volcengine generation endpoint."""
    base = base_url.rstrip("/")
    if base.endswith("/images/generations"):
        return base
    return base + "/api/v1/images/generations"


def _normalize_aspect_ratio(aspect_ratio: str) -> str:
    """Map common custom ratios to supported Volcengine ratios."""
    ratio_map = {
        "1.5:1": "3:2",
        "1.54:1": "16:9",
        "1.6:1": "16:9",
        "1.8:1": "9:5",
        "2.0:1": "2:1",
        "2.1:1": "21:10",
        "2.16:1": "21:9",
        "1.77:1": "16:9",
        "6:5": "4:3",
        "5:4": "4:3",
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

def _check_min_pixels(size: str) -> bool:
    """Check if size meets minimum 3,686,400 pixels requirement."""
    min_pixels = 3686400
    size_map = {
        "512px": {"1024x1024": 1048576, "2048x878": 1798144},
        "1K": {"1536x1536": 2359296, "2048x1152": 2359296, "2560x1440": 3686400, "3024x1296": 3919104},
        "2K": {"1920x1920": 3686400, "2560x1440": 3686400, "3024x1296": 3919104},
        "4K": {"1920x1920": 3686400, "2560x1440": 3686400, "3024x1296": 3919104},
    }
    for preset, resolutions in size_map.items():
        for res, pixels in resolutions.items():
            if size == res and pixels >= min_pixels:
                return True
    return False

def _resolve_size(aspect_ratio: str, image_size: str) -> str:
    """Resolve the target resolution for a ratio and logical size preset."""
    normalized = normalize_image_size(image_size)
    ratio = _normalize_aspect_ratio(aspect_ratio)
    size = (ASPECT_RATIO_SIZE_MAP.get(normalized) or {}).get(ratio)
    if not size:
        supported = sorted(ASPECT_RATIO_SIZE_MAP["1K"])
        raise ValueError(
            f"Unsupported aspect ratio '{aspect_ratio}' for Volcengine backend. "
            f"Supported: {supported}"
        )

    if not _check_min_pixels(size):
        print(f"  [WARN] Size {size} ({normalized}) does not meet minimum pixel requirement. "
              f"Upgrading to 2K equivalent for same ratio.")
        size_2k = (ASPECT_RATIO_SIZE_MAP["2K"] or {}).get(ratio)
        if size_2k:
            return size_2k
        else:
            raise ValueError(
                f"Cannot find valid 2K size for ratio '{ratio}'"
            )

    return size


def _generate_image(api_key: str, prompt: str,
                    aspect_ratio: str = "1:1", image_size: str = "1K",
                    output_dir: str = None, filename: str = None,
                    model: str = DEFAULT_MODEL, base_url: str = DEFAULT_ENDPOINT) -> str:
    """Generate one image with the Volcengine backend."""
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
        "watermark": False,
    }

    print("[Volcengine Seedream]")
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
        raise http_error(response, "Volcengine image generation")

    data = response.json()
    items = data.get("data") or []
    image_url = items[0].get("url") if items else None
    if not image_url:
        raise RuntimeError(f"Volcengine response missing image URL: {data}")

    path = resolve_output_path(prompt, output_dir, filename, ".jpeg")
    return download_image(image_url, path)


def generate(prompt: str,
             aspect_ratio: str = "1:1", image_size: str = "1K",
             output_dir: str = None, filename: str = None,
             model: str = None, max_retries: int = MAX_RETRIES) -> str:
    """Generate an image with retries using the Volcengine backend."""
    api_key = require_api_key(
        "VOLCENGINE_API_KEY",
        "ARK_API_KEY",
        message="No API key found. Set VOLCENGINE_API_KEY or ARK_API_KEY in the current environment or a .env file.",
    )
    base_url = os.environ.get("VOLCENGINE_BASE_URL") or DEFAULT_ENDPOINT
    resolved_model = model or os.environ.get("VOLCENGINE_MODEL") or DEFAULT_MODEL

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

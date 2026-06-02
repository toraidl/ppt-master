#!/usr/bin/env python3
"""
OpenCLI-Gemini image generation backend.

Uses opencli tool to call Gemini web API for image generation.
Requires opencli CLI tool installed.

Configuration keys:
  (None - uses opencli gemini web adapter via browser automation)
"""

import sys
import subprocess
import os
import time
import glob

if __name__ == "__main__" and any(arg in {"-h", "--help", "help"} for arg in sys.argv[1:]):
    print(__doc__)
    print("Use via: python3 skills/ppt-master/scripts/image_gen.py \"prompt\" --backend opencli-gemini")
    raise SystemExit(0)

from image_backends.backend_common import (
    MAX_RETRIES,
    retry_delay,
)

# Supported aspect ratios by Gemini web adapter
VALID_ASPECT_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"]

VALID_IMAGE_SIZES = ["512px", "1K", "2K", "4K"]

def _normalize_aspect_ratio(aspect_ratio: str) -> str:
    """Map common ratios to supported Gemini ratios."""
    ratio_map = {
        "1.5:1": "3:2",
        "1.54:1": "16:9",
        "1.6:1": "16:9",
        "1.8:1": "9:5",
        "2.0:1": "2:1",
        "2.1:1": "21:10",
        "2.16:1": "21:9",
        "1.77:1": "16:9",
        "9:5": "3:2",
        "21:9": "16:9",
        "21:10": "16:9",
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

def _check_opencli_available() -> bool:
    """Check if opencli tool is available."""
    try:
        result = subprocess.run(["opencli", "--version"],
                              capture_output=True,
                              text=True,
                              timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def _generate_image(prompt: str,
                    aspect_ratio: str = "1:1", image_size: str = "1K",
                    output_dir: str = None, filename: str = None) -> str:
    """
    Image generation via opencli Gemini web adapter.
    Note: image_size is ignored (Gemini auto-determines resolution).
    """
    ratio = _normalize_aspect_ratio(aspect_ratio)
    if ratio not in VALID_ASPECT_RATIOS:
        raise ValueError(
            f"Unsupported aspect ratio '{aspect_ratio}' for OpenCLI-Gemini. "
            f"Supported: {VALID_ASPECT_RATIOS}"
        )

    output_dir = output_dir or os.path.expanduser("~/tmp/gemini-images")
    os.makedirs(output_dir, exist_ok=True)

    if filename:
        if not filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            filename = f"{filename}.png"
    else:
        filename = "gemini_image.png"

    cmd = [
        "opencli", "gemini", "image", prompt,
        "--rt", ratio,
        "--op", output_dir,
        "--timeout", "600",  # 10 minutes for slow Gemini web
        "--site-session", "ephemeral",
        "--window", "background"
    ]

    print("[OpenCLI-Gemini]")
    print(f"  Prompt:       {prompt[:120]}{'...' if len(prompt) > 120 else ''}")
    print(f"  Aspect Ratio: {ratio}")
    print(f"  Output Dir:   {output_dir}")
    print()
    print("  [..] Generating...", end="", flush=True)
    start = time.time()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=660)
        elapsed = time.time() - start
        print(f"\n  [DONE] Completed ({elapsed:.1f}s)")

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Unknown error"
            raise RuntimeError(f"OpenCLI-Gemini generation failed: {error_msg}")

        output = result.stdout.strip()
        print(f"  [INFO] {output[:200]}")

        if "no-images" in output.lower():
            raise RuntimeError("Gemini web failed to generate images. Check if Gemini web is accessible or quota exceeded.")

        images = []
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            images.extend(glob.glob(os.path.join(output_dir, ext)))

        if not images:
            raise RuntimeError(f"No image files found in {output_dir}")

        latest_image = max(images, key=os.path.getmtime)

        ext = os.path.splitext(latest_image)[1]
        target_path = os.path.join(output_dir, filename)
        if latest_image != target_path:
            os.rename(latest_image, target_path)

        print(f"  [OK] Image saved to: {target_path}")
        return target_path

    except subprocess.TimeoutExpired:
        raise RuntimeError("OpenCLI-Gemini timeout after 660s")
    except FileNotFoundError:
        raise RuntimeError("OpenCLI tool not found. Install via: npm install -g @jackwener/opencli")
    except Exception as exc:
        raise RuntimeError(f"OpenCLI-Gemini error: {exc}")

def generate(prompt: str,
             aspect_ratio: str = "1:1", image_size: str = "1K",
             output_dir: str = None, filename: str = None,
             model: str = None, max_retries: int = MAX_RETRIES) -> str:
    """Generate an image with retries using the OpenCLI-Gemini backend."""

    if not _check_opencli_available():
        raise RuntimeError(
            "OpenCLI tool not found. Please install it first:\n"
            "  npm install -g @jackwener/opencli"
        )

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return _generate_image(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                output_dir=output_dir,
                filename=filename,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            delay = retry_delay(attempt, rate_limited=False)
            print(f"\n  [WARN] Error: {exc}. Retrying in {delay}s...")
            time.sleep(delay)

    raise RuntimeError(f"Failed after {max_retries + 1} attempts. Last error: {last_error}")
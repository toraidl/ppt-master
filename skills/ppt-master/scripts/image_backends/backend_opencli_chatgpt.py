#!/usr/bin/env python3
"""
OpenCLI-ChatGPT image generation backend.

Uses opencli tool to call ChatGPT web for image generation.
Requires opencli CLI tool installed.

Configuration keys:
  (None - uses opencli chatgpt web adapter via browser automation)
"""

import sys
import subprocess
import os
import time
import glob

if __name__ == "__main__" and any(arg in {"-h", "--help", "help"} for arg in sys.argv[1:]):
    print(__doc__)
    print("Use via: python3 skills/ppt-master/scripts/image_gen.py \"prompt\" --backend opencli-chatgpt")
    raise SystemExit(0)

from image_backends.backend_common import (
    MAX_RETRIES,
    retry_delay,
)

# ChatGPT web image generation does not expose aspect ratio control.
# We accept all ratios (ignore) so callers don't need to special-case.
VALID_ASPECT_RATIOS = [
    "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
    "4:5", "5:4", "21:9", "1:4", "1:8", "4:1", "8:1",
]

VALID_IMAGE_SIZES = ["512px", "1K", "2K", "4K"]


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
    Image generation via opencli ChatGPT web adapter.

    Note: aspect_ratio and image_size are ignored — ChatGPT web does not
    expose resolution control through this interface.
    """
    output_dir = output_dir or os.path.expanduser("~/Pictures/chatgpt")
    os.makedirs(output_dir, exist_ok=True)

    if filename:
        if not filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            filename = f"{filename}.png"
    else:
        filename = "chatgpt_image.png"

    cmd = [
        "opencli", "chatgpt", "image", prompt,
        "--op", output_dir,
        "--timeout", "300",
        "--site-session", "ephemeral",
        "--window", "background",
    ]

    print("[OpenCLI-ChatGPT]")
    print(f"  Prompt:       {prompt[:120]}{'...' if len(prompt) > 120 else ''}")
    print(f"  Output Dir:   {output_dir}")
    print()
    print("  [..] Generating...", end="", flush=True)
    start = time.time()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=360)
        elapsed = time.time() - start
        print(f"\n  [DONE] Completed ({elapsed:.1f}s)")

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Unknown error"
            raise RuntimeError(f"OpenCLI-ChatGPT generation failed: {error_msg}")

        output = result.stdout.strip()
        print(f"  [INFO] {output[:200]}")

        if "no-images" in output.lower() or "no images" in output.lower():
            raise RuntimeError(
                "ChatGPT web failed to generate images. "
                "Check if ChatGPT web is accessible or quota exceeded."
            )

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
        raise RuntimeError("OpenCLI-ChatGPT timeout after 360s")
    except FileNotFoundError:
        raise RuntimeError(
            "OpenCLI tool not found. Install via: npm install -g @jackwener/opencli"
        )
    except Exception as exc:
        raise RuntimeError(f"OpenCLI-ChatGPT error: {exc}")


def generate(prompt: str,
             aspect_ratio: str = "1:1", image_size: str = "1K",
             output_dir: str = None, filename: str = None,
             model: str = None, max_retries: int = MAX_RETRIES) -> str:
    """Generate an image with retries using the OpenCLI-ChatGPT backend."""

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

    raise RuntimeError(
        f"Failed after {max_retries + 1} attempts. Last error: {last_error}"
    )

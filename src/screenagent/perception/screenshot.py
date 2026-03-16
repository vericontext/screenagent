"""Screenshot capture using macOS screencapture CLI."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from screenagent.types import Rect

# Anthropic API image size limit
MAX_IMAGE_BYTES = 3_500_000  # conservative limit for Anthropic API (5 MB max)


def _downscale_png(data: bytes, max_bytes: int = MAX_IMAGE_BYTES) -> bytes:
    """Downscale a PNG using sips if it exceeds *max_bytes*."""
    if len(data) <= max_bytes:
        return data

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        Path(tmp_path).write_bytes(data)
        # Halve the width; sips keeps aspect ratio with --resampleWidth
        for _ in range(5):  # up to 5 halvings (1/32 original)
            try:
                # Read current width
                result = subprocess.run(
                    ["sips", "-g", "pixelWidth", tmp_path],
                    capture_output=True, text=True, timeout=10,
                )
                width = int(result.stdout.strip().split()[-1])
            except (ValueError, IndexError, subprocess.TimeoutExpired):
                # sips failed or returned unexpected output — return original
                return data
            new_width = max(width // 2, 800)
            subprocess.run(
                ["sips", "--resampleWidth", str(new_width), tmp_path],
                capture_output=True, timeout=10,
            )
            resized = Path(tmp_path).read_bytes()
            if len(resized) <= max_bytes:
                return resized
            if new_width <= 800:
                break
        # Return whatever we got after max halvings
        return Path(tmp_path).read_bytes()
    except Exception:
        # Any unexpected error — return original data rather than crashing
        return data
    finally:
        Path(tmp_path).unlink(missing_ok=True)


class ScreenshotPerceiver:
    def screenshot(self, region: Rect | None = None) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cmd = ["screencapture", "-x", "-t", "png"]
            if region:
                cmd.extend([
                    "-R",
                    f"{region.x:.0f},{region.y:.0f},{region.width:.0f},{region.height:.0f}",
                ])
            cmd.append(tmp_path)
            subprocess.run(cmd, check=True, capture_output=True, timeout=10)
            raw = Path(tmp_path).read_bytes()
            return _downscale_png(raw)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

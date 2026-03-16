"""Screenshot capture using macOS screencapture CLI."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from screenagent.types import Rect


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
            return Path(tmp_path).read_bytes()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

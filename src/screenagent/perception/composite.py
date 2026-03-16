"""CompositePerceiver — AX → CDP → screenshot fallback chain."""

from __future__ import annotations

import asyncio
import logging

from screenagent.types import Rect, ScreenState, UIElement
from screenagent.perception.ax import AXPerceiver
from screenagent.perception.cdp import CDPPerceiver
from screenagent.perception.screenshot import ScreenshotPerceiver

logger = logging.getLogger(__name__)

BROWSER_APPS = {"Google Chrome", "Chromium", "Microsoft Edge", "Brave Browser", "Arc"}


class CompositePerceiver:
    def __init__(self, cdp_port: int = 9222):
        self._ax = AXPerceiver()
        self._cdp = CDPPerceiver(port=cdp_port)
        self._screenshot = ScreenshotPerceiver()
        self._cdp_connected = False
        self._cdp_failed = False
        self._cdp_port = cdp_port

    async def _ensure_cdp(self) -> bool:
        if self._cdp_connected:
            return True
        if self._cdp_failed:
            return False
        try:
            await self._cdp.connect(self._cdp_port)
            self._cdp_connected = True
            self._was_ever_connected = True
            return True
        except ConnectionError:
            # Only mark as permanently failed on first connect attempt.
            # If we were previously connected (_cdp_connected was set then cleared),
            # allow future retry.
            if not hasattr(self, '_was_ever_connected'):
                self._cdp_failed = True
            logger.debug("CDP not available, skipping browser perception")
            return False

    def perceive(self, app_name: str, include_screenshot: bool = True) -> ScreenState:
        """Synchronous entry point — runs async parts internally."""
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._perceive_async(app_name, include_screenshot))
                return future.result()
        else:
            return asyncio.run(self._perceive_async(app_name, include_screenshot))

    async def _perceive_async(self, app_name: str, include_screenshot: bool) -> ScreenState:
        state = ScreenState(app_name=app_name)

        # Try AX tree
        try:
            state.ui_tree = self._ax.get_ui_tree(app_name)
        except PermissionError as e:
            logger.warning("AX permission error: %s", e)
        except Exception as e:
            logger.warning("AX error: %s", e)

        # Try CDP for browser apps
        if app_name in BROWSER_APPS:
            if await self._ensure_cdp():
                try:
                    state.url = await self._cdp.get_page_url()
                    state.dom_summary = await self._cdp.get_dom()
                except Exception as e:
                    logger.warning("CDP error: %s — will retry on next perception", e)
                    self._cdp_connected = False

        # Screenshot fallback / supplement
        if include_screenshot:
            try:
                if app_name in BROWSER_APPS and self._cdp_connected:
                    state.screenshot_png = await self._cdp.capture_screenshot()
                else:
                    state.screenshot_png = self._screenshot.screenshot()
            except Exception as e:
                logger.warning("CDP screenshot error, falling back to screencapture: %s", e)
                try:
                    state.screenshot_png = self._screenshot.screenshot()
                except Exception as e2:
                    logger.warning("Screenshot error: %s", e2)

        return state

    @property
    def cdp(self) -> CDPPerceiver:
        return self._cdp

    def screenshot(self, region: Rect | None = None) -> bytes:
        return self._screenshot.screenshot(region)

"""CDPPerceiver — Chrome DevTools Protocol perception via websockets."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any
from urllib.request import urlopen

import websockets

logger = logging.getLogger(__name__)


class CDPPerceiver:
    def __init__(self, port: int = 9222):
        self._port = port
        self._ws: Any = None
        self._msg_id = 0

    async def connect(self, port: int | None = None, *, max_retries: int = 5) -> None:
        if port is not None:
            self._port = port

        last_error: Exception | None = None
        for attempt in range(max_retries):
            if attempt > 0:
                delay = 2 ** (attempt - 1)  # 1, 2, 4, 8, 16
                logger.info("CDP connect retry %d/%d in %ds...", attempt + 1, max_retries, delay)
                await asyncio.sleep(delay)

            targets_url = f"http://localhost:{self._port}/json"
            try:
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(None, lambda: urlopen(targets_url, timeout=5).read())
                targets = json.loads(resp)
                # Find first page target
                page_target = next(
                    (t for t in targets if t.get("type") == "page"),
                    None,
                )
                if page_target is None:
                    raise RuntimeError("No page target found in Chrome DevTools")
                ws_url = page_target["webSocketDebuggerUrl"]
            except Exception as e:
                last_error = e
                logger.debug("CDP connect attempt %d failed: %s", attempt + 1, e)
                continue

            self._ws = await websockets.connect(
                ws_url,
                max_size=50 * 1024 * 1024,
                ping_interval=30,
                ping_timeout=60,
            )
            logger.info("Connected to Chrome DevTools page target at %s", ws_url)
            return

        raise ConnectionError(
            f"Cannot connect to Chrome DevTools on port {self._port} after {max_retries} attempts. "
            f"Launch Chrome with: /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome "
            f"--remote-debugging-port={self._port} --user-data-dir=/tmp/chrome-debug-profile"
        ) from last_error

    async def _reconnect(self) -> None:
        """Reconnect to a page target (e.g. after navigation changes the page)."""
        self._ws = None
        await self.connect(self._port)

    async def _send(self, method: str, params: dict | None = None) -> dict:
        if self._ws is None:
            raise ConnectionError("Not connected. Call connect() first.")
        self._msg_id += 1
        msg_id = self._msg_id
        payload = {"id": msg_id, "method": method, "params": params or {}}
        try:
            await self._ws.send(json.dumps(payload))
        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket closed, reconnecting...")
            await self._reconnect()
            return await self._send(method, params)

        while True:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=30)
            except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError):
                logger.info("WebSocket closed/timeout during recv, reconnecting...")
                await self._reconnect()
                return await self._send(method, params)
            data = json.loads(raw)
            if data.get("id") == msg_id:
                if "error" in data:
                    raise RuntimeError(f"CDP error: {data['error']}")
                return data.get("result", {})

    async def get_dom(self) -> str:
        doc = await self._send("DOM.getDocument", {"depth": -1})
        root = doc.get("root", {})
        return self._flatten_node(root)

    def _flatten_node(self, node: dict, depth: int = 0, max_depth: int = 8) -> str:
        if depth > max_depth:
            return ""
        indent = "  " * depth
        name = node.get("nodeName", "")
        node_type = node.get("nodeType", 0)

        # Text node
        if node_type == 3:
            value = (node.get("nodeValue") or "").strip()
            if value:
                return f"{indent}\"{value[:100]}\"\n"
            return ""

        attrs = node.get("attributes", [])
        attr_str = ""
        if attrs:
            pairs = [f'{attrs[i]}="{attrs[i+1]}"' for i in range(0, len(attrs) - 1, 2)]
            interesting = [p for p in pairs if any(
                p.startswith(a) for a in ("id=", "class=", "href=", "role=", "aria-", "type=", "name=", "placeholder=")
            )]
            if interesting:
                attr_str = " " + " ".join(interesting)

        lines = [f"{indent}<{name}{attr_str}>\n"]
        for child in node.get("children", []):
            lines.append(self._flatten_node(child, depth + 1, max_depth))
        return "".join(lines)

    async def evaluate_js(self, expression: str) -> str:
        result = await self._send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
        })
        val = result.get("result", {}).get("value")
        return str(val) if val is not None else ""

    async def get_page_url(self) -> str:
        return await self.evaluate_js("window.location.href")

    async def capture_screenshot(self) -> bytes:
        result = await self._send("Page.captureScreenshot", {"format": "png"})
        return base64.b64decode(result["data"])

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None

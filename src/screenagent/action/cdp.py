"""CDPActor — browser actions via Chrome DevTools Protocol."""

from __future__ import annotations

import asyncio
from typing import Any

from screenagent.perception.cdp import CDPPerceiver


class CDPActor:
    def __init__(self, cdp: CDPPerceiver):
        self._cdp = cdp

    async def navigate(self, url: str) -> None:
        # Enable Page events for load detection
        await self._cdp._send("Page.enable")
        await self._cdp._send("Page.navigate", {"url": url})
        # Wait for page load
        await asyncio.sleep(2)

    async def click_element(self, selector: str) -> None:
        js = f"""
        (() => {{
            const el = document.querySelector({selector!r});
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {{
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2
            }};
        }})()
        """
        result = await self._cdp._send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True,
        })
        value = result.get("result", {}).get("value")
        if value is None:
            raise RuntimeError(f"Element not found: {selector}")

        x, y = value["x"], value["y"]

        # Dispatch mouse events via CDP
        for event_type in ("mousePressed", "mouseReleased"):
            await self._cdp._send("Input.dispatchMouseEvent", {
                "type": event_type,
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            })

    async def type_in_element(self, selector: str, text: str) -> None:
        # Focus the element
        await self._cdp._send("Runtime.evaluate", {
            "expression": f"document.querySelector({selector!r}).focus()",
        })
        await asyncio.sleep(0.1)

        # Type via Input.dispatchKeyEvent
        for char in text:
            await self._cdp._send("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "text": char,
                "key": char,
                "unmodifiedText": char,
            })
            await self._cdp._send("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "key": char,
            })
            await asyncio.sleep(0.03)

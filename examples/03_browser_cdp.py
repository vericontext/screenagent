"""Browser automation via Chrome DevTools Protocol.

Requires: Chrome running with --remote-debugging-port=9222
    /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

No API key required.
"""

import asyncio

from screenagent.perception.cdp import CDPPerceiver
from screenagent.action.cdp import CDPActor


async def main():
    cdp = CDPPerceiver(port=9222)
    await cdp.connect()

    actor = CDPActor(cdp)

    # Navigate to a page
    await actor.navigate("https://example.com")

    # Read current URL
    url = await cdp.get_page_url()
    print(f"URL: {url}")

    # Get DOM summary
    dom = await cdp.get_dom()
    print(f"DOM: {dom[:500]}...")

    # Evaluate JavaScript
    title = await cdp.evaluate_js("document.title")
    print(f"Title: {title}")

    # Capture page screenshot
    png = await cdp.capture_screenshot()
    print(f"Screenshot: {len(png)} bytes")


if __name__ == "__main__":
    asyncio.run(main())

"""CGEventActor — mouse and keyboard input via Quartz CGEvent APIs."""

from __future__ import annotations

import time

from Quartz import (
    CGEventCreate,
    CGEventCreateMouseEvent,
    CGEventCreateKeyboardEvent,
    CGEventCreateScrollWheelEvent,
    CGEventPost,
    CGEventKeyboardSetUnicodeString,
    CGPointMake,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseUp,
    kCGEventMouseMoved,
    kCGHIDEventTap,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskShift,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskControl,
    kCGScrollEventUnitPixel,
)
from Quartz import CGEventSetFlags

MODIFIER_MAP: dict[str, int] = {
    "command": kCGEventFlagMaskCommand,
    "cmd": kCGEventFlagMaskCommand,
    "shift": kCGEventFlagMaskShift,
    "option": kCGEventFlagMaskAlternate,
    "alt": kCGEventFlagMaskAlternate,
    "control": kCGEventFlagMaskControl,
    "ctrl": kCGEventFlagMaskControl,
}

# Common virtual keycodes
KEYCODE_MAP: dict[str, int] = {
    "return": 0x24, "enter": 0x24,
    "tab": 0x30,
    "space": 0x31,
    "delete": 0x33, "backspace": 0x33,
    "escape": 0x35, "esc": 0x35,
    "left": 0x7B, "right": 0x7C,
    "down": 0x7D, "up": 0x7E,
    "a": 0x00, "b": 0x0B, "c": 0x08, "d": 0x02, "e": 0x0E,
    "f": 0x03, "g": 0x05, "h": 0x04, "i": 0x22, "j": 0x26,
    "k": 0x28, "l": 0x25, "m": 0x2E, "n": 0x2D, "o": 0x1F,
    "p": 0x23, "q": 0x0C, "r": 0x0F, "s": 0x01, "t": 0x11,
    "u": 0x20, "v": 0x09, "w": 0x0D, "x": 0x07, "y": 0x10,
    "z": 0x06,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76,
    "f5": 0x60, "f6": 0x61, "f7": 0x62, "f8": 0x64,
}


class CGEventActor:
    def click(self, x: float, y: float) -> None:
        point = CGPointMake(x, y)
        down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
        up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
        CGEventPost(kCGHIDEventTap, down)
        time.sleep(0.05)
        CGEventPost(kCGHIDEventTap, up)

    def double_click(self, x: float, y: float) -> None:
        point = CGPointMake(x, y)
        for click_count in (1, 2):
            down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
            up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
            # Set click count for double-click recognition
            from Quartz import CGEventSetIntegerValueField, kCGMouseEventClickState
            CGEventSetIntegerValueField(down, kCGMouseEventClickState, click_count)
            CGEventSetIntegerValueField(up, kCGMouseEventClickState, click_count)
            CGEventPost(kCGHIDEventTap, down)
            time.sleep(0.05)
            CGEventPost(kCGHIDEventTap, up)
            if click_count == 1:
                time.sleep(0.05)

    def type_text(self, text: str) -> None:
        for char in text:
            event_down = CGEventCreateKeyboardEvent(None, 0, True)
            CGEventKeyboardSetUnicodeString(event_down, len(char), char)
            event_up = CGEventCreateKeyboardEvent(None, 0, False)
            CGEventKeyboardSetUnicodeString(event_up, len(char), char)
            CGEventPost(kCGHIDEventTap, event_down)
            CGEventPost(kCGHIDEventTap, event_up)
            time.sleep(0.03)

    def key_press(self, key: str, modifiers: list[str] | None = None) -> None:
        keycode = KEYCODE_MAP.get(key.lower())
        if keycode is None:
            raise ValueError(f"Unknown key: {key!r}. Known keys: {sorted(KEYCODE_MAP.keys())}")

        flags = 0
        for mod in (modifiers or []):
            flag = MODIFIER_MAP.get(mod.lower())
            if flag is None:
                raise ValueError(f"Unknown modifier: {mod!r}. Known: {sorted(MODIFIER_MAP.keys())}")
            flags |= flag

        down = CGEventCreateKeyboardEvent(None, keycode, True)
        up = CGEventCreateKeyboardEvent(None, keycode, False)
        if flags:
            CGEventSetFlags(down, flags)
            CGEventSetFlags(up, flags)
        CGEventPost(kCGHIDEventTap, down)
        time.sleep(0.05)
        CGEventPost(kCGHIDEventTap, up)

    def scroll(self, x: float, y: float, dx: float, dy: float) -> None:
        # Move mouse to position first
        point = CGPointMake(x, y)
        move = CGEventCreateMouseEvent(None, kCGEventMouseMoved, point, 0)
        CGEventPost(kCGHIDEventTap, move)
        time.sleep(0.05)

        scroll_event = CGEventCreateScrollWheelEvent(
            None, kCGScrollEventUnitPixel, 2, int(dy), int(dx)
        )
        CGEventPost(kCGHIDEventTap, scroll_event)

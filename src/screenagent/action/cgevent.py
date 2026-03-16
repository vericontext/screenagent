"""CGEventActor — mouse and keyboard input via Quartz CGEvent APIs."""

from __future__ import annotations

import logging
import subprocess
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
    "caps_lock": 0x39, "capslock": 0x39,
    "left": 0x7B, "right": 0x7C,
    "down": 0x7D, "up": 0x7E,
    "a": 0x00, "b": 0x0B, "c": 0x08, "d": 0x02, "e": 0x0E,
    "f": 0x03, "g": 0x05, "h": 0x04, "i": 0x22, "j": 0x26,
    "k": 0x28, "l": 0x25, "m": 0x2E, "n": 0x2D, "o": 0x1F,
    "p": 0x23, "q": 0x0C, "r": 0x0F, "s": 0x01, "t": 0x11,
    "u": 0x20, "v": 0x09, "w": 0x0D, "x": 0x07, "y": 0x10,
    "z": 0x06,
    "0": 0x1D, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15,
    "5": 0x17, "6": 0x16, "7": 0x1A, "8": 0x1C, "9": 0x19,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76,
    "f5": 0x60, "f6": 0x61, "f7": 0x62, "f8": 0x64,
    # Punctuation / symbol keys
    "-": 0x1B, "=": 0x18, "[": 0x21, "]": 0x1E,
    ";": 0x29, "'": 0x27, ",": 0x2B, ".": 0x2F,
    "/": 0x2C, "`": 0x32, "\\": 0x2A,
}

# Characters that require Shift to type (mapped to the base key)
SHIFT_CHARS: dict[str, str] = {
    "+": "=", "_": "-", "{": "[", "}": "]",
    ":": ";", '"': "'", "<": ",", ">": ".",
    "?": "/", "~": "`", "|": "\\",
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
    "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
}


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Input-source helpers via Carbon TIS (ctypes)
# ---------------------------------------------------------------------------
import ctypes
import ctypes.util

_carbon_path = ctypes.util.find_library("Carbon")
_carbon = ctypes.cdll.LoadLibrary(_carbon_path) if _carbon_path else None

_cf_path = ctypes.util.find_library("CoreFoundation")
_cf = ctypes.cdll.LoadLibrary(_cf_path) if _cf_path else None

if _carbon and _cf:
    # CFString helpers
    _cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    _cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    _cf.CFStringGetCStringPtr.restype = ctypes.c_char_p
    _cf.CFStringGetCStringPtr.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _cf.CFRelease.argtypes = [ctypes.c_void_p]
    _cf.CFDictionaryCreate.restype = ctypes.c_void_p
    _cf.CFDictionaryCreate.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
    ]
    _cf.CFArrayGetCount.restype = ctypes.c_long
    _cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    _cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    _cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]

    # TIS functions
    _carbon.TISCopyCurrentKeyboardInputSource.restype = ctypes.c_void_p
    _carbon.TISGetInputSourceProperty.restype = ctypes.c_void_p
    _carbon.TISGetInputSourceProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _carbon.TISSelectInputSource.restype = ctypes.c_int32
    _carbon.TISSelectInputSource.argtypes = [ctypes.c_void_p]
    _carbon.TISCreateInputSourceList.restype = ctypes.c_void_p
    _carbon.TISCreateInputSourceList.argtypes = [ctypes.c_void_p, ctypes.c_bool]

    # Property key constant
    _kTISPropertyInputSourceID = ctypes.c_void_p.in_dll(_carbon, "kTISPropertyInputSourceID")

_kCFStringEncodingUTF8 = 0x08000100

_ENGLISH_SOURCE_IDS = ("com.apple.keylayout.ABC", "com.apple.keylayout.US")


def _get_input_source_id() -> str | None:
    """Get the current keyboard input source ID via Carbon TIS."""
    if not _carbon or not _cf:
        return None
    try:
        source = _carbon.TISCopyCurrentKeyboardInputSource()
        if not source:
            return None
        cf_id = _carbon.TISGetInputSourceProperty(source, _kTISPropertyInputSourceID)
        if not cf_id:
            _cf.CFRelease(source)
            return None
        raw = _cf.CFStringGetCStringPtr(cf_id, _kCFStringEncodingUTF8)
        _cf.CFRelease(source)
        return raw.decode("utf-8") if raw else None
    except Exception:
        return None


def _select_input_source(source_id: str) -> None:
    """Select a keyboard input source by ID via Carbon TIS."""
    if not _carbon or not _cf:
        return
    try:
        cf_key = _kTISPropertyInputSourceID.value
        cf_val = _cf.CFStringCreateWithCString(None, source_id.encode(), _kCFStringEncodingUTF8)
        if not cf_val:
            return
        keys = (ctypes.c_void_p * 1)(cf_key)
        vals = (ctypes.c_void_p * 1)(cf_val)
        filter_dict = _cf.CFDictionaryCreate(None, keys, vals, 1, None, None)
        if not filter_dict:
            _cf.CFRelease(cf_val)
            return
        source_list = _carbon.TISCreateInputSourceList(filter_dict, False)
        # Release filter_dict and cf_val only after TIS is done using them
        _cf.CFRelease(filter_dict)
        _cf.CFRelease(cf_val)
        if not source_list:
            return
        if _cf.CFArrayGetCount(source_list) > 0:
            source = _cf.CFArrayGetValueAtIndex(source_list, 0)
            _carbon.TISSelectInputSource(source)
        _cf.CFRelease(source_list)
    except Exception:
        pass


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
        # ASCII 텍스트인데 한글 입력 중이면 → 영문 전환 후 타이핑, 끝나면 복원
        prev_source: str | None = None
        if text.isascii() and any(c.isalpha() for c in text):
            cur = _get_input_source_id()
            if cur and not any(eid in cur for eid in _ENGLISH_SOURCE_IDS):
                logger.info("Switching input source from %s to ABC for ASCII text", cur)
                _select_input_source("com.apple.keylayout.ABC")
                time.sleep(0.05)
                prev_source = cur

        for char in text:
            # Check if this is a shifted symbol (e.g. '!' → Shift+'1')
            base_char = SHIFT_CHARS.get(char)
            if base_char is not None:
                # Use keycode 0 + Unicode string to avoid apps (e.g. Calculator)
                # interpreting the raw keycode (e.g. 0x18 for '=' when typing '+')
                down = CGEventCreateKeyboardEvent(None, 0, True)
                up = CGEventCreateKeyboardEvent(None, 0, False)
                CGEventKeyboardSetUnicodeString(down, len(char), char)
                CGEventKeyboardSetUnicodeString(up, len(char), char)
                CGEventPost(kCGHIDEventTap, down)
                time.sleep(0.02)
                CGEventPost(kCGHIDEventTap, up)
                time.sleep(0.03)
                continue

            # Check for direct keycode match (a-z, 0-9, punctuation)
            lower = char.lower()
            keycode = KEYCODE_MAP.get(lower)
            if keycode is not None:
                need_shift = char.isupper()
                down = CGEventCreateKeyboardEvent(None, keycode, True)
                up = CGEventCreateKeyboardEvent(None, keycode, False)
                if need_shift:
                    CGEventSetFlags(down, kCGEventFlagMaskShift)
                    CGEventSetFlags(up, kCGEventFlagMaskShift)
                CGEventPost(kCGHIDEventTap, down)
                time.sleep(0.02)
                CGEventPost(kCGHIDEventTap, up)
            else:
                # Unicode fallback for characters without a keycode (e.g. emoji, CJK)
                down = CGEventCreateKeyboardEvent(None, 0, True)
                CGEventKeyboardSetUnicodeString(down, len(char), char)
                up = CGEventCreateKeyboardEvent(None, 0, False)
                CGEventKeyboardSetUnicodeString(up, len(char), char)
                CGEventPost(kCGHIDEventTap, down)
                CGEventPost(kCGHIDEventTap, up)
            time.sleep(0.03)

        # Restore previous input source if we switched
        if prev_source:
            logger.info("Restoring input source to %s", prev_source)
            _select_input_source(prev_source)

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

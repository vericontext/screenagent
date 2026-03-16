"""Core data types for screenagent."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height


@dataclass
class UIElement:
    role: str
    title: str = ""
    value: str = ""
    rect: Rect | None = None
    element_id: str = ""
    children: list[UIElement] = field(default_factory=list)

    def to_text(self, indent: int = 0, max_siblings: int = 5) -> str:
        prefix = "  " * indent
        parts = [self.role]
        if self.title:
            parts.append(f'"{self.title}"')
        if self.value:
            parts.append(f"value={self.value!r}")
        if self.rect:
            parts.append(f"({self.rect.x:.0f},{self.rect.y:.0f} {self.rect.width:.0f}x{self.rect.height:.0f})")
        line = f"{prefix}{' '.join(parts)}"
        lines = [line]
        if len(self.children) > max_siblings:
            for child in self.children[:3]:
                lines.append(child.to_text(indent + 1, max_siblings))
            remaining = len(self.children) - 3
            sample_role = self.children[3].role
            lines.append(f"{'  ' * (indent + 1)}... and {remaining} more {sample_role} elements")
        else:
            for child in self.children:
                lines.append(child.to_text(indent + 1, max_siblings))
        return "\n".join(lines)


@dataclass
class ScreenState:
    ui_tree: UIElement | None = None
    screenshot_png: bytes | None = None
    url: str | None = None
    dom_summary: str | None = None
    app_name: str = ""

    def to_text(self) -> str:
        parts: list[str] = []
        if self.app_name:
            parts.append(f"App: {self.app_name}")
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.ui_tree:
            parts.append(f"UI Tree:\n{self.ui_tree.to_text()}")
        if self.dom_summary:
            parts.append(f"DOM:\n{self.dom_summary}")
        return "\n\n".join(parts)


@dataclass
class ToolResult:
    output: str = ""
    error: str = ""
    screenshot_png: bytes | None = None
    done: bool = False


@dataclass
class AgentResult:
    """Structured result from an Agent.run() call."""

    summary: str
    steps: int = 0
    success: bool = True

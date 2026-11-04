"""Braille-dot canvas: each terminal cell holds a 2x4 grid of dots."""

from typing import Optional

from rich.text import Text

# Braille dot bit for (x, y) inside a 2x4 cell
_BITS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))


class Canvas:
    """Draw dots and lines in dot coordinates (width*2 x height*4), render as rich Text."""

    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.bits = [[0] * width for _ in range(height)]
        self.style: list = [[None] * width for _ in range(height)]
        self.prio = [[0] * width for _ in range(height)]
        self.chars: dict[tuple[int, int], tuple[str, Optional[str]]] = {}

    def copy(self) -> "Canvas":
        c = Canvas(self.width, self.height)
        c.bits = [row[:] for row in self.bits]
        c.style = [row[:] for row in self.style]
        c.prio = [row[:] for row in self.prio]
        c.chars = dict(self.chars)
        return c

    def dot(self, x: float, y: float, style: Optional[str], prio: int = 0) -> None:
        """Set one dot. When layers share a cell, the higher priority picks its colour."""
        x, y = int(x), int(y)
        if 0 <= x < self.width * 2 and 0 <= y < self.height * 4:
            cx, cy = x // 2, y // 4
            self.bits[cy][cx] |= _BITS[x % 2][y % 4]
            if prio >= self.prio[cy][cx]:
                self.style[cy][cx], self.prio[cy][cx] = style, prio

    def line(self, x0: float, y0: float, x1: float, y1: float, style: Optional[str], prio: int = 0) -> None:
        w, h = self.width * 2, self.height * 4
        if (x0 < 0 and x1 < 0) or (y0 < 0 and y1 < 0) or (x0 >= w and x1 >= w) or (y0 >= h and y1 >= h):
            return  # fully off-screen
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(n + 1):
            t = i / n
            self.dot(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, style, prio)

    def overlay(self, other: "Canvas") -> None:
        """Replace this canvas's cells with every non-empty cell of `other`."""
        for y in range(self.height):
            for x in range(self.width):
                if other.bits[y][x]:
                    self.bits[y][x], self.style[y][x] = other.bits[y][x], other.style[y][x]

    def text(self, cx: int, cy: int, s: str, style: Optional[str]) -> None:
        """Write plain characters in cell coordinates (labels, icons)."""
        for i, ch in enumerate(s):
            if 0 <= cx + i < self.width and 0 <= cy < self.height:
                self.chars[(cx + i, cy)] = (ch, style)

    def to_text(self) -> Text:
        out = Text()
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) in self.chars:
                    out.append(*self.chars[(x, y)])
                else:
                    out.append(chr(0x2800 + self.bits[y][x]), self.style[y][x])
            if y < self.height - 1:
                out.append("\n")
        return out

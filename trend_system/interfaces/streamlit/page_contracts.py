from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class StreamlitPageContext:
    settings: dict[str, Any]
    language: str
    config_path: str


@dataclass(frozen=True)
class StreamlitPageSpec:
    key: str
    title_zh: str
    title_en: str
    renderer: Callable[[StreamlitPageContext], None]
    enabled: bool = True
    notes: str | None = None

    def title(self, language: str) -> str:
        return self.title_en if language == "en" else self.title_zh

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tomllib


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any]
    path: Path

    @property
    def home_timezone(self) -> str:
        return self.raw["profile"]["home_timezone"]

    @property
    def primary_symbol(self) -> str:
        return self.raw["signals"]["primary"]

    @property
    def vix_symbol(self) -> str:
        return self.raw["signals"]["volatility"]

    @property
    def price_field(self) -> str:
        return self.raw["signals"].get("price_field", "Close")


def load_settings(path: str | Path) -> Settings:
    config_path = Path(path)
    with config_path.open("rb") as fh:
        raw = tomllib.load(fh)
    return Settings(raw=raw, path=config_path)


def required_symbols(settings: Settings) -> list[str]:
    symbols = [settings.primary_symbol, settings.vix_symbol]
    symbols.extend(settings.raw["signals"].get("confirm", []))
    symbols.extend(settings.raw["signals"].get("defensive", []))
    return list(dict.fromkeys(symbols))

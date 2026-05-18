from __future__ import annotations

import base64
from html import escape
import zlib


MAP_WIDTH = 120
MAP_HEIGHT = 96
REGION_BOUNDS: tuple[tuple[str, int, int, int, int], ...] = (
    ("us", 5, 42, 6, 42),
    ("south_america", 25, 49, 40, 82),
    ("eu", 48, 66, 8, 34),
    ("middle_east", 62, 78, 24, 50),
    ("asia", 70, 106, 8, 50),
    ("asx", 86, 113, 58, 86),
    ("nzx", 108, 120, 70, 90),
)

# Generated from topojson/world-atlas land-110m, derived from Natural Earth.
# Antarctica is omitted so the decorative layer reads as a dashboard world map.
WORLD_MAP_PAYLOAD = (
    "eNrdmUdywzAMRfc8Bfb//vdLxhbFhvIh0p5JtHCcRMIjClEoEffCdXXfC3M/2rdexHr//HgJliNvSbZwi+RJR/18Peyu/HcB"
    "RZWA1/NNI0r9ptZoQX+dvTgOAdWht9bFWtPlxrZACqcurgrRYLfAGjfL44HplHCrIVtkNtodzNXl9T82bYoBDdeugu1r9hUE"
    "EmzUInIEOmj7st4RoaMjjHt7T6xrQWB3yx0+9h0PC1d2sRF40W4f/N4GpVFXfMuRcDK4ZLw+JlZoSrvQmmdoZBeadrbBYAUn"
    "32e2YzHLXZfBjiCdiqXuGi1wBdnNa+TnBPFJeiCIZhXI783idS1jVLPLSsGMHPQZmFBGnEot4tQjLMymCebPXZjeijTxdxJy"
    "45GDeakT0qX3PXeZKbr9NPvt+ucDHIFMCU6pPNscSMi5SsgGq6tw0Sa70nWREOZOQ8KyrLafQS3dll+vY1A8EMbVJQZJDHqa"
    "+Qb7IwGRJIUZ77Q2N6eKBBBdC4PiQRKK9JmVzNpWs8tQFIyHqCHK1Y4Z4Q/iPUBFwOgM+7CMrCTdingdhkp0/14Ce/P7Q8Yx"
    "Ythl0eENUpQ5WjiKJCja0EtSJEHRFgcKAKygaM6mAdNpCwsIxVopEXR/mMIg54HRewnMLAVxHwDWE97ZU9QBYFcRpvgDAkYP"
    "sAw94JOMIC/aB8jgLBbEUHi0jXsGT7KQ852M58dZGHKw+c5P48a+NhPnT5Vbzpg+CXuU86Iw+QDMjX/4ZZ+ByQGYN3Q8gUk0"
    "oHAwYWHUezjef36Sco+65se/QaMae3Z3hR5cD6hzUL8jIaBll9afaxEb+CRP/jjv2ZD973nD2/UELzkkzYU2iZPd68s4SY5P"
    "B7m5cnGGmm4z5Bh2fd38JXDWvX/ZyFnq0dsKa17uTtJdpZQf+PgvZQ=="
)


def _world_map_rows() -> list[str]:
    text = zlib.decompress(base64.b64decode(WORLD_MAP_PAYLOAD)).decode()
    rows = text.splitlines()
    return (rows + [""] * MAP_HEIGHT)[:MAP_HEIGHT]


WORLD_MAP_ROWS = _world_map_rows()


def _pad_row(row: str) -> str:
    if len(row) >= MAP_WIDTH:
        return row[:MAP_WIDTH]
    return row.ljust(MAP_WIDTH)


def _region_at(row_index: int, column_index: int) -> str | None:
    for region, start, end, row_start, row_end in REGION_BOUNDS:
        if row_start <= row_index < row_end and start <= column_index < end:
            return region
    return None


def build_world_map_text(active_markets: set[str] | None = None, *, repeats: int = 1) -> str:
    rows: list[str] = []
    for _ in range(max(repeats, 1)):
        for row_index, row in enumerate(WORLD_MAP_ROWS):
            padded = _pad_row(row)
            if active_markets is None:
                rows.append(padded.rstrip())
                continue
            chars = [
                char if char.strip() and _region_at(row_index, index) in active_markets else " "
                for index, char in enumerate(padded)
            ]
            rows.append("".join(chars).rstrip())
    return "\n".join(rows)


def build_world_map_markup(active_markets: set[str], *, repeats: int = 1) -> str:
    rows_html = []
    for _ in range(max(repeats, 1)):
        for row_index, row in enumerate(WORLD_MAP_ROWS):
            padded = _pad_row(row)
            cursor = 0
            segments: list[str] = []
            row_regions = sorted(
                (region, start, end)
                for region, start, end, row_start, row_end in REGION_BOUNDS
                if row_start <= row_index < row_end
            )
            for region, start, end in row_regions:
                if start < cursor:
                    continue
                if cursor < start:
                    segments.append(escape(padded[cursor:start]))
                classes = [f"wm-{region}"]
                if region in active_markets:
                    classes.append("active")
                region_text = escape(padded[start:end])
                segments.append(f'<span class="{" ".join(classes)}">{region_text}</span>')
                cursor = end
            if cursor < len(padded):
                segments.append(escape(padded[cursor:]))
            rows_html.append("".join(segments))
    return "\n".join(rows_html)

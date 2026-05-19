"""COBE WebGL globe — 5KB rotating earth, used as fixed background decoration.

Markets are highlighted in Prussian Blue when their trading session is open.
Coordinates are illustrative area samples around major market regions.
"""

from __future__ import annotations

import json


# COBE supports circular markers rather than polygons. These sampled clusters
# make active markets read as soft regional blocks instead of single city pins.
MARKET_REGION_SAMPLES: dict[str, list[tuple[float, float]]] = {
    "us": [
        (49.0, -124.0), (47.0, -103.0), (45.0, -82.0),
        (38.0, -122.0), (39.0, -98.0), (40.5, -74.0),
        (32.0, -117.0), (33.0, -96.0), (34.0, -84.0),
        (26.0, -80.0),
    ],
    "south_america": [
        (5.0, -74.0), (-3.0, -60.0), (-12.0, -77.0),
        (-15.0, -47.0), (-23.5, -46.6), (-30.0, -58.0),
        (-34.6, -58.4), (-33.5, -70.7),
    ],
    "eu": [
        (55.8, -4.3), (51.5, -0.1), (48.9, 2.4),
        (50.1, 8.7), (52.5, 13.4), (45.5, 9.2),
        (40.4, -3.7), (47.4, 8.5), (52.4, 4.9),
    ],
    "middle_east": [
        (25.2, 55.3), (24.7, 46.7), (29.4, 47.9),
        (31.9, 35.9), (35.7, 51.4), (25.3, 51.5),
    ],
    "asia": [
        (35.7, 139.7), (34.7, 135.5), (37.6, 126.9),
        (31.2, 121.5), (22.3, 114.2), (25.0, 121.6),
        (1.4, 103.8), (13.8, 100.5), (19.1, 72.9),
        (28.6, 77.2),
    ],
    "asx": [
        (-12.5, 130.8), (-27.5, 153.0), (-33.9, 151.2),
        (-37.8, 145.0), (-31.9, 115.9), (-34.9, 138.6),
    ],
    "nzx": [
        (-36.8, 174.8), (-38.7, 176.1), (-41.3, 174.8),
        (-43.5, 172.6), (-45.9, 170.5),
    ],
}


def build_cobe_globe_html(
    active_markets: set[str] | None = None,
    *,
    theme: str = "dark",
    size: int = 260,
) -> str:
    """Return a complete HTML document hosting a small spinning COBE globe.

    Args:
        active_markets: region keys (matching `MARKET_REGION_SAMPLES`) currently
            open for trading. Each active region renders a soft Prussian-blue
            block made from clustered COBE markers.
        theme: "dark" or "light".
        size: rendered globe diameter in pixels.
    """
    active = active_markets or set()

    if theme == "dark":
        base_color = [0.58, 0.68, 0.78]
        glow_color = [0.08, 0.13, 0.20]
        marker_color = [0.20, 0.38, 0.56]
        canvas_opacity = 0.62
        shadow_color = "rgba(12, 28, 46, 0.22)"
        page_background = "#1A1D1F"
        dark_flag = 1
        map_brightness = 1.04
        diffuse = 0.76
    else:
        base_color = [0.74, 0.82, 0.90]
        glow_color = [0.83, 0.89, 0.95]
        marker_color = [0.07, 0.22, 0.36]
        canvas_opacity = 0.64
        shadow_color = "rgba(18, 57, 91, 0.14)"
        page_background = "#E6EEF6"
        dark_flag = 0
        map_brightness = 0.92
        diffuse = 0.74

    markers: list[dict] = []
    for market_key, coords in MARKET_REGION_SAMPLES.items():
        if market_key not in active:
            continue
        for lat, lng in coords:
            markers.append({"location": [lat, lng], "size": 0.11})

    config = {
        "devicePixelRatio": 2,
        "width": size * 2,
        "height": size * 2,
        "phi": 0,
        "theta": 0.28,
        "dark": dark_flag,
        "diffuse": diffuse,
        "mapSamples": 12000,
        "mapBrightness": map_brightness,
        "baseColor": base_color,
        "markerColor": marker_color,
        "glowColor": glow_color,
        "markers": markers,
    }
    config_json = json.dumps(config)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{
    margin: 0;
    padding: 0;
    background: {page_background};
    overflow: hidden;
    color-scheme: {"dark" if theme == "dark" else "light"};
  }}
  #cobe-wrap {{
    width: {size}px;
    height: {size}px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    background: {page_background};
  }}
  #cobe-canvas {{
    width: {size}px !important;
    height: {size}px !important;
    display: block;
    opacity: {canvas_opacity};
    filter: drop-shadow(0 0 18px {shadow_color});
  }}
  @media (prefers-reduced-motion: reduce) {{
    #cobe-canvas {{
      opacity: {max(canvas_opacity - 0.12, 0.46)};
    }}
  }}
</style>
</head>
<body>
<div id="cobe-wrap"><canvas id="cobe-canvas"></canvas></div>
<script type="module">
  import createGlobe from 'https://cdn.jsdelivr.net/npm/cobe@0.6.3/+esm';
  const canvas = document.getElementById('cobe-canvas');
  const config = {config_json};
  let phi = 0;
  config.onRender = (state) => {{
    state.phi = phi;
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {{
      phi += 0.0008;
    }}
  }};
  try {{
    createGlobe(canvas, config);
  }} catch (e) {{
    console.error('COBE globe failed to initialise', e);
  }}
</script>
</body>
</html>"""

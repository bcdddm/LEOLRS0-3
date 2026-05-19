from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from trend_system.interfaces.streamlit.shared.preparing import render_preparing
from trend_system.interfaces.streamlit.shared.session_state import SessionKeys


ASSETS_DIR = Path(__file__).resolve().parent / "assets"


@lru_cache(maxsize=1)
def _chart_stylesheet() -> str:
    return (ASSETS_DIR / "tradingview_chart.css").read_text(encoding="utf-8")


def build_lightweight_chart_payload(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    label_resolver: Callable[[str], str],
    line_styles: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    styles = line_styles or {}
    for column in columns:
        if column not in frame.columns:
            continue
        series = frame[column].dropna()
        if series.empty:
            continue
        points = [
            {"time": pd.Timestamp(index).strftime("%Y-%m-%d"), "value": float(value)}
            for index, value in series.items()
        ]
        payload.append(
            {
                "key": column,
                "label": label_resolver(column),
                "style": styles.get(column, "solid"),
                "points": points,
            }
        )
    return payload


def render_lightweight_chart(
    frame: pd.DataFrame,
    columns: list[str],
    title: str,
    *,
    key: str,
    label_resolver: Callable[[str], str],
    line_styles: dict[str, str] | None = None,
) -> None:
    resolved_theme = str(st.session_state.get(SessionKeys.UI_THEME, "light")).strip().lower()
    if resolved_theme not in {"light", "dark"}:
        resolved_theme = "light"
    series_payload = build_lightweight_chart_payload(
        frame,
        columns,
        label_resolver=label_resolver,
        line_styles=line_styles,
    )
    if not series_payload:
        render_preparing(
            st.container(),
            "en",
            title="Preparing",
            detail="Chart surface is waiting for usable series data.",
        )
        return

    chart_id = f"tv-chart-{key}-{resolved_theme}"
    html = f"""
<div class="tv-lightweight-chart-card">
  <div class="tv-lightweight-chart-head">
    <div class="tv-lightweight-chart-title">{_escape_html(title)}</div>
    <div class="tv-lightweight-chart-legend" id="{chart_id}-legend"></div>
  </div>
  <div class="tv-lightweight-chart-wrap">
    <div class="tv-lightweight-chart" id="{chart_id}"></div>
  </div>
  <div class="tv-lightweight-chart-foot">
    Charts powered by <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts</a>
  </div>
</div>
<style>
  {_chart_stylesheet()}
</style>
<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
<script>
  const parentTheme =
    (() => {{
      try {{
        const parentDoc = window.parent?.document;
        const explicitTheme =
          parentDoc?.querySelector(".stApp")?.getAttribute("data-theme")
          || parentDoc?.documentElement?.getAttribute("data-theme");
        if (explicitTheme === "dark" || explicitTheme === "light") return explicitTheme;
        const parentInk = parentDoc ? getComputedStyle(parentDoc.documentElement).getPropertyValue("--leo-ink").trim() : "";
        return parentInk.startsWith("rgba(244") ? "dark" : "light";
      }} catch (error) {{
        return "light";
      }}
    }})();
  document.documentElement.setAttribute("data-theme", parentTheme);
  document.body.setAttribute("data-theme", parentTheme);
  document.documentElement.style.colorScheme = parentTheme;
  document.body.style.colorScheme = parentTheme;
  const seriesPayload = {json.dumps(series_payload)};
  const chartRoot = document.getElementById("{chart_id}");
  const legendRoot = document.getElementById("{chart_id}-legend");
  const lineStyleMap = {{
    solid: "Solid",
    dashed: "Dashed",
    dotted: "Dotted",
  }};
  const palette = ["#2563eb", "#dc2626", "#059669", "#a855f7", "#ea580c", "#0891b2", "#9333ea", "#475569"];

  function createLegendItem(color, label) {{
    const item = document.createElement("div");
    item.className = "tv-lightweight-chart-legend-item";
    const swatch = document.createElement("span");
    swatch.className = "tv-lightweight-chart-legend-swatch";
    swatch.style.background = color;
    const text = document.createElement("span");
    text.textContent = label;
    item.appendChild(swatch);
    item.appendChild(text);
    return item;
  }}

  function formatValue(price) {{
    if (price === null || price === undefined) return "";
    return price.toLocaleString("en-US", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
  }}

  const chartTextColor = parentTheme === "dark" ? "rgba(244, 240, 232, 0.72)" : "rgba(18, 57, 91, 0.78)";
  const chartGridColor = parentTheme === "dark" ? "rgba(174, 143, 84, 0.12)" : "rgba(74, 110, 150, 0.14)";
  const chartBorderColor = parentTheme === "dark" ? "rgba(174, 143, 84, 0.18)" : "rgba(174, 143, 84, 0.22)";
  const chartCrosshairColor = parentTheme === "dark" ? "rgba(174, 143, 84, 0.28)" : "rgba(18, 57, 91, 0.22)";

  const chart = LightweightCharts.createChart(chartRoot, {{
    autoSize: true,
    layout: {{
      background: {{ color: "transparent" }},
      textColor: chartTextColor,
      attributionLogo: true,
    }},
    grid: {{
      vertLines: {{ color: chartGridColor }},
      horzLines: {{ color: chartGridColor }},
    }},
    rightPriceScale: {{
      borderColor: chartBorderColor,
    }},
    timeScale: {{
      borderColor: chartBorderColor,
      timeVisible: false,
      secondsVisible: false,
    }},
    crosshair: {{
      vertLine: {{
        color: chartCrosshairColor,
        width: 1,
      }},
      horzLine: {{
        color: chartCrosshairColor,
        width: 1,
      }},
    }},
    localization: {{
      priceFormatter: formatValue,
    }},
    handleScroll: true,
    handleScale: true,
  }});

  function addCompatibleLineSeries(chartApi, options) {{
    if (typeof chartApi.addSeries === "function" && LightweightCharts.LineSeries) {{
      return chartApi.addSeries(LightweightCharts.LineSeries, options);
    }}
    if (typeof chartApi.addLineSeries === "function") {{
      return chartApi.addLineSeries(options);
    }}
    throw new Error("Unsupported Lightweight Charts API version");
  }}

  const allSeriesItems = [];
  seriesPayload.forEach((seriesConfig, index) => {{
    const color = palette[index % palette.length];
    const lineStyleName = lineStyleMap[seriesConfig.style] || "Solid";
    const series = addCompatibleLineSeries(chart, {{
      color,
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle[lineStyleName] ?? LightweightCharts.LineStyle.Solid,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
    }});
    series.setData(seriesConfig.points);
    const legendItem = createLegendItem(color, seriesConfig.label);
    legendRoot.appendChild(legendItem);
    allSeriesItems.push({{ series, legendItem, label: seriesConfig.label }});
  }});

  chart.subscribeCrosshairMove((param) => {{
    allSeriesItems.forEach((item) => {{
      const textEl = item.legendItem.querySelector("span:last-child");
      if (!textEl) return;
      if (param.time) {{
        const data = param.seriesData.get(item.series);
        const val = data !== undefined ? formatValue(data.value) : "";
        textEl.textContent = val ? `${{item.label}}: ${{val}}` : item.label;
      }} else {{
        textEl.textContent = item.label;
      }}
    }});
  }});

  chart.timeScale().fitContent();
</script>
"""
    components.html(html, height=430)


def _escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

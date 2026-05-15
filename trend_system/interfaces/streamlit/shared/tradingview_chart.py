from __future__ import annotations

import json
from typing import Callable

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


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
    series_payload = build_lightweight_chart_payload(
        frame,
        columns,
        label_resolver=label_resolver,
        line_styles=line_styles,
    )
    if not series_payload:
        st.info("No chart data available.")
        return

    chart_id = f"tv-chart-{key}"
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
  .tv-lightweight-chart-card {{
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 14px;
    padding: 12px 12px 10px;
    background:
      linear-gradient(180deg, rgba(15, 23, 42, 0.02), rgba(15, 23, 42, 0.00)),
      rgba(255, 255, 255, 0.02);
  }}
  .tv-lightweight-chart-head {{
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: flex-start;
    margin-bottom: 8px;
  }}
  .tv-lightweight-chart-title {{
    font-size: 14px;
    font-weight: 700;
    color: inherit;
  }}
  .tv-lightweight-chart-legend {{
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px 12px;
    font-size: 12px;
  }}
  .tv-lightweight-chart-legend-item {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: inherit;
    opacity: 0.88;
  }}
  .tv-lightweight-chart-legend-swatch {{
    width: 14px;
    height: 3px;
    border-radius: 999px;
    display: inline-block;
  }}
  .tv-lightweight-chart-wrap {{
    width: 100%;
    height: 380px;
  }}
  .tv-lightweight-chart {{
    width: 100%;
    height: 100%;
  }}
  .tv-lightweight-chart-foot {{
    margin-top: 8px;
    font-size: 11px;
    opacity: 0.72;
  }}
  .tv-lightweight-chart-foot a {{
    color: inherit;
  }}
</style>
<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
<script>
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

  const chart = LightweightCharts.createChart(chartRoot, {{
    autoSize: true,
    layout: {{
      background: {{ color: "transparent" }},
      textColor: "#64748b",
      attributionLogo: true,
    }},
    grid: {{
      vertLines: {{ color: "rgba(148, 163, 184, 0.16)" }},
      horzLines: {{ color: "rgba(148, 163, 184, 0.16)" }},
    }},
    rightPriceScale: {{
      borderColor: "rgba(148, 163, 184, 0.20)",
    }},
    timeScale: {{
      borderColor: "rgba(148, 163, 184, 0.20)",
      timeVisible: false,
      secondsVisible: false,
    }},
    crosshair: {{
      vertLine: {{
        color: "rgba(37, 99, 235, 0.25)",
        width: 1,
      }},
      horzLine: {{
        color: "rgba(37, 99, 235, 0.25)",
        width: 1,
      }},
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
    legendRoot.appendChild(createLegendItem(color, seriesConfig.label));
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

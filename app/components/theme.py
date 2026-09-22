"""Enterprise design system and stylesheet for Cascading Delay Intelligence.

Human-crafted, production-grade interface modeled after modern engineering tools
(Datadog, Linear, GitHub, Grafana). Focuses on high information density,
precise typography, subtle borders, and zero artificial gimmicks.
"""

from __future__ import annotations

import streamlit as st

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* Global Reset & Typography */
html, body, [class*="css"], .stMarkdown, .stText {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", Roboto, Helvetica, Arial, sans-serif !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

code, kbd, samp, pre, .mono {
    font-family: "JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace !important;
    font-variant-numeric: tabular-nums;
}

/* Production Dark Canvas (GitHub / Linear dark mode) */
.stApp {
    background-color: #0d1117 !important;
    color: #c9d1d9 !important;
}

/* Top Navigation Bar */
header[data-testid="stHeader"] {
    background-color: #0d1117 !important;
    border-bottom: 1px solid #21262d !important;
    height: 3rem !important;
}

/* Minimalist Dark Scrollbars */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: #0d1117;
}
::-webkit-scrollbar-thumb {
    background: #30363d;
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: #484f58;
}

/* Left Navigation Sidebar */
section[data-testid="stSidebar"] {
    background-color: #090d13 !important;
    border-right: 1px solid #21262d !important;
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 1.25rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}

/* Sidebar Section Headers */
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: #6e7681 !important;
    margin-top: 1.25rem !important;
    margin-bottom: 0.4rem !important;
    border-bottom: none !important;
    padding-bottom: 0 !important;
}

/* Sidebar Navigation Items */
div[data-testid="stRadio"] div[role="radiogroup"] {
    gap: 2px !important;
}

div[data-testid="stRadio"] div[role="radiogroup"] > label {
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: 6px !important;
    padding: 6px 10px !important;
    margin-bottom: 1px !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    color: #8b949e !important;
    transition: background 0.12s ease, color 0.12s ease !important;
    cursor: pointer !important;
}

div[data-testid="stRadio"] div[role="radiogroup"] > label:hover {
    background: #161b22 !important;
    color: #f0f6fc !important;
    border-color: #30363d !important;
}

div[data-testid="stRadio"] div[role="radiogroup"] > label[data-checked="true"],
div[data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) {
    background: #1f242c !important;
    color: #f0f6fc !important;
    border-color: #30363d !important;
    font-weight: 600 !important;
}

/* Enterprise Metric Cards */
div[data-testid="stMetric"] {
    background: #131822 !important;
    border: 1px solid #21262d !important;
    border-radius: 8px !important;
    padding: 14px 18px !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3) !important;
    transition: border-color 0.15s ease !important;
}

div[data-testid="stMetric"]:hover {
    border-color: #388bfd !important;
}

div[data-testid="stMetric"] label[data-testid="stMetricLabel"] {
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    color: #7d8590 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    font-size: 1.75rem !important;
    font-weight: 600 !important;
    color: #f0f6fc !important;
    letter-spacing: -0.02em !important;
    font-family: "JetBrains Mono", monospace !important;
    font-variant-numeric: tabular-nums;
    margin-top: 3px !important;
}

/* Typography Hierarchy */
h1 {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    color: #f0f6fc !important;
    margin-bottom: 1rem !important;
    padding-bottom: 0.5rem !important;
    border-bottom: 1px solid #21262d !important;
}

h2 {
    font-size: 1.15rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
    color: #f0f6fc !important;
    margin-top: 1.4rem !important;
    margin-bottom: 0.6rem !important;
}

h3 {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    color: #e6edf3 !important;
    margin-top: 1rem !important;
    margin-bottom: 0.4rem !important;
}

.stCaption {
    color: #6e7681 !important;
    font-size: 0.78rem !important;
}

/* Status Badges */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    font-family: "JetBrains Mono", monospace;
    line-height: 1.4;
}

.status-pill.critical {
    background: rgba(248, 81, 73, 0.12);
    color: #f85149;
    border: 1px solid rgba(248, 81, 73, 0.4);
}

.status-pill.warning {
    background: rgba(210, 153, 34, 0.12);
    color: #d29922;
    border: 1px solid rgba(210, 153, 34, 0.4);
}

.status-pill.info {
    background: rgba(56, 139, 253, 0.12);
    color: #58a6ff;
    border: 1px solid rgba(56, 139, 253, 0.4);
}

.status-pill.success {
    background: rgba(46, 160, 67, 0.12);
    color: #3fb950;
    border: 1px solid rgba(46, 160, 67, 0.4);
}

.status-pill.neutral {
    background: #161b22;
    color: #8b949e;
    border: 1px solid #30363d;
}

/* App Header Breadcrumb Bar */
.app-header-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0 12px 0;
    margin-bottom: 16px;
    border-bottom: 1px solid #21262d;
}

.app-breadcrumb {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.82rem;
    font-weight: 500;
    color: #8b949e;
}

.app-breadcrumb .active-section {
    color: #f0f6fc;
    font-weight: 600;
}

/* Detail Box Container */
.detail-panel {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 14px;
    font-size: 0.85rem;
    color: #c9d1d9;
}

/* Form Controls */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
    background-color: #0d1117 !important;
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
    color: #f0f6fc !important;
    font-size: 0.85rem !important;
}

div[data-baseweb="select"] > div:hover,
div[data-baseweb="input"] > div:hover {
    border-color: #8b949e !important;
}

div[data-baseweb="select"]:focus-within > div,
div[data-baseweb="input"]:focus-within > div {
    border-color: #58a6ff !important;
    box-shadow: 0 0 0 2px rgba(88, 166, 255, 0.2) !important;
}

/* Tables & Dataframes */
div[data-testid="stDataFrame"] {
    background: #0d1117 !important;
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
}

/* Buttons */
.stButton > button,
.stDownloadButton > button {
    background: #21262d !important;
    border: 1px solid #363b42 !important;
    color: #c9d1d9 !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    padding: 5px 14px !important;
    transition: all 0.12s ease !important;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    background: #30363d !important;
    border-color: #8b949e !important;
    color: #f0f6fc !important;
}
</style>
"""


def apply_theme() -> None:
    """Inject enterprise stylesheet into the Streamlit app."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

"""Enterprise design system and stylesheet for Cascading Delay Intelligence.

Refined, calm, and professional light-mode design system.
Built strictly to modern operations intelligence standards:
- Base: clean off-white / light slate (#F8FAFC) canvas with crisp white cards (#FFFFFF)
- Typography: Inter / system sans-serif hierarchy, tabular nums for metrics
- Primary Accent: #2563EB (restrained operational blue)
- Semantic colors: Green (#16A34A), Amber (#D97706), Red (#DC2626), Blue (#2563EB), Gray (#64748B)
- Centered container with max-width: 1400px
- Locked-in spacing scale and micro-interactions
"""

from __future__ import annotations

import streamlit as st

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

*, *::before, *::after {
    box-sizing: border-box !important;
}

html, body, .stApp {
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    overflow-x: hidden !important;
    max-width: 100vw !important;
}

.stApp, .stMarkdown, .stText, p, div[data-testid="stMainBlockContainer"] {
    color: #0F172A;
}

/* Ensure code blocks never overflow horizontally */
pre, code {
    white-space: pre-wrap !important;
    word-break: break-word !important;
    overflow-wrap: anywhere !important;
    max-width: 100% !important;
}

/* Protect inverted controls from any inherited colour */
.stButton > button[kind="primary"], .stButton > button[kind="primary"] span,
.status-pill, .status-pill span {
    color: inherit;
}
.stButton > button[kind="primary"], .stButton > button[kind="primary"] * {
    color: #FFFFFF !important;
}

/* Tighten Streamlit's default vertical rhythm so cards align to one grid */
div[data-testid="stVerticalBlock"] {
    gap: 0.6rem !important;
}
div[data-testid="stMainBlockContainer"] div[data-testid="stVerticalBlock"] > div {
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

/* Hide legacy test-harness compatibility radio from display */
div[data-testid="stSidebar"] div[data-testid="stRadio"] {
    display: none !important;
}
div[data-testid="column"] {
    min-width: 0 !important;
}
div[data-testid="column"] > div[data-testid="stVerticalBlock"] {
    gap: 0.6rem !important;
}
/* Plotly chart containers: no extra top offset, consistent bottom gap */
div[data-testid="stPlotlyChart"] {
    margin-top: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}
/* Captions sit directly under their visual with a small, even gap */
.stCaption, div[data-testid="stCaptionContainer"] {
    margin-top: -2px !important;
    line-height: 1.45 !important;
}
/* Buttons directly under a card share one baseline gap */
.stButton {
    margin-top: 2px !important;
}

code, kbd, samp, pre, .mono {
    font-family: "JetBrains Mono", "SFMono-Regular", Consolas, Menlo, monospace !important;
    font-variant-numeric: tabular-nums;
}

/* Light Canvas */
.stApp {
    background-color: #F8FAFC !important;
    color: #0F172A !important;
}

/* Maximum Content Width (Max 1400px, no lateral overflow) */
.main .block-container,
div[data-testid="stMainBlockContainer"] {
    max-width: 1380px !important;
    width: 100% !important;
    box-sizing: border-box !important;
    padding-top: 4.25rem !important;
    padding-bottom: 3.5rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    overflow-x: hidden !important;
}

/* Top Navigation Bar / Streamlit Header */
header[data-testid="stHeader"] {
    background-color: #FFFFFF !important;
    border-bottom: 1px solid #E2E8F0 !important;
    height: 3rem !important;
}

/* Minimalist Scrollbars */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: #F1F5F9;
}
::-webkit-scrollbar-thumb {
    background: #CBD5E1;
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: #94A3B8;
}

/* Sidebar Navigation */
section[data-testid="stSidebar"] {
    background: #FFFFFF !important;
    border-right: 1px solid #E2E8F0 !important;
    box-shadow: 2px 0 12px rgba(15, 23, 42, 0.02) !important;
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 1.1rem !important;
    padding-left: 0.85rem !important;
    padding-right: 0.85rem !important;
    padding-bottom: 2rem !important;
    max-width: 100% !important;
}

/* Sidebar Brand Header */
.ci-brand-wrapper {
    padding: 0.2rem 0.4rem 0.85rem 0.4rem;
    border-bottom: 1px solid #F1F5F9;
    margin-bottom: 0.4rem;
}
.ci-brand-top {
    display: flex;
    align-items: center;
    gap: 10px;
}
.ci-brand-logo-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, #1D4ED8 0%, #3B82F6 100%);
    border-radius: 9px;
    box-shadow: 0 2px 8px rgba(37, 99, 235, 0.22);
    flex-shrink: 0;
}
.ci-brand-text {
    display: flex;
    flex-direction: column;
}
.ci-brand-title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.98rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: #0F172A;
    line-height: 1.2;
}
.ci-brand-pill {
    font-size: 0.62rem;
    font-weight: 700;
    color: #2563EB;
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: 4px;
    padding: 1px 5px;
    letter-spacing: 0.05em;
}
.ci-brand-sub {
    font-size: 0.71rem;
    color: #64748B;
    font-weight: 500;
    margin-top: 1px;
}
.ci-brand-status-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 9px;
    padding: 5px 8px;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
}
.ci-status-indicator {
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.ci-status-label {
    font-size: 0.64rem;
    font-weight: 700;
    color: #047857;
    letter-spacing: 0.05em;
}
.ci-pulse-dot {
    width: 7px;
    height: 7px;
    background-color: #10B981;
    border-radius: 50%;
    display: inline-block;
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
    animation: ci-pulse 2s infinite;
}
@keyframes ci-pulse {
    0% {
        box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
    }
    70% {
        box-shadow: 0 0 0 5px rgba(16, 185, 129, 0);
    }
    100% {
        box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
    }
}
.ci-env-tag {
    font-size: 0.62rem;
    font-weight: 600;
    color: #64748B;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 1px 5px;
}

/* Sidebar: clean structured rhythm */
section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {
    gap: 0.25rem !important;
}
section[data-testid="stSidebar"] .stButton {
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

/* Sidebar Section Headers */
.ci-nav-section-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0.85rem 0.5rem 0.25rem 0.5rem;
    margin-top: 0.2rem;
}
.ci-nav-section {
    font-size: 0.65rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.09em !important;
    color: #94A3B8 !important;
    line-height: 1 !important;
    white-space: nowrap !important;
}
.ci-nav-section-rule {
    flex-grow: 1;
    height: 1px;
    background: #F1F5F9;
}

/* Sidebar Nav Buttons */
section[data-testid="stSidebar"] .stButton > button {
    text-align: left !important;
    justify-content: flex-start !important;
    align-items: center !important;
    padding: 0.5rem 0.75rem !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    line-height: 1.4 !important;
    min-height: 2.35rem !important;
    border-radius: 8px !important;
    margin: 0 !important;
    transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1) !important;
    width: 100% !important;
}

/* Active Nav Button */
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(90deg, #EFF6FF 0%, #F8FAFC 100%) !important;
    border: 1px solid #BFDBFE !important;
    border-left: 3.5px solid #2563EB !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 3px rgba(37, 99, 235, 0.08) !important;
    transform: translateX(2px) !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"],
section[data-testid="stSidebar"] .stButton > button[kind="primary"] *,
section[data-testid="stSidebar"] .stButton > button[kind="primary"] p,
section[data-testid="stSidebar"] .stButton > button[kind="primary"] span {
    color: #1D4ED8 !important;
}

/* Inactive Nav Button */
section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
    background-color: transparent !important;
    color: #475569 !important;
    border: 1px solid transparent !important;
    border-left: 3.5px solid transparent !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="secondary"] *,
section[data-testid="stSidebar"] .stButton > button[kind="secondary"] p,
section[data-testid="stSidebar"] .stButton > button[kind="secondary"] span {
    color: #475569 !important;
}

section[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
    background-color: #F8FAFC !important;
    color: #0F172A !important;
    border: 1px solid #E2E8F0 !important;
    border-left: 3.5px solid #94A3B8 !important;
    transform: translateX(2px) !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover * {
    color: #0F172A !important;
}

/* Sidebar divider */
section[data-testid="stSidebar"] hr {
    margin: 0.8rem 0 !important;
    border-color: #F1F5F9 !important;
}

/* Sidebar Telemetry Card */
.ci-sidebar-telemetry {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 9px;
    padding: 0.75rem 0.85rem;
    margin: 0.85rem 0 0.4rem 0;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.02);
}
.ci-telemetry-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.45rem;
}
.ci-telemetry-title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.66rem;
    font-weight: 700;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.ci-telemetry-badge {
    font-size: 0.6rem;
    font-weight: 700;
    color: #15803D;
    background: #DCFCE7;
    border-radius: 4px;
    padding: 1px 5px;
}
.ci-telemetry-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.71rem;
    padding: 2.5px 0;
    color: #64748B;
}
.ci-telemetry-val {
    font-weight: 600;
    color: #1E293B;
}
.ci-telemetry-val-success {
    font-weight: 600;
    color: #16A34A;
}

/* Sidebar Refresh Button Container */
.ci-sidebar-action {
    margin-top: 0.35rem;
    margin-bottom: 0.2rem;
}
section[data-testid="stSidebar"] .ci-sidebar-action .stButton > button {
    background: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    color: #334155 !important;
    font-weight: 600 !important;
    justify-content: center !important;
    text-align: center !important;
    border-left: 1px solid #CBD5E1 !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03) !important;
}
section[data-testid="stSidebar"] .ci-sidebar-action .stButton > button:hover {
    background: #F1F5F9 !important;
    border-color: #94A3B8 !important;
    color: #0F172A !important;
    transform: none !important;
}

/* Sidebar Footer */
.ci-sidebar-footer {
    padding: 0.75rem 0.4rem 0.25rem 0.4rem;
    margin-top: 0.5rem;
    border-top: 1px solid #F1F5F9;
}
.ci-user-pill {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 6px 8px;
    border-radius: 8px;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
}
.ci-user-avatar {
    width: 28px;
    height: 28px;
    border-radius: 6px;
    background: linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%);
    color: #FFFFFF;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    flex-shrink: 0;
}
.ci-user-info {
    display: flex;
    flex-direction: column;
    min-width: 0;
}
.ci-user-name {
    font-size: 0.74rem;
    font-weight: 600;
    color: #1E293B;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.ci-user-role {
    font-size: 0.65rem;
    color: #64748B;
    line-height: 1.2;
}
.ci-footer-meta {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    font-size: 0.65rem;
    color: #94A3B8;
    margin-top: 8px;
    font-weight: 500;
}

/* Standard Buttons across app */
.stButton > button,
.stDownloadButton > button {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    color: #334155 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    padding: 0.45rem 1rem !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;
    transition: all 0.15s ease !important;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    background-color: #F8FAFC !important;
    border-color: #CBD5E1 !important;
    color: #0F172A !important;
}

.stButton > button[kind="primary"] {
    background-color: #2563EB !important;
    border: 1px solid #2563EB !important;
    color: #FFFFFF !important;
}

.stButton > button[kind="primary"]:hover {
    background-color: #1D4ED8 !important;
    border-color: #1D4ED8 !important;
    color: #FFFFFF !important;
}

/* Topbar Header */
.ci-topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 14px 20px;
    margin-bottom: 20px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}
.ci-topbar-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.01em;
}
.ci-topbar-sub {
    font-size: 0.8rem;
    color: #64748B;
    margin-top: 2px;
}

/* Page Headers & Hierarchy — single consistent rhythm */
.ci-page-header {
    margin: 0 0 14px 0;
    padding: 0;
}
.ci-page-title {
    font-size: 1.75rem;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.02em;
    line-height: 1.25;
}
.ci-page-context {
    font-size: 0.92rem;
    color: #475569;
    margin-top: 4px;
    line-height: 1.5;
}

.ci-section-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1E293B;
    letter-spacing: -0.01em;
    margin: 28px 0 4px 0 !important;
    padding: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    line-height: 1.35;
}
.ci-section-sub {
    font-size: 0.82rem;
    color: #64748B;
    margin: 0 0 12px 0 !important;
    padding: 0;
    line-height: 1.5;
}

/* Standard Card Design (Clean, minimal, 12px border-radius) */
.ci-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 16px 20px;
    margin: 0 0 10px 0;
    box-sizing: border-box;
    min-width: 0;
    overflow-wrap: break-word;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03), 0 1px 2px -1px rgba(0, 0, 0, 0.03);
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
/* Metric grid inside a card: even columns that wrap gracefully */
.ci-metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 14px 16px;
    align-items: start;
}
/* Attention / bottleneck cards share one baseline: compact height */
.ci-attention-card {
    min-height: 146px;
    margin-bottom: 8px !important;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
}
.ci-attention-card .ci-attention-detail {
    flex: 1;
}
@media (max-width: 1000px) {
    .ci-attention-card {
        min-height: 0;
    }
}
/* Action buttons in columns sit directly flush with their card */
div[data-testid="column"] .stButton {
    margin-top: 0 !important;
}
div[data-testid="column"] .stButton > button {
    width: 100% !important;
}
/* Delay-split panels stack cleanly on narrow screens */
@media (max-width: 760px) {
    .ci-split-panel {
        border-right: none !important;
        border-bottom: 1px solid #E2E8F0;
    }
    .ci-split-panel:last-child {
        border-bottom: none !important;
    }
}
.ci-card:hover {
    border-color: #CBD5E1;
}
.ci-card-title {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748B;
    margin-bottom: 8px;
}
.ci-card-body {
    font-size: 0.88rem;
    color: #334155;
    line-height: 1.6;
}

/* Semantic Card Accents */
.ci-accent-red { border-left: 3px solid #DC2626; }
.ci-accent-amber { border-left: 3px solid #D97706; }
.ci-accent-green { border-left: 3px solid #16A34A; }
.ci-accent-blue { border-left: 3px solid #2563EB; }
.ci-accent-gray { border-left: 3px solid #94A3B8; }

/* KPI Cards — fluid responsive grid, equal heights, no squeeze/overflow */
.ci-kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    margin: 0 0 8px 0;
    align-items: stretch;
    width: 100%;
    box-sizing: border-box;
}
.ci-kpi-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 14px 16px;
    min-height: 118px;
    height: 100%;
    box-sizing: border-box;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    gap: 2px;
    min-width: 0;
    overflow: hidden;
}
.ci-kpi-label {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748B;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.ci-kpi-value {
    font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 1.55rem;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.02em;
    line-height: 1.2;
    margin: 4px 0 2px 0;
    font-variant-numeric: tabular-nums;
    overflow-wrap: break-word;
    word-break: break-word;
}
.ci-kpi-context {
    font-size: 0.74rem;
    color: #64748B;
    line-height: 1.4;
    overflow-wrap: break-word;
}

/* Hero Section (Context before metrics) */
.ci-hero-box {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
}
.ci-hero-lead {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #2563EB;
}
.ci-hero-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: #0F172A;
    letter-spacing: -0.01em;
    margin: 6px 0 6px 0;
    line-height: 1.4;
}
.ci-hero-detail {
    font-size: 0.88rem;
    color: #475569;
    line-height: 1.55;
}

/* Visual Centerpiece: Active Cascade Component */
.ci-centerpiece {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 22px 24px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
    margin-bottom: 16px;
}
.ci-centerpiece-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}
.ci-centerpiece-title {
    font-size: 1.2rem;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.01em;
}
.ci-centerpiece-sub {
    font-size: 0.85rem;
    color: #64748B;
    margin-top: 2px;
}
.ci-centerpiece {
    margin: 0 0 4px 0;
}
.ci-centerpiece-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 10px;
}
.ci-centerpiece-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 20px;
    justify-content: space-between;
    margin: 14px 0 16px 0;
    padding: 12px 16px;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
}
.ci-stat-item {
    display: flex;
    flex-direction: column;
    min-width: 110px;
    flex: 1 1 110px;
}
.ci-stat-num {
    font-size: 1.05rem;
    font-weight: 700;
    color: #0F172A;
    font-family: "JetBrains Mono", monospace;
    white-space: nowrap;
}
.ci-stat-lbl {
    font-size: 0.68rem;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
    margin-top: 2px;
}

/* Flowchart Chain inside Active Cascade */
.ci-flow-container {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding: 12px 0 4px 0;
    gap: 4px;
}
.ci-flow-node {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    border-radius: 9999px;
    font-size: 0.82rem;
    font-weight: 600;
    font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif !important;
    background: #F1F5F9;
    border: 1px solid #E2E8F0;
    color: #1E293B;
    max-width: 100%;
    overflow-wrap: anywhere;
    word-break: break-word;
    line-height: 1.4;
}
.ci-flow-node.root {
    background: #FEE2E2;
    border-color: #FECACA;
    color: #991B1B;
}
.ci-flow-arrow-down {
    padding-left: 24px;
    font-size: 0.85rem;
    color: #94A3B8;
    line-height: 1.2;
}

/* Health Dial / Gauge Card */
.ci-health-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 22px 20px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.ci-health-num {
    font-size: 2.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1;
    font-variant-numeric: tabular-nums;
}
.ci-health-num span {
    font-size: 1rem;
    color: #94A3B8;
    font-weight: 500;
}
.ci-health-progress-bg {
    height: 8px;
    background: #E2E8F0;
    border-radius: 4px;
    overflow: hidden;
    margin: 10px 0;
}
.ci-health-progress-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s ease;
}

/* Status Badges & Pills */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 8px;
    border-radius: 9999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    font-family: "Inter", -apple-system, sans-serif;
    line-height: 1.4;
    white-space: nowrap;
}
.status-pill.critical {
    background: #FEE2E2;
    color: #991B1B;
    border: 1px solid #FECACA;
}
.status-pill.warning {
    background: #FEF3C7;
    color: #92400E;
    border: 1px solid #FDE68A;
}
.status-pill.info {
    background: #EFF6FF;
    color: #1D4ED8;
    border: 1px solid #DBEAFE;
}
.status-pill.success {
    background: #DCFCE7;
    color: #166534;
    border: 1px solid #BBF7D0;
}
.status-pill.neutral {
    background: #F1F5F9;
    color: #475569;
    border: 1px solid #E2E8F0;
}

/* Timeline Components */
.ci-timeline-container {
    position: relative;
    padding-left: 28px;
    margin: 16px 0;
}
.ci-timeline-container::before {
    content: '';
    position: absolute;
    top: 6px;
    bottom: 6px;
    left: 8px;
    width: 2px;
    background: #CBD5E1;
}
.ci-timeline-row {
    position: relative;
    margin-bottom: 18px;
}
.ci-timeline-row:last-child {
    margin-bottom: 0;
}
.ci-timeline-bullet {
    position: absolute;
    left: -26px;
    top: 5px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #FFFFFF;
    border: 3px solid #2563EB;
    box-sizing: border-box;
}
.ci-timeline-bullet.root {
    border-color: #DC2626;
    background: #FEE2E2;
}
.ci-timeline-content {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 12px 16px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
}
.ci-timeline-time {
    font-size: 0.72rem;
    font-weight: 600;
    color: #2563EB;
    font-family: "JetBrains Mono", monospace;
}
.ci-timeline-event {
    font-size: 0.88rem;
    font-weight: 600;
    color: #0F172A;
    margin: 2px 0;
}
.ci-timeline-desc {
    font-size: 0.8rem;
    color: #64748B;
    line-height: 1.5;
}

/* Human Explanation Blocks */
.ci-explanation-block {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 14px;
}
.ci-explanation-q {
    font-size: 0.82rem;
    font-weight: 700;
    color: #1E293B;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
}
.ci-explanation-a {
    font-size: 0.88rem;
    color: #475569;
    line-height: 1.6;
    margin-bottom: 14px;
}
.ci-explanation-a:last-child {
    margin-bottom: 0;
}

/* Risk Detail Card */
.ci-risk-item {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
}
.ci-risk-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 6px;
}
.ci-risk-item {
    min-width: 0;
    overflow-wrap: break-word;
}
.ci-risk-bullet {
    font-size: 0.8rem;
    color: #475569;
    line-height: 1.5;
    margin: 3px 0;
    padding-left: 12px;
    position: relative;
}
.ci-risk-bullet::before {
    content: "•";
    position: absolute;
    left: 0;
    color: #DC2626;
    font-weight: bold;
}

/* Empty & Error States */
.ci-state {
    background: #FFFFFF;
    border: 1px dashed #CBD5E1;
    border-radius: 12px;
    padding: 32px 24px;
    text-align: center;
    margin: 14px 0;
}
.ci-state-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: #0F172A;
}
.ci-state-body {
    font-size: 0.82rem;
    color: #64748B;
    margin-top: 4px;
    line-height: 1.5;
}
.ci-state-error {
    border: 1px solid #FECACA;
    background: #FEF2F2;
}
.ci-state-error .ci-state-title {
    color: #991B1B;
}

/* Inputs & Form Controls */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
    background-color: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 8px !important;
    color: #0F172A !important;
    font-size: 0.85rem !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
}

div[data-baseweb="select"]:hover > div,
div[data-baseweb="input"]:hover > div {
    border-color: #94A3B8 !important;
}

div[data-baseweb="select"]:focus-within > div,
div[data-baseweb="input"]:focus-within > div {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12) !important;
}

/* Card action buttons: full-width inside their column so edges align */
.stButton > button[widthmode="stretch"], .stButton > button[kind="primary"][widthmode="stretch"] {
    width: 100%;
}
/* Responsive Grid adjustments */
@media (max-width: 900px) {
    .main .block-container,
    div[data-testid="stMainBlockContainer"] {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    .ci-topbar {
        flex-direction: column;
        align-items: flex-start;
        gap: 12px;
    }
    .ci-kpi-value {
        font-size: 1.35rem;
    }
    .ci-centerpiece-stats {
        gap: 10px 14px;
    }
}
</style>
"""


def apply_theme() -> None:
    """Inject enterprise stylesheet into the Streamlit app."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

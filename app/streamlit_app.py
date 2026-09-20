"""Cascading Delay Intelligence — Streamlit application entry point.

Minimal foundation app. The full dashboard will be implemented in a
future feature branch once data ingestion and analytics are available.
"""

import streamlit as st

PROJECT_NAME = "Cascading Delay Intelligence"
PROJECT_DESCRIPTION = (
    "End-to-end logistics data product for identifying delay patterns "
    "and cascading operational delays across routes, warehouses, and transfers."
)

st.set_page_config(page_title=PROJECT_NAME, page_icon=":truck:", layout="wide")

st.title(PROJECT_NAME)
st.write(PROJECT_DESCRIPTION)

st.header("Status")
st.info("Project foundation initialized.")

"""
Build Integrated Dataset for Streamlit Application
Bridges cascading-delay-dataset/data/ with the Streamlit dashboard by assembling
the canonical integrated_logistics_data.csv with full journey milestones and causal metadata.
"""

import os
from pathlib import Path
import pandas as pd

DATA_DIR = Path("cascading-delay-dataset/data")
OUTPUT_DIR = Path("data/processed")
OUTPUT_FILE = OUTPUT_DIR / "integrated_logistics_data.csv"

def build_integrated_dataset():
    print(f"Loading tables from {DATA_DIR}...")
    shipments = pd.read_csv(DATA_DIR / "shipments.csv")
    events = pd.read_csv(DATA_DIR / "logistics_events.csv")
    locations = pd.read_csv(DATA_DIR / "locations.csv")
    cascades = pd.read_csv(DATA_DIR / "cascade_events.csv")
    delay_reasons = pd.read_csv(DATA_DIR / "delay_reasons.csv").set_index("delay_reason_id", drop=False)

    print("Merging events with shipment profiles...")
    # Base is operational scan events (77,063 rows)
    merged = events.merge(
        shipments,
        on="shipment_id",
        how="left",
        suffixes=("", "_shp")
    )

    # Add location metadata
    merged = merged.merge(
        locations[["location_id", "location_name", "city", "state"]],
        on="location_id",
        how="left"
    )

    # Standardize column names for analytics layer
    merged["route_id"] = merged["origin_location_id"] + " -> " + merged["destination_location_id"]
    merged["warehouse_id"] = merged["location_id"]
    merged["source_warehouse"] = merged["origin_location_id"]
    merged["destination_warehouse"] = merged["destination_location_id"]
    merged["timestamp"] = merged["actual_timestamp"]
    merged["delay_duration"] = merged["delay_minutes"]
    
    # Map delay reasons
    def get_reason(row):
        rid = row.get("delay_reason_id")
        if pd.notna(rid) and rid in delay_reasons.index:
            return delay_reasons.loc[rid, "reason_name"]
        cat = row.get("root_cause_category")
        if pd.notna(cat) and str(cat).lower() != "nan":
            return str(cat)
        return "None" if row["delay_minutes"] == 0 else "Operational Variance"

    merged["delay_reason"] = merged.apply(get_reason, axis=1)

    # Traceability flags
    merged["_delay_match"] = merged["delay_duration"].apply(lambda d: "both" if d > 0 else "left-only")
    merged["_transfer_match"] = merged["cascade_level"].apply(lambda l: "both" if l >= 0 else "left-only")
    merged["_record_source"] = "cascading-delay-dataset"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing integrated dataset to {OUTPUT_FILE} ({len(merged):,} rows)...")
    merged.to_csv(OUTPUT_FILE, index=False)
    print("Done! Application dataset successfully built.")

if __name__ == "__main__":
    build_integrated_dataset()

# Cascading Delay Intelligence

## 1. Project Overview

**Cascading Delay Intelligence** is an end-to-end data product for a logistics company that wants to understand how operational delays propagate across shipment routes and warehouse transfers.

The company currently maintains shipment scans, delay reports, and warehouse transfer records separately. Because these sources are disconnected, it is difficult to identify routes and warehouses that repeatedly contribute to cascading delivery delays.

The goal of this project is to transform raw operational datasets into a usable business intelligence product that:

* Ingests multiple logistics datasets
* Validates and profiles incoming data
* Cleans and standardizes data
* Combines multiple operational sources
* Reconstructs shipment journeys
* Identifies delay patterns and cascading delays
* Calculates meaningful logistics KPIs
* Performs route and warehouse analysis
* Detects anomalies and operational risks
* Provides interactive visualizations
* Provides threshold-based alerts
* Generates reports
* Automates repeatable data workflows

The product should focus on **data engineering, analytics, and business intelligence**, rather than being primarily an ML prediction system.

---

# 2. Business Problem

### Problem Statement

> A logistics company tracks shipment scans, delay reports, and warehouse transfer records separately, making it impossible to predict which operational routes consistently produce cascading delivery delays.

### Core Business Question

The product should help answer:

> **Which routes, warehouses, and operational stages are most associated with cascading delivery delays, and what patterns explain those delays?**

### Supporting Questions

The system should help answer:

1. How many shipments are delayed?
2. What is the average delay?
3. Which routes have the highest delay rates?
4. Which warehouses are associated with repeated delays?
5. Which delay reasons occur most frequently?
6. Where do delays begin?
7. How often does an initial delay propagate to downstream stages?
8. Which routes show unusual delay behavior?
9. What operational factors are associated with cascading delays?
10. Which metrics should trigger an operational alert?

---

# 3. Product Goal

Convert:

```text
Raw Logistics Data
        ↓
Data Validation
        ↓
Data Cleaning
        ↓
Data Integration
        ↓
Feature Engineering
        ↓
Analytics
        ↓
Business Insights
        ↓
Interactive Data Product
        ↓
Alerts + Reports
```

into a single usable workflow.

The final product should allow a stakeholder to move from raw data to actionable insights without manually performing the entire analysis.

---

# 4. Product Scope

## MVP

The MVP must include:

* CSV/JSON dataset ingestion
* Dataset validation
* Dataset profiling
* Missing-value handling
* Data-type standardization
* Duplicate detection
* String normalization
* Date/time normalization
* Multi-source data integration
* Feature engineering
* Exploratory analysis
* KPI calculation
* Route analysis
* Warehouse analysis
* Delay analysis
* Cascading-delay analysis
* SQL-based analytical queries
* Interactive Streamlit dashboard
* Plotly visualizations
* Threshold-based alerts
* Report generation
* Basic email-report integration
* Automated pipeline execution
* GitHub-based validation
* Documentation

---

# 5. Non-Goals

The initial version should NOT unnecessarily introduce:

* Complex machine-learning models
* Real-time Kafka infrastructure
* Microservices
* Kubernetes
* Cloud-native distributed architecture
* Complex MLOps infrastructure
* Unnecessary external APIs
* Large-scale production infrastructure

These may be considered future improvements if the business requirement justifies them.

The MVP should prioritize:

**Correctness → Data Quality → Business Insights → Usability → Automation**

---

# 6. Technology Stack

## Core

* Python
* Pandas
* NumPy

## Database / Analytics

* SQL
* SQLite for simple/local development OR PostgreSQL if required by the implementation

## Visualization

* Plotly
* Streamlit

## Development

* Git
* GitHub

## Automation

* GitHub Actions

## Reporting

* Python-based report generation
* Email integration

---

# 7. High-Level Architecture

```text
                    ┌─────────────────────┐
                    │    Raw Data Sources │
                    │                     │
                    │ Shipment Scans      │
                    │ Delay Reports       │
                    │ Warehouse Transfers │
                    └──────────┬──────────┘
                               │
                               ↓
                    ┌─────────────────────┐
                    │   Data Ingestion    │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Validation &        │
                    │ Data Quality Checks  │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Data Cleaning       │
                    │ & Standardisation   │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Multi-Source        │
                    │ Integration         │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Feature Engineering │
                    └──────────┬──────────┘
                               ↓
               ┌───────────────┴────────────────┐
               ↓                                ↓
      ┌──────────────────┐             ┌──────────────────┐
      │ Python Analytics │             │ SQL Analytics    │
      └────────┬─────────┘             └────────┬─────────┘
               │                                │
               └───────────────┬────────────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Business Insights   │
                    │ & KPI Layer         │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Streamlit Product   │
                    │ + Plotly            │
                    └──────┬───────┬──────┘
                           │       │
                           ↓       ↓
                       Alerts   Reports
                           │       │
                           └───┬───┘
                               ↓
                         Stakeholders
```

---

# 8. Data Sources

The system is designed around three primary datasets.

## 8.1 Shipment Scans

Expected information may include:

* shipment_id
* timestamp
* warehouse_id
* route_id
* scan_type
* status

Purpose:

Track the movement and operational state of shipments.

---

## 8.2 Delay Reports

Expected information may include:

* shipment_id
* delay_id
* delay_reason
* delay_duration
* reported_at
* warehouse_id
* route_id

Purpose:

Identify reported operational delays and their causes.

---

## 8.3 Warehouse Transfers

Expected information may include:

* transfer_id
* shipment_id
* source_warehouse
* destination_warehouse
* transfer_time
* expected_transfer_time
* actual_transfer_time

Purpose:

Understand warehouse movement and transfer-related delays.

---

# 9. Data Contract

AI agents MUST NOT assume exact dataset columns unless they are actually present in the project datasets.

Before implementing transformation logic:

1. Inspect the actual dataset.
2. Identify columns.
3. Determine data types.
4. Determine relationships between datasets.
5. Document assumptions.
6. Create or update the data dictionary.

If a required field does not exist, do not silently invent it.

Instead:

```text
Dataset
   ↓
Inspect
   ↓
Confirm Schema
   ↓
Map Fields
   ↓
Implement Transformation
```

---

# 10. Data Pipeline

The pipeline should follow these stages:

```text
1. Intake
2. Profiling
3. Validation
4. Cleaning
5. Standardisation
6. Integration
7. Feature Engineering
8. Analytical Dataset Creation
9. KPI Calculation
10. Insight Generation
11. Product Consumption
```

Each stage should have a clear responsibility.

Avoid putting the entire pipeline inside one large Python file.

## 10.1 Orchestration (`pipeline/run_pipeline.py`)

Stage logic stays in its own module; `run_pipeline` only coordinates:
source build → ingestion → validation → **gate** → cleaning →
integration → analytics → SQL cross-check → cascade → route risk →
alerts → run manifest (`data/processed/runs/run_<timestamp>.json`,
gitignored). The gate interprets the validation verdict: ERROR stops the
run (downstream SKIPPED, overall FAILED, non-zero exit); WARNING
continues with overall SUCCESS_WITH_WARNINGS. CLI:
`python -m pipeline.run_pipeline --dataset showcase`
(`--dataset lade --input <pickup.csv>` when the LaDe source is available;
nothing is ever downloaded automatically).

---

# 11. Data Validation

Validation should check:

* Required columns
* Missing values
* Invalid data types
* Invalid timestamps
* Duplicate records
* Invalid IDs
* Negative durations where invalid
* Impossible timestamps
* Invalid categorical values
* Referential integrity
* Join mismatches
* Unexpected null relationships

Validation should produce useful information rather than simply failing silently.

Example:

```text
Validation Summary
------------------
Rows processed: 10,000
Valid rows: 9,842
Invalid rows: 158

Missing shipment IDs: 12
Duplicate records: 84
Invalid timestamps: 31
Join mismatches: 31
```

---

# 12. Data Cleaning

Cleaning operations may include:

* Missing-value handling
* Duplicate removal
* String normalization
* Date/time conversion
* Data-type enforcement
* Category standardization
* Invalid-record handling
* Outlier investigation

Cleaning logic must be deterministic and reproducible.

Do not modify raw files directly.

Use:

```text
data/raw/
    ↓
processing
    ↓
data/processed/
```

---

# 13. Multi-Source Integration

The central analytical dataset should combine relevant information from:

```text
Shipment Scans
       +
Delay Reports
       +
Warehouse Transfers
       ↓
Integrated Shipment Journey
```

Potential keys:

* shipment_id
* route_id
* warehouse_id
* timestamp relationships

The exact join strategy must be based on the actual dataset schema.

AI agents must validate joins instead of assuming that every row has a matching record.

Track:

* matched records
* unmatched records
* duplicate joins
* one-to-many relationships
* many-to-many risks

---

# 14. Shipment Journey Reconstruction

The system should attempt to reconstruct the operational journey of a shipment.

Conceptually:

```text
Shipment Created
      ↓
Warehouse A
      ↓
Transfer
      ↓
Warehouse B
      ↓
Route
      ↓
Delivery
```

For each shipment, where the data supports it, derive:

* journey duration
* number of warehouse transfers
* number of delays
* total delay duration
* initial delay point
* downstream delays
* route involved
* warehouses involved

---

# 15. Cascading Delay Definition

A cascading delay should not simply mean:

> "A shipment was delayed."

Instead, the system should identify a sequence where an earlier operational delay is followed by one or more downstream delays.

Conceptually:

```text
Initial Delay
      ↓
Missed / Late Transfer
      ↓
Warehouse Waiting
      ↓
Downstream Route Delay
      ↓
Final Delivery Delay
```

The exact cascade rule must be documented and based on available timestamps and operational relationships.

Do not claim a causal relationship when the dataset only demonstrates correlation or temporal sequence.

Use language such as:

* "associated with"
* "followed by"
* "observed pattern"
* "correlated with"

unless causality is actually established.

---

# 16. Feature Engineering

Potential derived features include:

```text
total_delay_duration
delay_count
transfer_count
warehouse_wait_time
route_delay_rate
warehouse_delay_rate
on_time_flag
delayed_flag
cascade_flag
days_to_delivery
delay_stage
```

Only create features that are supported by the available data.

Every derived feature should have:

* Name
* Definition
* Source columns
* Calculation
* Business meaning

---

# 17. KPI Layer

Potential KPIs:

### Shipment KPIs

* Total shipments
* Delayed shipments
* On-time shipments
* On-time delivery rate

### Delay KPIs

* Average delay
* Median delay
* Maximum delay
* Total delay duration
* Delay rate

### Cascade KPIs

* Cascade events
* Cascade rate
* Average downstream delay
* Routes associated with cascades
* Warehouses associated with cascades

### Operational KPIs

* Average transfer time
* Transfer delay rate
* Warehouse waiting time

KPI definitions must be centralized rather than duplicated throughout the application.

---

# 18. Route Analysis

Route analysis should identify:

* shipment volume by route
* delay rate by route
* average delay by route
* cascade rate by route
* common delay reasons
* route-level anomalies

Example analytical question:

```text
Which routes have a high shipment volume
AND unusually high delay/cascade rates?
```

Avoid ranking routes using arbitrary scores unless the scoring methodology is explicitly defined.

---

# 18.1 Route Cascade Risk (Empirical Indicators)

The cascade analysis (§15) is descriptive per shipment. This layer adds
transparent, route-level **historical** risk indicators over observed
journeys. It does not train a model and does not predict the future.

Definitions (per route R, shipment grain — each shipment counts once):

```text
cascade_rate(R)           = cascade_shipments / delayed_shipments x 100
downstream_delay_rate(R)  = same ratio (independently computed flag path;
                            identical under the shared cascade definition)
cascade_probability(R)    = cascade_shipments / delayed_shipments (0..1),
                            the empirical conditional probability
                            P(downstream delay | initial delay on R)
cascade_recurrence(R)     = weeks_with_cascade / weeks_with_delays
                            (weekly by default, configurable frequency)
```

Consistency: mean, population standard deviation (ddof=0), and
coefficient of variation (std/mean) of the route's weekly cascade rates.
Std/cv are null with fewer than two observed weeks; cv is null when the
mean is zero.

Depth: average/maximum/distribution of `cascade_depth` from §15 (no new
stages). Transitions: observed consecutive stage pairs with empirical
P(next | current); only transitions present in the data.

Risk classes (LOW / MEDIUM / HIGH / INSUFFICIENT_DATA) come from
caller-configurable thresholds (`config/route_risk_config.py`), never
hardcoded business verdicts. Routes below the minimum delayed-shipment
guard are INSUFFICIENT_DATA, never LOW. Metrics always ship beside any
label.

Empirical probability vs ML prediction: these ratios summarize what
already happened (e.g. 32 downstream of 100 initial delays = 0.32).
They carry no trained model, no features, no validation of future
accuracy, and must never be presented as predictions.

Minimum data: a route column, a timestamp column, and at least one
delayed shipment. Routes without timestamped delays keep rates/depths
but get null recurrence/consistency. Shipments without any delayed event
are out of scope for every ratio; rows without usable timestamps are
skipped with explicit counts.

---

# 19. Warehouse Analysis

Warehouse analysis should examine:

* inbound volume
* outbound volume
* average waiting time
* delay frequency
* transfer delays
* cascade associations
* operational anomalies

The goal is to identify operational patterns that may require investigation.

---

# 20. Root Cause Investigation

Root-cause analysis should be evidence-based.

Possible dimensions:

```text
Delay Reason
    ↓
Warehouse
    ↓
Route
    ↓
Transfer
    ↓
Time Period
```

Example:

```text
High Delay Rate
      ↓
Mostly observed at Warehouse W12
      ↓
Mostly associated with Transfer Type X
      ↓
Mostly occurs during evening operations
```

This should be presented as an observed analytical pattern, not automatically as a proven causal explanation.

---

# 21. Anomaly Detection

The MVP can use statistical/business rules such as:

* percentile thresholds
* z-scores
* IQR
* sudden changes from historical averages
* unusually high route delay rates
* unusually high warehouse delay rates

Example:

```text
IF route_delay_rate > defined_threshold
THEN create route alert
```

Thresholds must be configurable.

Avoid hardcoding unexplained business thresholds.

---

# 22. SQL Analytics

SQL should be used for business-oriented analytical queries.

Examples:

* shipment counts
* delay rates
* route aggregation
* warehouse aggregation
* joins
* rankings
* window functions
* rolling metrics
* analytical views

Example conceptual query:

```sql
SELECT
    route_id,
    COUNT(*) AS total_shipments,
    AVG(delay_duration) AS avg_delay
FROM shipments
GROUP BY route_id;
```

Actual SQL must match the real database schema.

SQL results should be validated against Python/Pandas calculations where practical.

---

# 23. Streamlit Application

The application should be organized into clear pages.

Suggested pages:

```text
Overview
Dataset Explorer
Delay Analysis
Route & Warehouse Insights
Risk & Alerts
Reports
```

The UI should prioritize business usability over technical complexity.

A stakeholder should understand the important information without reading the source code.

---

# 24. Dashboard Design

The Overview page should provide:

```text
Total Shipments
Delayed Shipments
Average Delay
On-Time Rate
Cascade Rate
Active Alerts
```

Then:

```text
Delay Trend
Route Performance
Warehouse Performance
Delay Reasons
Cascade Patterns
```

Charts should answer specific business questions.

Avoid adding charts simply because the data allows them.

---

# 25. Interactive Filters

Potential filters:

* Date range
* Route
* Warehouse
* Delay reason
* Shipment status
* Cascade status

Filters should update the relevant KPIs and visualizations.

Do not create duplicated filtering logic across every page.

---

# 26. Alerts

The alert system should identify conditions such as:

```text
High Route Delay Rate
High Warehouse Delay Rate
Unusual Delay Increase
High Cascade Rate
Unusual Transfer Time
```

Each alert should contain:

```text
Alert Type
Entity
Current Value
Threshold
Severity
Reason
Timestamp
```

Alerts should be explainable.

Avoid opaque alert scores without an understandable reason.

---

# 27. Reporting

The reporting layer should provide a concise business summary containing:

* KPI summary
* Major delay patterns
* Route findings
* Warehouse findings
* Cascade findings
* Active alerts
* Recommended areas for investigation

Reports should distinguish:

```text
Observed Data
      ↓
Analysis
      ↓
Interpretation
```

Do not present assumptions as facts.

---

# 28. Email Reporting

Email functionality should be modular.

The core analytics system must work even if email configuration is unavailable.

Use environment variables for credentials.

Never commit:

* API keys
* SMTP passwords
* tokens
* credentials

Example:

```text
EMAIL_HOST
EMAIL_PORT
EMAIL_USERNAME
EMAIL_PASSWORD
EMAIL_RECIPIENT
```

---

# 29. Project Structure

```text
cascading-delay-intelligence/
│
├── app/
│   ├── streamlit_app.py
│   ├── pages/
│   │   ├── overview.py
│   │   ├── dataset.py
│   │   ├── analysis.py
│   │   ├── routes.py
│   │   ├── alerts.py
│   │   └── reports.py
│   │
│   └── components/
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── sample/
│
├── pipeline/
│   ├── ingestion.py
│   ├── validation.py
│   ├── cleaning.py
│   ├── transformation.py
│   ├── feature_engineering.py
│   └── pipeline.py
│
├── analysis/
│   ├── eda.py
│   ├── kpis.py
│   ├── route_analysis.py
│   ├── warehouse_analysis.py
│   └── cascade_analysis.py
│
├── sql/
│   ├── schema.sql
│   ├── metrics.sql
│   ├── analysis.sql
│   └── views.sql
│
├── reports/
│
├── tests/
│
├── .github/
│   └── workflows/
│       └── validate.yml
│
├── requirements.txt
├── .gitignore
├── README.md
└── design.md
```

The structure can evolve when implementation requirements justify a change.

Do not reorganize the project unnecessarily.

---

# 30. Team Responsibilities

## Data Product & Analytics Lead

Responsibilities:

* Overall architecture
* Multi-source integration
* Feature engineering
* Business analytics
* KPI design
* SQL analysis
* Route analysis
* Warehouse analysis
* Cascading-delay analysis
* Root-cause investigation
* Anomaly/risk logic
* Product integration
* End-to-end testing

## Data Engineering & Automation

Responsibilities:

* Data ingestion
* Dataset validation
* Data-quality checks
* Cleaning workflows
* Standardisation
* Duplicate detection
* Pipeline automation
* Logging
* Automated validation
* GitHub Actions

## Data Visualization & Application

Responsibilities:

* Streamlit application
* Navigation
* Dashboard UI
* Plotly charts
* Interactive filters
* KPI presentation
* Alert interface
* Report interface
* Email reporting
* UX improvements

All members should review each other's work.

---

# 31. AI Agent Development Rules

AI agents working on this repository MUST follow these rules.

## Rule 1 — Inspect Before Changing

Before modifying code:

1. Inspect the repository.
2. Inspect relevant files.
3. Understand existing architecture.
4. Check existing implementations.
5. Identify dependencies.

Do not blindly create new files.

---

## Rule 2 — Do Not Invent Data

Never assume:

* column names
* database schema
* relationships
* business rules
* thresholds
* dataset values

Inspect the actual data first.

---

## Rule 3 — Preserve Existing Functionality

Before modifying an existing component:

```text
Understand current behavior
        ↓
Identify required change
        ↓
Make minimal change
        ↓
Test existing behavior
        ↓
Test new behavior
```

Do not rewrite working modules unnecessarily.

---

## Rule 4 — Separation of Concerns

Keep:

```text
Ingestion
Validation
Cleaning
Transformation
Analysis
Visualization
Reporting
```

separate.

Do not place data-processing logic directly inside Streamlit UI code unless the logic is genuinely UI-specific.

---

## Rule 5 — Reusable Functions

Prefer small reusable functions.

Bad:

```python
def process_everything():
    # 500 lines
```

Better:

```python
load_data()
validate_data()
clean_data()
transform_data()
engineer_features()
calculate_kpis()
```

---

## Rule 6 — Configuration

Avoid hardcoded:

* file paths
* thresholds
* credentials
* database URLs
* email addresses

Use configuration/environment variables where appropriate.

---

## Rule 7 — Error Handling

Errors should be:

* understandable
* actionable
* logged where appropriate

Avoid:

```python
except:
    pass
```

Do not silently suppress errors.

---

## Rule 8 — Reproducibility

The same input dataset and configuration should produce the same analytical output unless randomness is explicitly required.

---

# 32. Testing Requirements

Testing should cover:

### Data Tests

* Schema validation
* Missing values
* Duplicate detection
* Data types
* Invalid values

### Pipeline Tests

* Ingestion
* Cleaning
* Transformation
* Integration

### Analytics Tests

* KPI calculations
* Delay calculations
* Cascade detection
* Route aggregation
* Warehouse aggregation

### Application Tests

* App startup
* Page loading
* Filters
* Data availability
* Alert generation

---

# 33. Git Workflow

Use:

```text
main
  ↑
develop
  ↑
feature/*
```

Example branches:

```text
feature/data-pipeline
feature/data-quality
feature/analytics
feature/sql-analysis
feature/streamlit-dashboard
feature/alerts
feature/reporting
```

Each feature should be developed independently and merged through a Pull Request.

PRs should contain:

```text
What changed?
Why was it changed?
How was it tested?
Any limitations?
```

---

# 34. Commit Guidelines

Prefer meaningful commits.

Good:

```text
feat: add shipment dataset validation
feat: add route delay analysis
feat: add cascade detection
feat: add Streamlit KPI dashboard
fix: handle missing warehouse IDs
test: add KPI calculation tests
docs: update data pipeline documentation
```

Avoid:

```text
update
changes
final
final2
new
stuff
```

---

# 35. Definition of Done

A feature is considered complete only when:

* Implementation exists
* Code is integrated correctly
* Relevant tests pass
* Existing functionality still works
* Documentation is updated when needed
* No credentials are exposed
* Edge cases are considered
* PR description explains the change

For analytical features, also verify:

```text
Data → Calculation → Result → Business Meaning
```

---

# 36. AI Agent Task Execution Protocol

When an AI agent receives a task, it should follow:

```text
1. Understand the task
2. Inspect repository
3. Identify affected modules
4. Check existing implementation
5. Plan minimal changes
6. Implement
7. Run tests/validation
8. Review generated code
9. Check integration
10. Summarize changes
```

The agent should not start coding immediately when repository context is unknown.

---

# 37. Decision-Making Principles

When multiple implementation options exist, prioritize:

1. Correctness
2. Simplicity
3. Maintainability
4. Data quality
5. Reproducibility
6. Performance
7. User experience

Do not choose a more complex architecture merely because it looks more production-grade.

---

# 38. Performance Principles

Optimize only when there is a meaningful reason.

Potential optimizations:

* Vectorized Pandas/NumPy operations
* Efficient joins
* Avoid unnecessary DataFrame copies
* SQL aggregation where appropriate
* Caching expensive analytical operations in Streamlit
* Avoid recalculating unchanged datasets

Do not sacrifice correctness for premature optimization.

---

# 39. Security Rules

Never commit:

```text
.env
API keys
passwords
tokens
SMTP credentials
database credentials
private datasets
```

Use `.env.example` for configuration documentation.

---

# 40. Documentation Requirements

Important analytical logic must be documented.

For each major metric:

```text
Metric Name
Definition
Formula
Source Columns
Business Meaning
Limitations
```

For each major transformation:

```text
Input
Transformation
Output
Reason
```

---

# 41. Future Extensions

Potential future improvements:

* Predictive delay modeling
* Route risk scoring
* Advanced anomaly detection
* Real-time shipment monitoring
* External logistics APIs
* Cloud deployment
* PostgreSQL production database
* Automated scheduled reports
* Advanced role-based access
* Machine-learning-based forecasting

These are future extensions and should not complicate the MVP unless required.

---

# 42. Final Product Principle

The product should answer one central question:

> **Where are delays happening, how are they propagating, and which operational areas should be investigated?**

Every major feature should contribute to answering this question.

If a feature does not improve:

* data quality,
* analysis,
* business understanding,
* decision support,
* usability,
* or automation,

question whether it belongs in the MVP.

---

# 43. AI Agent Golden Rule

**Do not build what you assume the project needs. Build what the repository, dataset, requirements, and documented business problem actually support.**

Always prefer:

```text
Inspect → Understand → Plan → Implement → Validate → Document
```

over:

```text
Assume → Code → Hope
```

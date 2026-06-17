# Carbon Footprint Coach

A Streamlit platform that helps individuals **understand**, **track**, and **reduce** their carbon footprint through daily logging, dashboards, personalized insights, and an action tracker.

## Features

- Daily activity logging for transport, electricity, diet, flights, and recycling/composting
- Dashboard with category breakdown, trend over time, benchmark comparison, and daily goal tracking
- Personalized recommendations based on the user's logged patterns
- Action tracker with estimated yearly reduction potential
- CSV export/import so users can keep their own data
- Session-based storage to avoid mixing data between users on public deployments
- CSV validation and formula-injection sanitization
- Unit tests and Streamlit smoke tests

## Project structure

```text
.
├── app.py
├── carbon_engine.py
├── data_manager.py
├── requirements.txt
├── runtime.txt
├── README.md
└── tests/
    ├── test_app_smoke.py
    ├── test_carbon_engine.py
    └── test_data_manager.py
```

## Run locally

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## Run tests

```bash
pytest -q
```

## Methodology

The app uses simplified average emission factors to keep the user experience lightweight and understandable. The results are intended for awareness and behavior change, not regulatory reporting.

Main assumptions:

- Transport factors are approximate kg CO2e per km values.
- Electricity uses an approximate India grid factor of 0.82 kg CO2e/kWh.
- Diet uses simplified per-meal estimates for meat-based and plant-based meals.
- Recycling/composting is represented as a small daily saving.
- Benchmarks are rough daily kg CO2e comparisons for user motivation.

For a production-grade calculator, these factors should be updated with official and location-specific datasets such as:

- UK Government GHG conversion factors
- Central Electricity Authority India CO2 Baseline Database
- GHG Protocol cross-sector emission factor tools
- Our World in Data emissions datasets

## Privacy and security choices

- Data is stored in `st.session_state`, not a shared server-side file.
- CSV upload size is limited to 1 MB.
- Imported CSVs are checked for expected columns, valid dates, valid transport modes, duplicate dates, numeric values, non-negative values, and reasonable maximum values.
- Formula-like CSV cells starting with `=`, `+`, `-`, or `@` are neutralized before storage/export.
- The app does not require login, API keys, or permanent personal-data storage.

## Limitations

- This is an awareness tool, not a formal carbon accounting system.
- Emission factors are approximate and may not represent every location, vehicle, diet, home size, or electricity provider.
- More accurate estimates would need fuel economy, household size, city-specific electricity data, and detailed food/consumption categories.

## Demo flow

1. Open **Log today** and enter daily activity values.
2. Go to **Dashboard** to view total footprint, trend, top category, and goal gap.
3. Open **Insights** to see personalized recommendations.
4. Use **Action tracker** to select reduction commitments.
5. Open **Methodology** to inspect assumptions and security decisions.

# Microgrid Demo App

Interactive presentation tool for Newkirk et al. 2026 — comparing DC-coupled solar microgrids, natural gas generation, and grid electricity across CONUS.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Structure

- `app.py` — Main Streamlit app
- `map_panel.py` — Interactive CONUS map with H3 hex choropleth
- `location_panel.py` — Location breakdown with gas price slider
- `deep_dives.py` — Expandable sections with static plots
- `ng_recompute.py` — Gas price slider backend
- `lib/` — Self-contained copy of AI Microgrids model code for NG LCOE recomputation
- `data/` — Pre-computed LCOE results (merged dataset with 3yr NG construction)
- `assets/` — Static plot images

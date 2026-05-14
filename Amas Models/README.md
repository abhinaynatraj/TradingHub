# Amas Models

Personal research tool: turn Amas mentorship materials into formalized model specs, backtest each model over 14 years of NQ/ES 1m data, and visualize results in a single-page dashboard.

Mirrors `Fractal Sweep/`'s pattern.

## Quick start

```bash
# from Statistic.ally/
pip install duckdb pandas numpy

# generate model_stats.json for all models on NQ
cd "Amas Models"
python3 engine/model_stats.py

# run tests
python3 -m pytest tests/ -q

# serve dashboard from repo root
cd ..
python3 -m http.server 8001
# open http://localhost:8001/Amas Models/model_dashboard.html
```

See [`CLAUDE.md`](CLAUDE.md) for engine details, [`docs/model_specs.md`](docs/model_specs.md) for the formalized models.

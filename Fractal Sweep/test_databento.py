#!/usr/bin/env python3
"""
Minimal Databento connection test.
Run: python3 test_databento.py
"""
import databento as db

import os
API_KEY = os.environ.get("DATABENTO_API_KEY", "")  # set via: export DATABENTO_API_KEY=your_key

client = db.Historical(API_KEY)

print("Testing NQ.c.0 with stype_in=continuous...")
try:
    cost = client.metadata.get_cost(
        dataset  = "GLBX.MDP3",
        symbols  = ["NQ.FUT"],
        schema   = "ohlcv-1m",
        stype_in = "parent",
        start    = "2024-01-01",
        end      = "2024-01-05",
    )
    print(f"  NQ cost estimate: ${cost:.4f}  ✅")
except Exception as e:
    print(f"  NQ error: {e}")

print("Testing ES.c.0 with stype_in=continuous...")
try:
    cost = client.metadata.get_cost(
        dataset  = "GLBX.MDP3",
        symbols  = ["ES.FUT"],
        schema   = "ohlcv-1m",
        stype_in = "parent",
        start    = "2024-01-01",
        end      = "2024-01-05",
    )
    print(f"  ES cost estimate: ${cost:.4f}  ✅")
except Exception as e:
    print(f"  ES error: {e}")

# Also test what the library version is
print(f"\ndatabento version: {db.__version__}")

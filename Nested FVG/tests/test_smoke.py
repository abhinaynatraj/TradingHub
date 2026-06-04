"""End-to-end smoke test. Skips automatically if the shared DB is absent."""
import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

ENGINE = Path(__file__).parent.parent / 'engine'
DATA = Path(__file__).parent.parent / 'data'
DB = Path(__file__).parent.parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'


@pytest.mark.skipif(not DB.exists(), reason="shared DuckDB not present")
def test_end_to_end_one_pairing():
    r = subprocess.run([sys.executable, 'build_stats.py', '--pairings', '1m_5m', '--no-smt'],
                       cwd=str(ENGINE), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    manifest = json.loads((DATA / 'manifest.json').read_text())
    assert '1m_5m' in manifest['pairings']
    pm = manifest['pairings']['1m_5m']

    pq = DATA / pm['file']
    n_rows = duckdb.connect().execute(
        f"SELECT COUNT(*) FROM read_parquet('{pq}')").fetchone()[0]
    assert n_rows == pm['n_trades']

    wr = duckdb.connect().execute(f"""
        SELECT 100.0 * SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN outcome IN ('win','loss','scratch') THEN 1 ELSE 0 END),0)
        FROM read_parquet('{pq}')
    """).fetchone()[0]
    assert abs((wr or 0) - pm['agg']['wr']) < 0.1

    bad = duckdb.connect().execute(f"""
        SELECT COUNT(*) FROM read_parquet('{pq}')
        WHERE outcome NOT IN ('win','loss','scratch','expired')
    """).fetchone()[0]
    assert bad == 0

// Analysis/dashboard/shared.js
// Theme: shared with the rest of Statistic.ally via localStorage 'hub-theme'
(function () {
  const t = localStorage.getItem('hub-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', t);
})();

window.toggleTheme = function () {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('hub-theme', next);
};

// DuckDB-Wasm singleton
let _dbPromise = null;
async function getDB() {
  if (_dbPromise) return _dbPromise;
  _dbPromise = (async () => {
    const duckdb = await import('https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm');
    const JSDELIVR_BUNDLES = duckdb.getJsDelivrBundles();
    const bundle = await duckdb.selectBundle(JSDELIVR_BUNDLES);
    const worker_url = URL.createObjectURL(
      new Blob([`importScripts("${bundle.mainWorker}");`], { type: 'text/javascript' })
    );
    const worker = new Worker(worker_url);
    const logger = new duckdb.ConsoleLogger();
    const db = new duckdb.AsyncDuckDB(logger, worker);
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
    URL.revokeObjectURL(worker_url);
    return db;
  })();
  return _dbPromise;
}

window.loadParquet = async function (path, alias) {
  const db = await getDB();
  const conn = await db.connect();
  // Register the parquet file via fetch
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`Failed to fetch ${path}: ${resp.status}`);
  const buf = new Uint8Array(await resp.arrayBuffer());
  await db.registerFileBuffer(`${alias}.parquet`, buf);
  await conn.query(`CREATE OR REPLACE VIEW ${alias} AS SELECT * FROM read_parquet('${alias}.parquet')`);
  await conn.close();
};

window.query = async function (sql) {
  const db = await getDB();
  const conn = await db.connect();
  try {
    const result = await conn.query(sql);
    return result.toArray().map(r => Object.fromEntries(
      Object.entries(r).map(([k, v]) => [k, typeof v === 'bigint' ? Number(v) : v])
    ));
  } finally {
    await conn.close();
  }
};

window.fmtPct = (x) => (x == null || isNaN(x)) ? '—' : (x * 100).toFixed(1) + '%';
window.fmtNum = (x) => (x == null || isNaN(x)) ? '—' : Number(x).toLocaleString();

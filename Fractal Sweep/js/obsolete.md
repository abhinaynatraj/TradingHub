# Obsolete Code Archive

Code archived during the 2026-05-04 refactor from the monolithic `model_dashboard.html`.
These files are **not imported** by any active module — pure reference.

| Item | Original Lines | Reason | Replaced by |
|------|---------------|--------|-------------|
| `window._maeSegment` / `window._mfeSegment` | 825-826 | Noop getter/setter stubs. Always returned `'all'`, setter did nothing. | — |
| `switchExcSeg()`, `switchMAESeg()`, `switchMFESeg()` | 835-842 | Segment switching UI removed, locked to `'all'`. No HTML bindings. | `_excSegment = 'all'` in state.js |
| `TSPOT_CFG` + `tspot_breakdown` demo data | 1001-1036 | 36 lines of fabricated data. Never consumed by any tab/DOM element. | — |
| `CLASSIFICATION_DATA = {}` | 1116 | Always-empty fallback. Real path checks `D.by_classification`. `CLS_META` kept. | — |
| `barChart()` SVG bar chart | 1167-1194 | Replaced by `lineChart()` + canvas-based charts. Zero call sites. | `lineChart()` |
| `renderHeatmap()` SVG heatmap | 1278-1292 | Edge tab builds heatmaps inline in `renderEdgeStudy()`. Zero call sites. | Inline in `renderEdgeStudy()` |
| `comboTable()` combo table | 1294-1305 | Edge tab builds combo tables inline. Zero call sites. | Inline in `renderEdgeStudy()` |
| `fmtDate()` | 1780-1784 | `fmtDateRange()` is the formatter actually in use. No call sites. | `fmtDateRange()` |
| `switchMode()`, `switchCisd()` | 1776-1777 | Mode/CISD are hardcoded in `renderControls()`. Zero call sites. | `switchModel()` |
| `drawGroupedBars()` canvas | 2533-2609 | Walk-forward uses `drawLineCanvas()` / `drawHistCanvas()` locals. | Local canvas helpers |
| `drawLineChart()` canvas | 2611-2661 | Same — local helpers used. Zero call sites. | Local canvas helpers |
| `drawScatterPlot()` canvas | 2663-2710 | Same — zero call sites. | Local canvas helpers |
| `renderSweepMAEAnalysis()` | 4786-4836 | Superseded MAE panel. Target DOM IDs may not exist. | `renderMAEStudy()` |
| `drawSweepMAEBell()` canvas | 4884-4936 | Helper for `renderSweepMAEAnalysis()`. Dead by association. | — |
| `renderDistributionStudy()` | 5449-5451 | Superseded distribution study panel. Zero call sites. | `renderMAEStudy()` / `renderMFEStudy()` |
| `_renderDistSection()` | 5454-5465 | Helper for `renderDistributionStudy()`. Dead by association. | — |

## Why Archive?

- **Debugging reference:** Old implementations preserved for comparison
- **Historical context:** Shows what the dashboard evolved from
- **Recovery:** Code can be restored if needed
- **Safe to delete:** Once refactor is stable, these files can be deleted with zero impact

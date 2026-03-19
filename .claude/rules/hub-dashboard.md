---
paths:
  - "index.html"
---

# Hub Dashboard Rules

## Adding a New Project Card

1. Add an entry to the `PROJECTS` array (id, title, subtitle, desc, json, link, color, icon, type)
2. Add a `if (project.type === 'yourtype')` block in `loadStats()` returning `{ label1, val1, cls1, label2, val2, cls2, label3, val3, cls3, dateRange }`
3. `cls` values: `'pos'` (green), `'neg'` (red), `'neutral'`

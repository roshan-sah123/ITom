---
name: frontend-engineering
description: Comprehensive enterprise frontend design system, high-contrast obsidian UI tokens, high-scale telemetry tabular grid UX, interactive chart drill-downs, and client-side security standards.
---

# Enterprise Frontend Engineering & UI/UX Skill

## 1. Scope & Design Philosophy
This skill defines industry-standard frontend engineering practices for mission-critical enterprise dashboards, IT Operations Management (ITOM) platforms, and telemetry observation portals.

### Core Philosophy: Anti-"AI Slop" Visual Craftsmanship
* **No Generic / Muddy Designs**: Reject washed-out brown glows, generic unstyled templates, and clunky layouts.
* **High-Contrast Obsidian Surfaces**: Use structured dark-mode depth layers (`#0B0B0B` canvas, `#141414` cards, `#16161A` top headers, `#222222` subtle borders).
* **Domain Theme Accents**: Differentiate operational domains with sharp, purposeful accent palettes (Emerald for Health/Compliance, Electric Blue for Intune, Amber for SolarWinds/Warning, Purple for DEX, Orange for Active Operations).
* **Instant Perceived Performance**: Sub-50ms initial paint via progressive two-phase data ingestion.

---

## 2. Design Tokens & Visual Hierarchy

```css
:root {
  /* Canvas & Surfaces */
  --bg-canvas: #0B0B0B;
  --bg-surface-1: #141414;
  --bg-surface-2: #16161A;
  --bg-surface-elevated: #1C1C22;
  
  /* Borders & Dividers */
  --border-subtle: #222222;
  --border-card: rgba(255, 255, 255, 0.08);
  --border-focus: #F97316;
  
  /* Domain Semantic Accents */
  --accent-ops: #F97316;        /* Orange */
  --accent-intune: #3B82F6;     /* Electric Blue */
  --accent-solarwinds: #F59E0B; /* Amber */
  --accent-cmdb: #10B981;       /* Emerald Green */
  --accent-dex: #A855F7;        /* Purple */
  --status-up: #10B981;         /* Emerald */
  --status-warning: #F59E0B;    /* Amber */
  --status-critical: #EF4444;   /* Crimson Red */
  
  /* Typography */
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
}
```

---

## 3. High-Scale Telemetry Table & Pagination Standards

### Component Architecture & Layout
Every high-scale data table (1,000 to 50,000+ assets) must implement the unified **3-Zone Enterprise Table Controller**:

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ZONE 1: TOOLBAR & REAL-TIME SEARCH (200ms Debounced Input + CSV Export + Active Filter Pills)          │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ZONE 2: STICKY DATA GRID (Zebra striping, monospace IPs/Serials, semantic status badges, tooltips)     │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ZONE 3: 3-PART FOOTER CONTROLLER                                                                      │
│ ┌───────────────────────────┬───────────────────────────────────────────┬────────────────────────────┐ │
│ │ "Showing 1–50 of 25,987"  │ Page Selector [10, 25, 50, 100 per page]  │ « ‹ 1 2 3 ••• 520 › » Nav  │ │
│ └───────────────────────────┴───────────────────────────────────────────┴────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Invariant Rules for Pagination Controllers:
1. **Mathematical Anchor Repositioning**:
   When changing page sizes (e.g., from 50 to 10), keep the current entity visible:
   $$\text{New Page} = \min\left(\left\lfloor \frac{(\text{Current Page} - 1) \times \text{Old Size}}{\text{New Size}} \right\rfloor + 1, \; \text{Total Pages}\right)$$
2. **Scroll Position Reset**:
   Always reset the table container's scroll position (`tableContainer.scrollTop = 0`) when switching pages to prevent disorienting jumps.
3. **Search & Filter Preservation**:
   Filtering must dynamically recalculate `totalPages` and update the record counter (e.g., `Showing 1–50 of 3,442 matching Endpoints (filtered from 25,987 total)`).

---

## 4. Interactive Charts & Drill-Downs

* **Chart.js / Canvas Integration**:
  - Always clean up previous chart instances with `chartInstance.destroy()` before re-rendering to prevent canvas memory leaks.
  - Slices/bars must support interactive click events that automatically filter the corresponding data table and scroll to the grid view smoothly.
  - Tooltips must include helpful hints (e.g., `💡 Click slice to filter table`).

---

## 5. Security & DOM Sanitization Standards

* **Mandatory XSS Prevention**:
  Never use raw `innerHTML` with unsanitized server data. All user, hostname, model, and serial number inputs must pass through `escapeHtml()`:
  ```javascript
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
  ```

---

## 6. Accessibility (A11y) & Unintegrated Tab Governance

* **Accessibility & Keyboard Navigation**:
  - Table containers must provide `role="region"` and `aria-label="Operational Telemetry Grid"`.
  - Pagination navigation buttons must maintain `aria-label="Go to Page X"` and `aria-current="page"` on active page indicators.
* **Non-Integrated Sections Rule (GEMINI.md Invariant)**:
  - Any tab or module without live API ingestion attached must strictly render clean "Coming Soon / Phase 2" pipeline cards.
  - Never fabricate or hardcode simulated/mock numbers for unintegrated domains.


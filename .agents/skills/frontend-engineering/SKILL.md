---
name: frontend-engineering
description: Guidance for distinctive, intentional enterprise frontend engineering and UI/UX design for ITOM telemetry, hybrid server infrastructure, and CMDB platforms. Combines studio-grade visual craftsmanship with high-scale tabular data UX, 8pt spatial discipline, modular component isolation, and zero-hallucination API binding. Use whenever designing, building, or refactoring the frontend.
license: Apache-2.0
compatibility: Modern Evergreen Browsers, ES6 Modules, Vanilla CSS / Tailwind v4
metadata:
  version: "3.0.0"
  domain: "IT Operations Management & High-Scale Telemetry Observability"
  framework: "Design-Studio Grade Component Architecture"
---

# Enterprise ITOM Frontend Engineering & Visual Design Standard

## 1. The Design Studio Mindset & Subject Grounding

Approach this role as the **design lead at an elite digital product studio** tasked with building a mission-critical command portal for global enterprise infrastructure. The client has rejected cliché, unstyled templates, clunky SaaS cards, and AI-generated defaults. You are building an authoritative, distinctive operational instrument.

### Ground in the Subject Matter
This is **IT Operations Management (ITOM)**, Network Operations Centers (NOC), and Enterprise Architecture:
- **The Users**: NOC Tier-3 incident commanders, cloud infrastructure engineers, and enterprise asset managers.
- **The Data Reality**: 1,572 hybrid server nodes across 71 global campus sites (SolarWinds Orion), 27,412 workplace laptops and mobile devices (Microsoft Intune), and 28,984 universal Configuration Items (PostgreSQL 16 CMDB).
- **The Primary Job**: Enable instant, sub-second operational triage, surface critical failures before outages escalate, reconcile asset configurations, and guarantee 100% data integrity without cognitive overload.

---

## 2. Calibrate Against & Purge AI Design Tells

Avoid the default visual habits that instantly signal an uncrafted, AI-generated dashboard:
1. **The Generic SaaS-Card Kit**: Do not chop every screen into identical rounded cards with the same soft drop-shadow (`rgba(0,0,0,0.1)`) and decorative gradient washes.
2. **Template Chrome**:
   - Do **NOT** put tracked-out `ALL-CAPS` eyebrow labels above every single heading.
   - Do **NOT** join metadata strings with repetitive middle dots (`A · B · C`).
   - Do **NOT** append generic `→` or `>` arrows to every button or label.
   - Do **NOT** use numbered markers (`01 / 02 / 03`) unless the content is genuinely an ordered sequence or timeline.
3. **Accenting Words in Headlines**: Never highlight a single word in a heading with a gradient or different color just for effect.
4. **Scattered, Un-orchestrated Motion**: Eliminate bounce effects and unnecessary fade-and-slide-up transitions on card hover. Only use motion that directly answers a human interaction (e.g., opening a drawer, expanding a row, confirming a sync).

---

## 3. Core Enterprise Directives & Non-Negotiables

### 3.1 Zero-Hallucination Policy
- **Never display simulated, mock, or hardcoded figures** for live operational domains.
- All numbers for Hybrid Servers must bind dynamically to live backend REST endpoints (`/api/v1/solarwinds/*`).
- All numbers for Digital Workplace Endpoints must bind dynamically to `/api/v1/intune/*`.
- All numbers for CMDB must bind dynamically to `/api/v1/cmdb/*`.
- Non-integrated modules (e.g., Network CMDB, Telecom) must strictly render clean "Phase 2 Pipeline" state cards.

### 3.2 Strict Domain Boundary Separation
- **Operational Telemetry (Infrastructure Analytics)**: Live health, CPU/RAM utilization %, ping latency, active alerts, 24h continuous SLA trends, and campus facility sparklines.
- **Asset Accounting (CMDB Explorer)**: Configuration Item inventory, serial numbers, discovery provenance (Intune vs. SolarWinds), hardware baselines, and relationship topology. **Zero operational noise** (no CPU/RAM gauges or ping latency).

### 3.3 Component Isolation & Error Boundaries (Anti-Monolith Invariant)
- **Never write monolithic scripts with shared mutable global variables**. A syntax error or null pointer in one widget must never halt the JavaScript thread or freeze tables.
- Every widget and table must be encapsulated in an isolated module with its own error boundary:

```javascript
export async function mountComponent(targetId, fetchFn, renderFn) {
  const el = document.getElementById(targetId);
  if (!el) return;
  try {
    el.innerHTML = renderSkeleton();
    const data = await fetchFn();
    renderFn(el, data);
  } catch (err) {
    el.innerHTML = renderInlineError("Data unavailable. Upstream integration offline.");
    console.error(`[ComponentError: ${targetId}]`, err);
  }
}
```

---

## 4. Design Tokens & Visual Hierarchy (High-Contrast Obsidian)

### 4.1 Base Palette (4–6 Deliberate Hex Values)
```css
:root {
  /* Canvas & Depth Surfaces */
  --bg-canvas:           #0B0B0B;   /* Deep obsidian background */
  --bg-surface-1:        #141414;   /* Primary card and panel surface */
  --bg-surface-2:        #1A1A1E;   /* Secondary surface & table header */
  --bg-surface-elevated: #222228;   /* Popover, modal, and drawer surface */

  /* Structural Borders */
  --border-subtle:       #222222;   /* 1px structural container borders */
  --border-card:         rgba(255, 255, 255, 0.08); /* Card rim highlight */
  --border-focus:        #F97316;   /* Active outline and focus states */

  /* Deliberate Domain Accents */
  --accent-ops:          #F97316;   /* Operational highlights & alert badges */
  --accent-intune:       #3B82F6;   /* Microsoft Intune workplace blue */
  --status-healthy:      #10B981;   /* High Health, Compliant, Up */
  --status-warning:      #F59E0B;   /* Warning, Degraded, InGracePeriod */
  --status-critical:     #EF4444;   /* Low Health, Down, Noncompliant */
  --accent-cmdb:         #8B5CF6;   /* CMDB CI Accounting & Topology */
}
```

### 4.2 Typography & Type Scale
- **Display & UI Body**: `'Inter', -apple-system, BlinkMacSystemFont, sans-serif`. Use sentence case for labels. Line lengths under 80 characters.
- **Monospace Telemetry**: `'JetBrains Mono', 'Fira Code', monospace` for IP addresses, MACs, UUIDs, serials, and timestamps.
- **Scale**:
  - Page Title: `20px` (`1.25rem`), font-weight: `600`, tracking: `-0.01em`.
  - Section Headings: `15px` (`0.9375rem`), font-weight: `600`.
  - Body Text: `13px` (`0.8125rem`), font-weight: `400`, line-height: `1.5`.
  - Data / Monospace: `12px` (`0.75rem`), font-weight: `500`.

### 4.3 Sizing & Spacing Architecture (The 8-Point Spatial Grid)
Every measurement is a disciplined multiple of 8px (with 4px for micro-spacing):

| UI Component | Dimensions | Padding / Gap | Margin | Behavior |
|---|---|---|---|---|
| **Global Header** | Height: `64px` | `px-6 py-0` (`24px`) | `0` | Sticky (`top: 0, z-index: 100`) |
| **Module Navigation Bar** | Height: `52px` | `px-6 py-0` (`24px`) | `0` | Sticky beneath header (`top: 64px`) |
| **Workspace Viewport** | Height: `calc(100vh - 116px)` | `p-6` (`24px`) | Max: `1920px` | Scrollable main viewport |
| **Executive KPI Row** | Height: `108px` | `p-4` (`16px`) | Margin-bottom: `24px`, Gap: `16px` | 4-column CSS grid |
| **Analytics Charts Row** | Height: `~280px` | `p-5` (`20px`) | Margin-bottom: `24px`, Gap: `16px` | 2, 3, or 4 columns |
| **Data Grid Container** | Min-height: `500px` | `p-0` | Margin-bottom: `24px` | Border: `1px #222`, Rounded: `8px` |
| **Table Header Row** | Height: `44px` | `px-4 py-0` | `0` | Sticky (`top: 0, bg: #16161A`) |
| **Table Data Rows** | Height: `48px` | `px-4 py-2` | `0` | Alternating zebra: `#141414` / `#111111` |
| **3-Part Footer** | Height: `52px` | `px-6 py-0` | `0` | Flex justify-between (`bg: #141414`) |
| **Module Termination Gap** | Height: `48px` | — | — | Mandatory gap after the 8th module |
| **System Status Strip** | Height: `40px` | `px-6 py-0` | `0` | Background: `#0E0E10`, Border-top: `1px #1E1E24` |
| **Global Footer** | Height: `56px` | `px-6 py-0` | `0` | Background: `#0B0B0B`, Border-top: `1px #1A1A1A` |

---

## 5. The Two-Pass Design Process: Plan, Review, Build, Critique

Before writing or editing frontend code, execute two deliberate passes:

### Pass 1: Design Specification
1. **Identify the focal anchor**: Choose **one** element to be the memorable feature (e.g., the interactive Health Donut with slice-filtering, or the 24h Campus SLA Trend line). Keep everything around it quiet and disciplined.
2. **Establish the layout concept**: Use ASCII/dotted wireframes to define spatial relationships and alignment before writing HTML.
3. **Define CSS selector specificity**: Use flat, modular class names (`.itom-table`, `.itom-kpi-card`, `.itom-filter-pill`). Never use nested element selectors that accidentally cancel out padding or margins.

### Pass 2: Self-Critique & "Chanel's Rule"
Review the plan against the brief:
- *Did I default to generic SaaS cards?* If yes, replace with high-contrast obsidian surfaces and structural dividers.
- *Did I add visual clutter that does not convey information?* Apply Coco Chanel's rule: take a look at the design and **remove one accessory**.
- *Is the copy clear and active?* (See Section 7).

---

## 6. High-Scale Telemetry Data Table Standard

Every high-scale data grid (1,500 to 28,000+ assets) must implement the **3-Zone Layout Pattern**:

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ZONE 1: TOOLBAR (200ms Debounced Search + Active Filter Pills + RFC-4180 CSV Export Stream)              │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ZONE 2: STICKY DATA GRID (Monospace Serials/IPs, Semantic Status Badges, Truncated Captions, Tooltips)   │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ZONE 3: 3-PART FOOTER CONTROLLER                                                                          │
│ ┌───────────────────────────┬───────────────────────────────────────────┬────────────────────────────┐  │
│ │ "Showing 1–25 of 1,572"   │ Page Selector: [10, 25, 50, 100 per page] │ « ‹ 1 2 3 ••• 63 › » Nav   │  │
│ └───────────────────────────┴───────────────────────────────────────────┴────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Table Operational Invariants:
1. **Deterministic Anchor Pagination Math**: When changing page size, always calculate the new page anchor to keep the current record in view:

   $$\text{New Page} = \min\left(\left\lfloor \frac{(\text{Current Page} - 1) \times \text{Old Size}}{\text{New Size}} \right\rfloor + 1, \; \text{Total Pages}\right)$$

2. **Scroll Reset**: Always execute `tableContainer.scrollTop = 0` on page changes.
3. **Mandatory XSS Sanitization**: All hostnames, serials, primary users, and models must pass through `escapeHtml()` before innerHTML insertion:

```javascript
export function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
```

4. **Interactive Chart Memory Safety**: Always call `chartInstance.destroy()` before re-instantiating Chart.js canvases to prevent memory leaks and ghost event listeners.

---

## 7. Writing in Enterprise Design (Microcopy & Direction)

Words in an ITOM interface exist solely to enable fast, unambiguous operational decisions:
- **Active Voice CTAs**: Name buttons by the exact action they take: `"Export CSV"` (not `"Submit"`), `"Filter High Health"` (not `"Click Here"`), `"Download Trend Report"` (not `"Download"`).
- **Plain Technical Terms**: Use the language of systems engineers. Say `"Microsoft Intune Managed Devices"` or `"SolarWinds Server Nodes"`, not marketing jargon like `"Smart Fleet Intelligence"`.
- **Errors as Direction, Not Mood**: When an API fails, never show vague apologies (`"Oops! Something went wrong"`). State exactly what happened and provide an actionable remedy:
  * *Example*: `"Unable to reach SolarWinds SWIS API at :8000. Verify backend daemon status or click [Retry Sync]."`
- **Actionable Empty States**: If a filter returns 0 rows, provide a one-click reset:
  * *Example*: `"No servers match filter 'Critical' in region 'India'. [Clear Active Filters]."`

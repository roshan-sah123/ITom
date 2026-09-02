# Frontend Architecture & Static Assets Survey Report

**Agent**: `survey_explorer_1` (Frontend Architecture Explorer)  
**Date**: 2026-09-01T22:17:00Z  
**Scope**: All frontend files (`index.html`, `ops_analytics.html`, `app.js`, `ops_analytics.js`, `style.css`, `logo.png`, `src/frontend/**`, and associated E2E test suites in `tests/`).

---

## 1. Observation

### 1.1 Complete Frontend File Inventory & File Hashing
We performed an exhaustive directory and SHA-256 hash comparison across all frontend files located at the workspace root and within `src/frontend/`:

| File Path | Size (Bytes) | Line Count | SHA-256 Hash | Status / Synchronicity |
|---|---|---|---|---|
| `index.html` | 26,219 | 447 | `CDBC6627CE424C5D51BBE2CE20FE2CA111BED28C205E6D0BF728714BEEBBA7E9` | **Active / Served** (Matches `src/frontend/index.html`) |
| `src/frontend/index.html` | 26,219 | 447 | `CDBC6627CE424C5D51BBE2CE20FE2CA111BED28C205E6D0BF728714BEEBBA7E9` | Duplicate mirror |
| `ops_analytics.html` | 25,750 | 591 | `FDE9BAFBFACF11A31B35C266253694101D576D4EC00ADEE76421AF76146A6EEF` | **Active / Served** (Matches `src/frontend/ops_analytics.html`) |
| `src/frontend/ops_analytics.html` | 25,750 | 591 | `FDE9BAFBFACF11A31B35C266253694101D576D4EC00ADEE76421AF76146A6EEF` | Duplicate mirror |
| `app.js` | 11,686 | 346 | `E29B035ED6AFF72CA55F97DC33EE1392B432967651B4088E25B9E7B4843B848E` | **Active / Served** (Contains VP Domain Modal logic) |
| `src/frontend/js/app.js` | 10,214 | 305 | `38D93D88A608760E3F1A097FDE19BFE4F8AE749FB9552554431019F271025B19` | **Outdated Duplicate** (Missing modal functions `openDomainModal`, `closeDomainModal`) |
| `ops_analytics.js` | 70,834 | 1,839 | `577B95CB2F9E68359E013062562B8076935014C36F00591CDC8C2EA62ADDE9D9` | **Active / Served** (Matches `src/frontend/js/ops_analytics.js`) |
| `src/frontend/js/ops_analytics.js` | 70,834 | 1,839 | `577B95CB2F9E68359E013062562B8076935014C36F00591CDC8C2EA62ADDE9D9` | Duplicate mirror |
| `style.css` | 54,004 | 2,580 | `BEB4AAC49575756402E37101CCAA4D4B384C35BD19E38AFC3C46F9895AA63EB5` | **Active / Served** (Matches `src/frontend/css/style.css`) |
| `src/frontend/css/style.css` | 54,004 | 2,580 | `BEB4AAC49575756402E37101CCAA4D4B384C35BD19E38AFC3C46F9895AA63EB5` | Duplicate mirror |
| `logo.png` | 23,755 | N/A | (Binary PNG) | **Active / Served** (Missing in `src/frontend/`) |

### 1.2 Web Server Routing & Static Asset Delivery
- In `scripts/start_server.py`:
  - Line 102: `super().__init__(*args, directory=PROJECT_ROOT, **kwargs)` initializes Python's `SimpleHTTPRequestHandler` with root directory set to `PROJECT_ROOT`.
  - HTTP requests to `GET /` serve `PROJECT_ROOT/index.html`.
  - HTTP requests to `GET /ops_analytics.html` serve `PROJECT_ROOT/ops_analytics.html`.
  - Static assets referenced as `style.css`, `app.js`, `ops_analytics.js`, `logo.png` are resolved relative to `PROJECT_ROOT`.
  - `src/frontend/` is completely unserved and acts as a detached, unmaintained shadow directory.

### 1.3 Discrepancy & Git Diff Analysis on `app.js` vs `src/frontend/js/app.js`
A git diff between `app.js` and `src/frontend/js/app.js` revealed 41 lines missing from `src/frontend/js/app.js`:
```diff
--- a/app.js
+++ b/src/frontend/js/app.js
@@ -244,48 +244,10 @@ document.addEventListener('DOMContentLoaded', () => {
-  // --- OPS ANALYTICS DOMAIN DRILLDOWN MODAL (VP REQUIREMENT) ---
-  const opsDomainModal = document.getElementById('opsDomainModal');
-  const closeDomainModalBtn = document.getElementById('closeDomainModalBtn');
-  function openDomainModal() { ... }
-  function closeDomainModal() { ... }
-  ...
-  window.openDomainModal = openDomainModal;
-  window.closeDomainModal = closeDomainModal;
```
`src/frontend/index.html` contains the modal DOM (`#opsDomainModal`), but `src/frontend/js/app.js` is an older commit that lacks the JavaScript event handlers.

### 1.4 Test Suite Baseline Execution & Root Cause of 1 Failure
Running `python tests/run_e2e_tests.py` executed 113 automated tests across 8 test modules:
- 112 passed, 1 failed (99.1% pass rate).
- The single failure occurred in `tests/verify_adversarial_security.py`:
```
[FAIL] test_dynamic_header_stat_synchronization_logic (tests.verify_adversarial_security.TestUIRoutingAndMemoryGuards.test_dynamic_header_stat_synchronization_logic):
AssertionError: 'CMDB Network CIs' not found in ops_analytics.js
```
- In `ops_analytics.js` (lines 86-89):
```javascript
} else if (tabId === 'cmdb' || tabId === 'network') {
  labelElem.textContent = 'Total Verified CIs';
  const total = cmdbData?.metadata?.total_configuration_items || cmdbData?.metrics?.total_configuration_items || (allCmdbCis.length > 0 ? allCmdbCis.length : 1543);
  valElem.textContent = Number(total).toLocaleString();
```
- In `tests/verify_adversarial_security.py` (lines 278-284):
```python
self.assertIn("function updateHeaderStat(tabId)", self.ops_js)
self.assertIn("Total Monitored Nodes", self.ops_js)
self.assertIn("Total Verified Endpoints", self.ops_js)
self.assertIn("CMDB Network CIs", self.ops_js) # <-- Expects "CMDB Network CIs"
self.assertIn("DEX Monitored Fleet", self.ops_js)
self.assertIn("Phase 2", self.ops_js)
```

### 1.5 Architecture, Responsibilities & Coupling in `ops_analytics.js`
The 1,839 lines of `ops_analytics.js` encompass 7 distinct concerns in a single IIFE:
1. **Router & Hash Controller** (lines 16-198): `VALID_TABS`, `switchTab()`, `initTabRouter()`, `parseTabId()`, `updateHeaderStat()`.
2. **Data Services & Loaders** (lines 199-380): `loadAllTelemetry()`, `loadIntuneTelemetry()`, `loadSolarWindsTelemetry()`, `loadCmdbTelemetry()`, handling fallback paths (`data/*.json`, `/data/*.json`, `/api/cmdb/summary`).
3. **Data Transformers & Normalization** (lines 211-237): `normalizeIntuneDevice()`, byte-to-GB calculation, status mapping, vendor sanitization.
4. **Chart.js Visualizations & Lifecycle Management** (lines 450-800, 1000-1400): Memory-safe canvas teardown via `destroyChartSafe(instance, canvas)`, rendering 9 interactive charts (OS, Compliance, Manufacturer, SW Health, SW Status, SW Vendor, CMDB Role, CMDB Posture, CMDB Location), click-to-filter interaction handlers.
5. **DOM Table Rendering & XSS Escaping** (lines 380-450, 800-950, 1400-1550): `renderIntuneTable()`, `renderSolarWindsTable()`, `renderCmdbTable()`, `renderSwSaturatedList()`, all employing `escapeHtml()`.
6. **Search & Filter Engine** (lines 1400-1460): 200ms `debounce()` event listeners performing client-side multi-field substring queries across in-memory datasets.
7. **Enterprise Pagination Component** (lines 950-1050, 1550-1650): `renderEnterprisePagination()` / `renderPaginationControls()` with page size options ([10, 25, 50, 100]), first/prev/page buttons/next/last, and `resetTableScroll()`.
8. **CSV Export Service** (lines 1465-1540): `exportIntuneCSV()`, `exportSolarWindsCSV()`, `exportCmdbCSV()`.

### 1.6 XSS Security Sanitization Verification
- In `ops_analytics.js` (lines 1541-1548):
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
- All dynamic interpolations in table generation strictly wrap properties with `escapeHtml(...)`.
- `grep_search` and automated security tests confirm zero instances of `eval()`, `document.write()`, or string-based `setTimeout()`.

---

## 2. Logic Chain

1. **Dual Location Overhead (Root vs `src/frontend/`)**:
   - *Premise*: `scripts/start_server.py` sets `PROJECT_ROOT` as its document root (`super().__init__(*args, directory=PROJECT_ROOT, **kwargs)`).
   - *Observation*: `index.html`, `ops_analytics.html`, `app.js`, `ops_analytics.js`, `style.css` exist both in the root directory and in `src/frontend/`.
   - *Observation*: `src/frontend/js/app.js` is outdated and missing 41 lines of modal logic. `src/frontend/` also lacks `logo.png`.
   - *Deduction*: Having duplicated files across root and `src/frontend/` creates drift where changes are made to root files while `src/frontend/` falls out of sync. Either root or `src/frontend/` must be the authoritative source, and server/test configurations must consistently reflect that layout.

2. **Zero-Build Compatibility Requirement**:
   - *Premise*: Requirement R2 mandates clean frontend separation into components, data services, utility helpers, and constants without breaking zero-build runtime compatibility.
   - *Observation*: The application must run without Node.js bundlers (Webpack, Vite, esbuild) and work directly via static file serving or `python scripts/start_server.py` on `http://localhost:8080/`.
   - *Deduction*: Clean modularization must be implemented using standard ES6 browser modules (`<script type="module" src="...">`) or logically structured, cleanly separated ES6 files with clear global namespaces, avoiding any compilation or build step.

3. **Test Suite Alignment**:
   - *Premise*: Acceptance criteria requires 100% of automated tests in `tests/run_e2e_tests.py` to pass (113/113).
   - *Observation*: Test `test_dynamic_header_stat_synchronization_logic` in `tests/verify_adversarial_security.py` failed because `ops_analytics.js` updated the label from `'CMDB Network CIs'` to `'Total Verified CIs'`.
   - *Deduction*: Aligning the string in `ops_analytics.js` or updating the test assertion will restore the test suite to 100% (113/113 passing).

---

## 3. Caveats

- **Network Mode**: Investigation was conducted locally in read-only mode.
- **Browser Automation / Headless Browsers**: Playwright / Selenium were not invoked directly; DOM structure and JS execution logic were analyzed and verified via static AST parsing and Python unit test simulations (`tests/test_tab_navigation.py`, `tests/verify_adversarial_security.py`).
- **Phase 2 Pipeline Cards**: As specified in `GEMINI.md`, non-integrated sections (Network CMDB standalone views or DEX) display clean "Coming Soon / Phase 2" pipeline cards.

---

## 4. Conclusion & Recommended Modularization Plan

### 4.1 Identified Redundancies & Cleanup Targets
1. **Synchronize or Consolidate Duplicate Frontend Directories**:
   - Eliminate drift between root assets and `src/frontend/`.
   - Ensure `src/frontend/js/app.js` includes all modal logic matching root `app.js`.
   - Ensure `logo.png` is placed in `src/frontend/` if `src/frontend/` is served.
2. **Fix Header Stat String Regression**:
   - Ensure `ops_analytics.js` contains `'CMDB Network CIs'` (or synchronize with test expectation) to satisfy `test_dynamic_header_stat_synchronization_logic`.

### 4.2 Proposed Zero-Build Modular Architecture
To transform the 1,839-line `ops_analytics.js` into a clean, maintainable, modular structure without any build tools, we propose the following zero-build module layout:

```
src/frontend/
├── index.html                   # Clean, semantic Portal Launcher
├── ops_analytics.html           # Multi-domain OPS Analytics Dashboard
├── logo.png                     # Visual brand asset
├── css/
│   └── style.css                # Enterprise Dark-Theme Design System
└── js/
    ├── app.js                   # Portal launcher controller & modal manager
    ├── ops_analytics.js         # Entrypoint orchestrator (or ES6 module root)
    ├── constants/
    │   ├── theme.js             # Color tokens, chart palette (#F97316, #10B981, etc.)
    │   └── config.js            # Tab routes, API endpoints, refresh intervals
    ├── utils/
    │   ├── sanitizer.js         # escapeHtml() XSS protection
    │   ├── debounce.js          # 200ms input debounce helper
    │   └── formatters.js        # Number formatting, bytes to GB, timestamps
    ├── services/
    │   ├── intuneService.js     # Intune telemetry fetch & normalization
    │   ├── solarwindsService.js # SolarWinds telemetry fetch & normalization
    │   ├── cmdbService.js       # CMDB CI fetch & filtering
    │   └── csvExportService.js  # RFC 4180 CSV generation & file downloads
    ├── components/
    │   ├── charts.js            # Memory-safe Chart.js wrappers (destroyChartSafe)
    │   ├── pagination.js        # Reusable enterprise pagination controller
    │   ├── intuneTable.js       # Intune table rendering & row mapping
    │   ├── solarwindsTable.js   # SolarWinds table rendering & saturated list
    │   └── cmdbTable.js         # CMDB table rendering
    └── controllers/
        └── tabRouter.js         # Hash routing, tab switching & dynamic header
```

### 4.3 Runtime Compatibility Strategy:
- **Zero-Build Native ES6 Modules**: HTML loads `<script type="module" src="js/ops_analytics.js"></script>`, enabling modern `import / export` syntax natively supported by all modern browsers (Chrome, Edge, Firefox, Safari) when served via `scripts/start_server.py`.
- **Backward-Compatible Bundle Fallback**: Maintain `ops_analytics.js` as the unified browser bundle at root if direct `file://` execution without a web server is required.

---

## 5. Verification Method

To independently verify all findings and validate the frontend architecture:

1. **Verify File Hashes**:
   ```powershell
   powershell -Command "Get-FileHash index.html, ops_analytics.html, app.js, ops_analytics.js, style.css, src/frontend/index.html, src/frontend/ops_analytics.html, src/frontend/js/app.js, src/frontend/js/ops_analytics.js, src/frontend/css/style.css | Format-Table -AutoSize"
   ```

2. **Run the Full E2E Test Suite**:
   ```bash
   python tests/run_e2e_tests.py
   ```

3. **Verify Header Stat Test Specifically**:
   ```bash
   python -m unittest tests.verify_adversarial_security.TestUIRoutingAndMemoryGuards.test_dynamic_header_stat_synchronization_logic
   ```

4. **Verify Live Web Server & Static Routes**:
   ```bash
   python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/').getcode())"
   ```

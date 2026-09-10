# UI & Visual Design Tokens

## High-Contrast Obsidian Design System
The ITOM Portal interface adheres to an enterprise dark obsidian visual hierarchy. Generic light modes, unstyled defaults, and low-contrast palettes are prohibited.

### Core Surface & Canvas Tokens
- **Canvas / Root Background**: `#0B0B0B`
- **Card & Container Surfaces**: `#141414`
- **Elevated Headers & Modals**: `#16161A`
- **Borders & Dividers**: `#222222` (or `rgba(255, 255, 255, 0.08)`)

### Domain Semantic Accent Tokens
- **Orange (Active Operations / Highlights)**: `#F97316`
- **Emerald Green (High Health / Up / Compliant)**: `#10B981`
- **Amber (Warning / Medium Health)**: `#F59E0B`
- **Crimson Red (Critical / Down / Low Health)**: `#EF4444`
- **Electric Blue (Intune Endpoint Telemetry)**: `#3B82F6`
- **Purple (DEX Experience Metrics)**: `#A855F7`

### Typography & Data Grids
- **Primary Font**: `'Inter', -apple-system, BlinkMacSystemFont, sans-serif`
- **Monospace Font (IPs, Hostnames, Serials)**: `'JetBrains Mono', 'Fira Code', monospace`
- **Tabular Grids**: All high-scale asset tables must use the 3-Zone Enterprise Table Controller (Debounced Search Toolbar, Sticky Data Grid, 3-Part Footer Controller with Page Size Selector & Windowed Pagination).
- **Accessibility**: Include `role="region"`, `aria-label`, and `aria-current="page"` on all interactive grid controllers.

---
name: frontend-engineering
description: Use when designing or changing the Coforge ITOM Portal frontend. Follow the running product’s evidence-first operations UI, existing HTML/CSS/JavaScript architecture, and live data states.
---

# Coforge ITOM Frontend Engineering

## Product UI to preserve

The portal is a compact, evidence-first operations workspace. Its current home screen uses a light neutral canvas, white data surfaces, restrained blue navigation and focus accents, and clear green, amber, and red status cues. The page prioritizes operational freshness and attention: a compact header and search, primary workspace navigation, an overview with source freshness, fleet summary, operator queue, source health, workspace links, and a low-priority footer.

The workspaces carry the detail. Infrastructure, Endpoints, and CMDB views use source-backed summaries, charts where they support decisions, and searchable/filterable/paginated inventory. Knowledge Centre and Automations are separate destinations; describe roadmap or unavailable functionality honestly. Preserve Coforge branding and existing copy conventions.

Do not copy the older dark Obsidian mockups or stale screenshots over the running UI. If project notes, screenshots, comments, and the live application disagree, inspect the active route and loaded styles/scripts; use the current application and source as truth. Ask the user only if the intended direction remains ambiguous after that inspection.

## Find the active implementation first

This project is a lightweight HTML/CSS/JavaScript application, not a React or Tailwind component app. Before changing a screen:

- Inspect `frontend/index.html` for the current structure and view identifiers.
- Inspect `frontend/css/style.css` for the active cascade, tokens, responsive rules, and component patterns. Later overrides may supersede earlier styles.
- Inspect `frontend/js/app.js`, `frontend/js/components/`, and shared utilities for routing, data loading, and interaction patterns. Follow the actual script paths loaded by the page; do not assume a path from an old README.
- Use the running portal at `http://localhost:8080/` when available to confirm the screen you are editing.

Prefer the existing design tokens and shared helpers. Search for an existing component or behavior before adding another one. Keep changes within the requested screen and follow its established markup and JavaScript module boundaries.

## Visual and interaction guidance

- Keep the overview calm and scannable. Use clear headings, short supporting text, restrained borders, compact labels, and deliberate whitespace. Use cards to group related information, not as decoration around every element.
- Let hierarchy come from typography, spacing, alignment, and surface contrast. Use the established blue accent for navigation and primary actions; reserve semantic colors for actual status. Do not introduce decorative gradients, arbitrary accent colors, or a different theme without a product reason.
- Keep operational numbers and charts tied to the existing API/data flow. Show loading, stale, unavailable, empty, and error states distinctly. Never fill a gap with invented live figures or trends; explain what is missing and offer a supported next step when possible.
- Preserve working search, filter, sort, pagination, export, and drill-down behavior. For large inventories, use the table toolbar and footer patterns already in the relevant workspace; do not impose one fixed table layout on every view.
- Keep the layout usable at narrow widths. Follow existing breakpoints, allow navigation to remain reachable, stack summary and chart regions when needed, and avoid forcing wide data tables to shrink unreadably.
- Preserve semantic HTML and keyboard access. Give controls clear accessible names, expose selected navigation state, keep visible focus indicators, use live regions for meaningful async status, and do not rely on color alone to communicate health or failure.
- Use safe DOM update patterns already present in the project. When HTML strings are necessary, escape untrusted values for the correct context. Reuse shared chart lifecycle helpers so rerenders do not leave duplicate instances or handlers.

## Before finishing

Review the changed screen in context, ideally in the running portal at desktop and narrow widths. Check that its visual treatment matches neighboring views, the real loading/error/empty states still make sense, and existing interactions remain intact. Run relevant project checks when the user requests them or the change warrants them; report anything that could not be verified.

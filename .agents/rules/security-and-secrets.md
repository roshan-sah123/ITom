# Security & Secrets Management

## Credential Isolation & Environment Variables
- **Never commit credentials, API keys, client secrets, or tokens to git.**
- All client IDs, tenant secrets, database passwords, and SolarWinds SWIS credentials must reside exclusively in `.env` (with schema documentation in `.env.example`).
- Runtime settings must be loaded and validated via Pydantic `BaseSettings` (`app/core/config.py`).

## DOM Sanitization & XSS Prevention
- All user input, hostname values, device names, and serial numbers rendered in DOM tables must be sanitized through `escapeHtml()`:
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
- Direct injection of raw server strings into `innerHTML` without prior sanitization is strictly prohibited.

## Upstream Monitoring Read-Only Boundary
- External integrations (Microsoft Graph, SolarWinds Orion) are strictly read-only monitoring sources.
- Any mutating HTTP requests (`POST`, `PUT`, `DELETE`, `PATCH`) targeting upstream endpoints must be rejected with `HTTP 405 Method Not Allowed`.

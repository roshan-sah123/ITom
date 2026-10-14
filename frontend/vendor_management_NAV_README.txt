ITOM portal: safe Vendor Management navigation installer
======================================================

For a first installation, run this kit in your local project as below.
For an already installed launcher, sync the updated helper files and hard-refresh;
you do not need to rerun the installer to remove the logo.
No attached, cached, or online index.html was replaced. The installer reads
YOUR current frontend/index.html, not an older downloaded portal page.

Place these four new files in the real ITom/frontend folder:
  install_vendor_management_nav.py
  vendor_management_nav.css
  vendor_management_nav.js
  vendor_management_NAV_README.txt

Keep the latest existing vendor_management.html and
vendor_management_server.py alongside them. Do not replace those companion
files or your database with this kit. Python 3.8+ is sufficient; no packages.

INSTALL
-------
1. Sync/download the new files and close editors writing index.html.
2. Open a terminal at the ITom project root (the parent of frontend).
3. Optional check (writes nothing):
     python frontend/install_vendor_management_nav.py --dry-run
4. Install:
     python frontend/install_vendor_management_nav.py
   Use python3 instead of python on systems that require that name.
5. Hard-refresh your original main portal (Ctrl+Shift+R / Cmd+Shift+R).
   Expect Vendor Management text only (no logo), immediately after Automations.
6. If the companion is not already running, use its existing launch command.
   Default database setup, from the project root:
     python frontend/vendor_management_server.py
   If you previously used --database, keep using the SAME absolute path:
     python frontend/vendor_management_server.py --database "<your existing absolute database path>"
   Do not start a second process on port 8081. Do not choose a new database
   path unless you intentionally want separate empty data.
7. Click Vendor Management. It opens the latest adjacent companion served at
     http://127.0.0.1:8081/vendor_management.html
   in a NEW TAB. The main portal stays open. Verify the form loads and your
   expected saved records are present before making edits.

WHAT CHANGES / SAFETY
--------------------
Only three insertions are made to the actual local frontend/index.html:
- a semantic anchor with accessible Vendor Management text only (no logo);
- one local stylesheet reference before </head>;
- one deferred local script reference before </body>.
No existing source is reformatted or replaced. UTF-8 BOMs and existing line
endings remain intact. Styling is scoped to the new link. It deliberately has
no nav-tab class or data-view so ordinary portal tab handlers do not claim it.
The script stops click/auxclick bubbling without cancelling normal navigation.
For older installations, it also removes only the original decorative square
span directly inside the known Vendor Management anchor (exact ID and class).
The Vendor Management label, URL, target="_blank", and other icons remain intact.
The old glyph can remain in index.html source; the updated script removes it
from the displayed DOM when loaded. New installations omit it from source.

Before replacing index.html atomically, the installer writes and verifies an
exact-byte, uniquely named backup in PROJECT/.vendor-management-backups,
outside frontend, and prints its path and SHA-256 hash. Serve only frontend
(or your application's intended document root), not the whole project:
backups and database directories must never be public web content.

An unchanged second run is a no-op, including a verified older installation
with the original glyph: it is not duplicated or rewritten. Unrecognized
existing Vendor Management navigation, partial kit references,
absent/ambiguous Automations targets, unsupported
containers, missing head/body closures, non-UTF-8 input, <base href>, symlinks,
and missing companion/assets cause refusal without changing index.html.
The installer accepts static <a> or <button> tabs, including nested spans,
data-view=automation(s), and ordinary list-item navigation. Dynamic navigation
or a different portal structure needs integration against the actual source;
it is not guessed. Do not force the installer against the old cached page.
Concurrent edits are checked before replacement; avoid editing/sync conflicts
while running it. A crashed install may leave install.lock in the backup
folder: confirm no installer is running before manually removing that lock.

ROLLBACK
--------
The installer prints an exact copy command using the unique backup path.
Keep that path. Close editors and first save any later index edits you want to
keep: restoring a backup would discard those later edits. You can instead copy
the chosen index-<timestamp>-<uuid>.html.bak from .vendor-management-backups
back to frontend/index.html using your file manager, then hard-refresh.
The three helper files may remain; without references they are inactive.
No rollback operation changes the companion or its database.

SCOPE AND TROUBLESHOOTING
-------------------------
This is a LOCAL-ONLY launch link, not an embedded form, same-origin API
integration, shared server deployment, or shared authentication. 127.0.0.1
means the computer running the browser; every user needs their own local
companion if they use this link. It never inherits the main portal login.
The server continues to use its existing database handling and validation.
Inline form integration is NOT implemented by this logo-only update. The link
intentionally still opens the local companion in a new tab. Safe integration
requires fresh authoritative frontend/index.html, frontend/js/app.js,
frontend/js/api.js, app/main.py, and app/core/config.py (exclude secrets).
Cached portal sources are stale and must not be used to replace current files.
No backend, database, IIS, authentication, port 8080, or other navigation is changed.

If the form is unreachable, check the existing companion process and port
8081, then open the URL directly. If the old logo remains, confirm the portal
serves the updated vendor_management_nav.js and hard-refresh its cache.
If the link itself is absent, confirm the main portal serves your installed
local index.html.
If CSS/scripts are blocked by portal Content Security Policy, or a main
router captures all clicks in the capture phase or replaces the navigation
at runtime, that deployment needs a source-aware integration. Do not weaken
security policies or replace the current index with an older cached copy.

Validation performed for this kit uses synthetic portal fixtures and a mocked
browser DOM, not your unavailable current portal. Confirm the placement and
new-tab behavior once locally after installation.

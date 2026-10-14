ITom Vendor Management — isolated local companion
Portal/Phone fields revision — 14 October 2026.
Local page marker: Fields revision 2026-10-14.

UPDATED FEATURE FILES (keep all four in the existing frontend folder)
  vendor_management.html
  vendor_management_server.py
  vendor_management_test.py
  vendor_management_README.txt
Only these Vendor Management files change. No main ITom file, navigation,
IIS/SSO configuration, dependency, backend module or application database is
modified or imported. Runtime: Python 3.9+ standard library and a modern
browser supporting native dialog, Unicode property escapes and Web Crypto.
There are no runtime dependencies to install.

RESTART / START (from the ITom project root)
1. Stop the existing vendor companion with Ctrl+C in its own terminal.
2. Back up data/vendor_management.db (or your existing --database path)
   with the companion stopped.
3. Replace the four feature files in frontend with these updated versions.
4. Run (reuse your existing --database argument, if any):
     python frontend/vendor_management_server.py
   If previously started with --database, use that SAME dedicated database
   path, not a new filename. Otherwise your saved records will appear missing.
5. Open or hard-refresh:
     http://127.0.0.1:8081/vendor_management.html
Keep that process running. Uploading source alone does not restart your local
service. The running server reads HTML once at startup; refreshing the browser
without restarting it will still show the old page. Select Phone and look for
exactly Phone number, Contact person name and Account ID (no extension/notes).
Select Portal and confirm the separate What to do and How to do cells, plus
its unchanged mandatory SOP message. The footer shows Fields revision 2026-10-14.
In PowerShell, confirm the local file:
  Select-String -Path frontend/vendor_management.html -SimpleMatch 'Fields revision 2026-10-14'
Then check what the running server serves:
  (Invoke-WebRequest http://127.0.0.1:8081/vendor_management.html).Content | Select-String -SimpleMatch 'Fields revision 2026-10-14'
If only the file has the marker, restart the known companion process. Existing ITom ports 8080/8000, IIS and SSO stay unchanged. Do not open
via file:// or port 8080: HTML and API must share this companion's origin.
The service stays bound to 127.0.0.1:8081. If the port is occupied, stop only
the known companion process before restarting; do not stop unrelated services.

FORM WORKFLOW
- Type any vendor name (1–100 normalized characters). There is no vendor
  dropdown, predefined vendor list, or vendor type field.
- Check one or more of Phone, Email, Portal and Other. Other requires a custom
  method name (1–80 characters) and has its own independent steps.
- Portal has two distinct required multiline cells: What to do and How to do.
  They appear side by side on desktop, stacked at widths up to 650px. Each
  accepts nonblank text up to 2,000 normalized characters, preserving line
  breaks/tabs. NFKC and CRLF/CR-to-LF normalization apply; other control and
  invisible format characters are rejected by both browser and server.
  Fields are enabled/required and sent only while Portal is selected. Drafts
  survive toggles and SOP Cancel/Escape; Clear resets them. Submit snapshots
  both fields so background edits cannot alter the pending save or exact retry.
  Portal has NO numbered steps or URL field. It requires a NEW SOP upload
  on EVERY submission selecting Portal, even with Phone, Email or Other.
  Submit opens "Portal SOP is mandatory"; Yes reveals the file picker and
  "Attach SOP and save". No is hidden, and both browser and server reject a
  no-attachment bypass. Cancel/Escape retain the draft without saving.
  Existing generic or Portal-associated SOPs do not satisfy a new submission.
- Phone has NO numbered steps. It collects:
    Phone number * — 3–20 ASCII digits, maximum 40 normalized characters;
      optional leading +, spaces, parentheses, dots and hyphens. Stored as
      text, not an integer; international prefixes/leading zeros remain.
    Contact person name — optional; blank or omitted saves as an empty string.
      When provided, 1–100 normalized characters with at least one letter or
      digit. A team/contact name is allowed.
    Account ID * — 1–100 normalized characters, at least one letter or digit;
      stored as text, preserving leading zeros and case.
  These are the ONLY Phone form fields and keys in new browser payloads.
  Extension and Phone notes are no longer collected or displayed as fields;
  previously stored values remain in SQLite and GET responses, including
  after a new three-field Phone save. They are not silently cleared.
  Required fields apply only while Phone is selected. Hidden fields are
  disabled and excluded from the payload. All drafts survive method toggles
  and SOP Cancel/Escape. Clear resets them. Controls/invisible characters reject.
  Number validation is a bounded syntax check, not verification of ownership
  or reachability. No telephone call, tel link or account lookup is performed.
- Only Other reveals Step 1, Step 2, Step 3, etc. Add/remove steps; remaining
  numbers update automatically. Keep 1–30 nonblank steps, each at most 2,000
  normalized characters. The last step cannot be removed. Toggling preserves
  its unsaved name/steps. Only Other steps are sent. Clear resets drafts only.
- Email reveals an "Email ticket details" section, with no numbered steps:
    Vendor support email * — one plain email address, maximum 254 characters.
    Subject template * — 1–200 normalized characters, single line.
    Opening / header text (greeting) — optional, maximum 2,000 characters.
    Message body template — optional, maximum 10,000 characters.
  Email uses the details below; no numbered steps are required. Address/subject
  are required only when Email is checked. The email fields are not rebuilt
  when toggling: all drafts survive toggles and SOP Cancel/Escape. Clear resets
  them. Submit snapshots the template before the SOP confirmation; changing
  background fields cannot change the pending save or an exact retry.
  "Header" means greeting/opening text, NOT raw SMTP headers. Greeting and
  body allow newlines/tabs, normalize CRLF/CR to LF and use Unicode NFKC;
  other control/invisible characters reject. Subject rejects CR/LF and other
  controls before normalizing whitespace. Address uses NFKC/outer trim,
  preserves local-part case and lowercases the domain. The supported syntax
  is ASCII dot-atom local part (max 64), with a dotted domain (labels max 63).
  Display names, recipient lists, quoted/internationalized local parts and
  raw Unicode domains are not accepted; use a plain address/punycode domain.
  Syntax checks do not verify deliverability or ownership. CC/BCC, SMTP
  headers and sending options are intentionally not part of this form.
  Templates are saved as plain text only: no HTML rendering, interpolation,
  mailto link, outgoing email or automatic ticket creation.
- Submit validates the form first, then opens an accessible modal. Without
  Portal it asks "Do you want to attach SOP?" and SOP remains optional.
  With Portal it says "Portal SOP is mandatory" and offers Yes/Cancel only.
  Native dialog provides keyboard containment;
  Cancel or Escape closes without sending a save and restores Submit focus.
- Yes reveals a file picker and an explicit "Attach SOP and save" button.
  A valid file is mandatory for this path. Picking a file alone never saves.
- No is available ONLY without Portal; it saves without a NEW SOP and keeps
  all previously saved generic and Portal SOPs unchanged.
- During a request, repeated clicks and cancellation are disabled. After an
  error, the dialog stays open for retry; inputs/file are retained. Cancelling
  is not an undo after a request has already been sent (or timed out).

SOP association is explicit: a submission selecting Portal attaches the file
to Portal, including in mixed-method saves. This becomes the current Portal
SOP, not the generic vendor-wide SOP. Without Portal, an upload becomes the
current optional vendor-wide SOP and never changes a saved Portal SOP.
All earlier revisions remain stored. A legacy generic SOP is NOT silently
promoted to Portal. The directory shows "Download current Portal SOP" within
Portal, and a separate vendor-wide download when available. Links download
only; documents are not rendered inline.
Phone shows its three labelled values; Portal shows What to do and How to do
as safe multiline text; Email continues to show its labelled template details.
Prior Phone, Portal and Email instructions stay in storage and appear as
unnumbered "Prior [method] notes (read-only)" for reference. They are never
required step inputs. Legacy missing Phone/Email/Portal details or Portal SOP are
explicitly marked as not yet recorded; no values or attachments are invented.
Only Other/custom methods show ordered steps or a legacy missing-steps message.
Filter and Refresh still work.
This records vendor configuration, not actual tickets. No vendor portal,
mail, telephone or ticket-system integration is performed.

UPDATE / RETRY SEMANTICS
Names use Unicode NFKC normalization, collapsed whitespace and case-insensitive
keys. Controls/invisible formatting are rejected. The first saved vendor and
method spelling is retained. A custom Other name cannot duplicate another
method selected in the same submission. Naming Other "Email", "Phone" or
"Portal" (including NFKC/case-insensitive aliases) is rejected even if that
canonical checkbox is not selected: use the proper checkbox and its required
details or SOP instead. Existing associations are reused.
Saving Other replaces its ENTIRE ordered step list. Saving Email replaces its
WHOLE structured details object; omitted optional values become empty strings.
Saving Portal replaces both Portal detail fields atomically with its new SOP.
Saving Phone replaces its three form values; blank or omitted contact person
name clears only that contact field. Phone number and account ID remain required.
For backward-compatible direct API clients, explicit extension/notes values
still update; omitted values keep
previously stored values (empty strings for a new Phone record).
Canonical Phone, Portal and Email saves never delete/rewrite legacy instruction
rows. Unselected methods, details and instructions remain unchanged, including
saved Portal details on a non-Portal save. Unchecking is not deletion.
Omit phone_details/email_details/portal_details when
the respective method is not selected (even null is rejected). Concurrent
different submissions follow last-committed-write semantics for overlapping
methods. The form snapshots all selected details before the SOP modal; later
background field/toggle changes cannot alter the pending save or exact retry.
Every submission has a random request_id. Exact retries (including attachment)
are transactionally deduplicated, even across server restart, so a delayed
retry cannot revert a later save or create another SOP revision. Reusing an
ID with different data is rejected. The browser keeps the ID in memory for
retries of the same content/file/choice after an error, until success. After
page reload or changing content, a new submission gets a new ID; a deliberate
new upload can create another revision. There is no localStorage containing
SOP content or form drafts. Drafts are not retained across a browser reload.

PERSISTENCE / ADDITIVE MIGRATION
Default: <project-root>/data/vendor_management.db, derived from server location
rather than the current directory. Optional dedicated alternate location:
  python frontend/vendor_management_server.py --database data/vendor_management_local.db
Never point this at the application's data/itom.db or another app database.
Startup preserves vm_vendors and vm_vendor_methods, adding only these tables
and an index if missing:
  vm_method_steps — (vendor, method, position) and instruction text
  vm_email_details — address, subject, opening and body, with a composite
                     foreign key to the vendor's canonical Email method
  vm_phone_details — number, contact_name, account_id, extension and notes,
                     with a composite foreign key to canonical Phone
  vm_portal_details — what_to_do and how_to_do, with a composite foreign key
                      to the vendor's canonical Portal method (new this revision)
  vm_portal_sops — retained SOP-ID associations, referencing vm_sops and
                   the vendor's canonical Portal method; current is newest
  vm_sops — opaque random ID, vendor, filename, MIME type, size, SHA-256,
             creation time, complete file BLOB
  vm_submissions — request_id and payload digest for durable idempotency
Old vendor/method records, steps, SOPs and submission receipts survive
unchanged. This revision adds only vm_portal_details; existing tables are not
altered. No fields or associations are fabricated: missing legacy Email/Phone/
Portal details and unassociated Portal SOP return null. Historical instructions
and uploaded SOP contents are never converted into What to do / How to do.
Repeated startup is safe. Vendor/method/Other-step/Email/Phone/Portal updates, SOP
metadata+bytes, Portal association and submission receipt commit together in
one SQLite transaction; failures roll
back all those writes. Read responses use a consistent database snapshot.
SQL is parameterized and foreign keys are enforced on every connection.
The existing main ITom data/itom.db is never opened by this feature.

RETENTION / BACKUPS
SOP bytes are stored in the companion SQLite database, never under a supplied
filename on disk. All SOP revisions and submission receipts are retained
indefinitely; there is no delete, purge or expiry UI. Only the latest SOP is
listed per category (Portal and generic), but known opaque IDs for retained older revisions can still download.
Do not manually remove submission receipts while clients may retry. Plan
storage capacity: each successful new SOP can add up to 10 MiB plus database
overhead. Back up the complete database while the server is stopped; it
contains vendors, instructions, all attachments and idempotency receipts.
Restore that database with the server stopped. Apply normal OS access
permissions/encryption/backups for potentially sensitive SOPs. Files/folders
need write permission. Source uploads do not include any personal database.

LOCAL SECURITY / DOCUMENT LIMITS
Local trusted single-user only. No authentication, authorization, TLS,
antivirus, audit trail, production multi-user support or IIS/SSO integration.
Do not expose this server through a proxy, tunnel or public network. Other
local processes/users can access its directory and attachments; opaque IDs
are not authorization. Treat downloaded documents as untrusted and scan them
with your own security tools before opening. Format checks do not establish
that arbitrary documents are safe or fully well-formed.
Allowed SOPs: nonempty PDF, non-macro DOCX and UTF-8 TXT, up to 10 MiB each.
The server, not only the picker, checks names, extension and file content.
- Filenames are normalized (max 150 chars), never used as paths; traversal,
  separators, control/format characters and unsafe name punctuation reject.
- TXT rejects binary/control data, markup, shebangs and executable signatures.
- PDF requires a PDF header, object/startxref markers and EOF trailer. Known
  action/JavaScript/embedded-file/encrypted content and object streams reject,
  including hex-escaped PDF name markers. This is a conservative format gate,
  not a full PDF parser or malware scanner.
- DOCX is inspected in memory without filesystem extraction. A standard Word
  document, content-type manifest and root relationship are required. Macros,
  executable/unknown entry types, embedded objects, ActiveX, dynamic fields,
  external relationships, DTD/entities and alternate XML encodings reject.
  Limits: 256 ZIP entries, 8 MiB per expanded entry, 32 MiB expanded total,
  200:1 maximum per-entry expansion ratio, stored/deflate compression only.
  Duplicate/unsafe paths, corrupt ZIPs, encrypted entries and invalid images
  reject. Expanded reads and CRC checks are bounded, not just declared sizes.
These deliberate restrictions can reject legitimate documents (e.g. some
compressed PDFs, Word page fields, external links or embedded objects). Use
a simple static PDF/DOCX or plain TXT; do not merely rename an unsafe file.

HTTP protections retained: exact Host and same-origin Origin on writes,
fetch-site checks, JSON-only, duplicate-header/JSON-field checks, no CORS,
10-second socket timeouts, safe DOM textContent and hash-based script/style
CSP. The October 13 CSP fix is retained: HTML CRLF and lone CR normalize to
LF BEFORE both hashing and serving; script/style hashes therefore match the
browser. No unsafe-inline permission was added. Requests are capped at 14 MiB including base64/JSON; SOPs at 10 MiB.
The combined request bound applies even if individual field limits pass.
Only /, /vendor_management.html, /api/vendors and /api/sops/<32-hex-id> are
served. Downloads force Content-Disposition: attachment, a safe UTF-8 filename,
Cache-Control: no-store and X-Content-Type-Options: nosniff. No arbitrary
filesystem endpoint or inline preview is provided.

API (same origin; direct clients must supply correct Host and Origin)
POST /api/vendors, Content-Type: application/json; UTF-8 body:
  {"vendor":"Acme","methods":["Phone","Other"],
   "custom_method":"Partner desk",
   "steps":{"Other":["Open the partner help desk"]},
   "phone_details":{"number":"+44 (0)20 1234-5678",
                    "contact_name":"Support team","account_id":"000123"},
   "request_id":"0123456789abcdef0123456789abcdef","sop":null}
Use a freshly generated lowercase 32-hex ID for every new submission; reuse
it with identical content, including phone fields/file bytes, when retrying.
Portal only (sop is REQUIRED, a fresh upload every submission):
  {"vendor":"Acme","methods":["Portal"],"steps":{},
   "portal_details":{"what_to_do":"Open a support case",
                     "how_to_do":"Sign in\nSelect New case"},
   "request_id":"<newly generated lowercase 32-hex ID>",
   "sop":{"name":"portal-guide.txt","data":"<base64 file bytes>"}}
The same sop object is optional for requests without Portal. Including Portal
always associates the new SOP with Portal. No client-supplied attachment IDs,
reuse flags or current generic SOP can substitute for the upload.
Email retains its structured contract and NO steps:
  {"vendor":"Acme","methods":["Email"],"steps":{},
   "email_details":{"address":"support@vendor.example","subject":"Case [number]",
                    "opening":"Hello support,\n","body":"Issue:\n\tDescribe the problem"},
   "request_id":"<newly generated lowercase 32-hex ID>","sop":null}
The steps object is always REQUIRED: only the "Other" key when Other is
selected, otherwise {}. Phone/Portal/Email step keys (even empty arrays),
unselected keys and absent steps reject. Mixed Phone+Email+Portal sends {},
required phone_details/email_details/portal_details and a valid sop. Add Other and include
its custom_method plus steps.Other. Built-in aliases in Other reject.
phone_details requires number/account_id, both strings; optional contact_name
must be a string when provided and defaults to empty when omitted or blank.
Optional extension/notes are accepted for legacy API clients, preserve stored values
when omitted, and default to empty only for new records. New browser requests
send neither key. email_details requires address/subject; optional opening/body
default to empty. portal_details requires exactly what_to_do/how_to_do, both
nonblank strings up to 2,000 characters each. Unknown nested fields reject. Omit
the entire object when its method is unselected, including null.
GET /api/vendors returns name, methods (labels), steps (label to instruction
array, including retained canonical legacy notes), email_details (four-field
object or null), phone_details (five-field object or null, retaining legacy
extension/notes), portal_details (what_to_do/how_to_do object or null), sop (current generic
vendor-wide metadata or null), and portal_sop (current Portal-associated
metadata or null). Metadata has no bytes. New canonical methods have empty
instruction arrays; Other/custom methods have ordered instructions.
GET /api/sops/<32-hex-id> downloads retained bytes, including older revisions.
200 success; 400 validation, 403 Host/Origin, 404 unknown path/ID, 408 timeout,
413 request size, 415 request content type, 503 storage unavailable. Retrying
an identical current-contract request with the same ID is safe. Old clients
sending canonical method steps, lacking steps/request_id, missing required
structured details or Portal upload are rejected. Update/restart server and
refresh HTML together. Historical submission fingerprints remain unchanged;
old-contract requests cannot be retried through this new API. Do not reuse
old IDs for changed content.

VALIDATION (from the project root; no production database is accessed)
  python -B frontend/vendor_management_test.py
71 unittest cases passed at delivery, including the optional Node.js mocked
DOM interaction case with 386 assertions (zero skips). The original 65 tests /
334 DOM assertions passed before editing. Their relevant coverage is retained
and adapted to Portal fields and the three-field Phone form. Six added cases
cover Portal schema, both required multiline field bounds/controls, additive
migration without fabricated details, restart/retry/non-Portal preservation,
atomic rollback with SOP/receipt, and legacy Phone extension/notes retention.
It covers all 15 nonempty method combinations; Portal mandatory-SOP server
and browser bypass rejection; exact and stale retries across restart; Phone
schema, normalization, field bounds and invalid controls; unselected fields;
Other-only steps; alias rejection; generic-versus-Portal SOP association;
legacy data/notes/blob/receipt preservation; actual restart persistence;
rollback before Portal association and receipt commits; concurrent retries;
and safe labelled text rendering with immutable pending form snapshots.
Existing HTTP/local-host/origin, document-content restrictions, malicious ZIP,
10 MiB boundary, Email/no-Email-steps, free-text vendor, Other ordering and
CSP hashing regressions remain covered. LF, CRLF and lone-CR serving/hash
checks run in the suite.
Tests use unique disposable SQLite files beside the test file and ephemeral
loopback ports, cleaning up afterward. They never open production/default
SQLite databases. If Node.js is absent the mocked DOM case is reported
skipped; no runtime dependency is added. Mocked DOM checks also cover
conditional disabled/required fields, draft preservation, Add/remove/numbering
for Other, optional No, mandatory Yes/file, Cancel/Escape, retries and repeated
click guards, legacy read-only notes and Clear.
No packages were installed.
HTML validator passed with zero errors/warnings and no external assets.
HTML contract checks passed: unique IDs, expected inputs, no inline event
handlers, textContent rendering and accessible dialog hooks. Embedded
JavaScript executes in the mocked DOM checks. No real-browser visual/accessibility or
end-to-end browser run was performed in the delivery environment. Native
focus trapping must still be exercised in your target browser. These tests
are not a malware scan and make no antivirus assurance.

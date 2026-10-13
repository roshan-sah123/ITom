ITom Vendor Management — isolated local companion

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
2. Back up data/vendor_management.db with the companion stopped.
3. Replace the four feature files in frontend with these updated versions.
4. Run:
     python frontend/vendor_management_server.py
5. Open or hard-refresh:
     http://127.0.0.1:8081/vendor_management.html
Keep that process running. Uploading source alone does not restart your local
service. The running server reads HTML once at startup; refreshing the browser
without restarting it will still show the old page. Select Email and look for
the marker "Email uses the details below; no numbered steps are required." In PowerShell, confirm the local file:
  Select-String -Path frontend/vendor_management.html -SimpleMatch 'Email uses the details below; no numbered steps are required.'
Then check what the running server serves:
  (Invoke-WebRequest http://127.0.0.1:8081/vendor_management.html).Content | Select-String -SimpleMatch 'Email uses the details below; no numbered steps are required.'
If only the file has the marker, restart the known companion process. Existing ITom ports 8080/8000, IIS and SSO stay unchanged. Do not open
via file:// or port 8080: HTML and API must share this companion's origin.
The service stays bound to 127.0.0.1:8081. If the port is occupied, stop only
the known companion process before restarting; do not stop unrelated services.

FORM WORKFLOW
- Type any vendor name (1–100 normalized characters). There is no vendor
  dropdown, predefined vendor list, or vendor type field.
- Check one or more of Phone, Email, Portal and Other. Other requires a custom
  method name (1–80 characters) and has its own independent steps.
- Each selected non-Email method reveals an ordered list: Step 1, Step 2,
  Step 3, etc. Email has no Step 1, Add step, Remove or numbered-step inputs.
  Add/remove steps; remaining numbers update automatically. Keep 1–30 steps,
  each nonblank and at most 2,000 normalized characters. A single-line step
  input is used. The last step cannot be removed. Toggling methods off/on
  preserves their unsaved drafts, including the Other name. Only checked
  methods and non-Email steps are sent. Clear resets unsaved fields/steps only.
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
- Submit validates the form first, then opens an accessible modal asking
  "Do you want to attach SOP?" Native dialog provides keyboard containment;
  Cancel or Escape closes without sending a save and restores Submit focus.
- Yes reveals a file picker and an explicit "Attach SOP and save" button.
  A valid file is mandatory for this path. Picking a file alone never saves.
- No submits immediately without a NEW SOP. An already saved SOP is retained.
- During a request, repeated clicks and cancellation are disabled. After an
  error, the dialog stays open for retry; inputs/file are retained. Cancelling
  is not an undo after a request has already been sent (or timed out).

There is ONE current vendor-wide SOP, shared across all of that vendor's
methods, not a separate SOP per method. A new upload becomes the current
revision; earlier revisions remain stored. Choosing No never removes or
replaces the current SOP. The directory offers only download links, not
inline document rendering, and shows saved ordered steps under non-Email methods.
Expand Email in the directory to see the labelled address, subject, greeting
and body. Multiline whitespace is preserved. Existing Email instructions stay
in storage and appear only as unnumbered "Prior Email notes (read-only)",
clearly marked as reference material, with no step entry required. Email never
shows a missing-steps message. Legacy Email records still show "email details
not yet recorded" when appropriate, not invented values. Filter and Refresh
still work. Legacy non-Email methods with no steps are explicitly marked
"Legacy method — steps not yet recorded"; type the vendor name and select
that method to record its instructions.
This records vendor configuration, not actual tickets. No vendor portal,
mail, telephone or ticket-system integration is performed.

UPDATE / RETRY SEMANTICS
Names use Unicode NFKC normalization, collapsed whitespace and case-insensitive
keys. Controls/invisible formatting are rejected. The first saved vendor and
method spelling is retained. A custom Other name cannot duplicate another
method selected in the same submission. Naming Other "Email" (including
normalized/case-insensitive aliases) is rejected: select the Email checkbox
and supply its details instead. Existing associations are reused.
Saving a selected non-Email method replaces its ENTIRE ordered step list;
methods not selected remain unchanged. Saving Email replaces its WHOLE
email_details object: omitted optional greeting/body become empty. It never
deletes or rewrites previously stored Email steps, including in mixed saves. Saving only non-Email
methods preserves previously stored Email fields and steps; email_details
must be omitted from non-Email requests. Unchecking is not deletion. Concurrent different
submissions follow last-committed-write semantics for overlapping methods.
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
  vm_sops — opaque random ID, vendor, filename, MIME type, size, SHA-256,
             creation time, complete file BLOB
  vm_submissions — request_id and payload digest for durable idempotency
Old vendor/method records, steps, SOPs and submission receipts survive
unchanged. No email fields are fabricated: legacy Email details return null.
Repeated startup is safe. Vendor/method/step/email updates, SOP metadata+bytes and
submission receipt commit together in one SQLite transaction; failures roll
back all those writes. Read responses use a consistent database snapshot.
SQL is parameterized and foreign keys are enforced on every connection.
The existing main ITom data/itom.db is never opened by this feature.

RETENTION / BACKUPS
SOP bytes are stored in the companion SQLite database, never under a supplied
filename on disk. All SOP revisions and submission receipts are retained
indefinitely; there is no delete, purge or expiry UI. Only the latest SOP is
listed, but known opaque IDs for retained older revisions can still download.
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
CSP. Requests are capped at 14 MiB including base64/JSON; SOPs at 10 MiB.
The combined request bound applies even if individual field limits pass.
Only /, /vendor_management.html, /api/vendors and /api/sops/<32-hex-id> are
served. Downloads force Content-Disposition: attachment, a safe UTF-8 filename,
Cache-Control: no-store and X-Content-Type-Options: nosniff. No arbitrary
filesystem endpoint or inline preview is provided.

API (same origin; direct clients must supply correct Host and Origin)
POST /api/vendors, Content-Type: application/json; UTF-8 body:
  {"vendor":"Acme","methods":["Phone","Other"],
   "custom_method":"Partner desk",
   "steps":{"Phone":["Call support","Record reference"],
            "Other":["Open the partner help desk"]},
   "request_id":"0123456789abcdef0123456789abcdef","sop":null}
Use a newly generated lowercase 32-hex ID for each new submission; reuse it
with identical content when retrying. Optional SOP instead of null:
  {"name":"instructions.txt","data":"<base64 file bytes>"}
For an Email submission, include email_details, for example:
  {"vendor":"Acme","methods":["Email"],
   "steps":{},
   "email_details":{"address":"support@vendor.example","subject":"Case [number]",
                    "opening":"Hello support,\n","body":"Issue:\n\tDescribe the problem"},
   "request_id":"<newly generated lowercase 32-hex ID>","sop":null}
The steps object is always required and contains exactly the selected non-Email
method keys. For Email only, send "steps":{}. For Email + Phone, send e.g.
"steps":{"Phone":["Call support"]} alongside email_details. Email step keys
(even an empty list), unselected keys, or an absent steps object are rejected.
email_details requires address and subject; opening/body default to empty.
Unknown nested fields reject, including headers/cc/bcc/send. Omit the entire
email_details field when Email is not selected (even null is rejected).
GET /api/vendors returns vendors with name, methods (labels), steps (label to
ordered instruction array, including preserved legacy Email notes or an empty
Email array for new records), email_details (the complete four-field object,
or null if not recorded) and current sop (null or metadata without bytes).
GET /api/sops/<id> downloads retained attachment bytes by generated opaque ID.
200 success; 400 validation, 403 Host/Origin, 404 unknown path/ID, 408 timeout,
413 request size, 415 request content type, 503 storage unavailable. Retrying
an identical current-contract request with the same ID is safe. Old clients
sending Email steps, lacking steps/request_id, or selecting Email without its
required details are rejected; update/restart the server and refresh the HTML
together. Stored historical submission fingerprints remain untouched; requests
using the old Email-steps contract cannot be retried through this new API.
Do not reuse their request IDs for changed content.

VALIDATION (from the project root; no production database is accessed)
  python -B frontend/vendor_management_test.py
48 unittest cases passed at delivery, including one optional Node.js mocked
DOM interaction case with 108 assertions (zero skips). The suite checks HTTP/security
headers, additive legacy migration, step ordering/replacement, unselected
method retention, SOP byte/metadata atomic rollback, actual server restart,
concurrent idempotent retry, safe downloads, format spoofing, malicious ZIPs,
path traversal, XSS-like text, valid format fixtures and the 10 MiB boundary.
Email tests add required-field/schema validation, recipient/subject injection
rejection, limits and multiline text, normalized Other alias rejection,
whole-object replacement, unselected preservation, transactional rollback,
legacy migration, GET/restart persistence and idempotent email retries.
The no-Email-steps regression tests verify the explicit empty-object contract,
rejection of extraneous Email steps, mixed Email/Phone requirements, retention
of old Email notes/SOP bytes/submission fingerprints across new details saves
and restart, plus Email-only SOP upload/retry persistence.
Tests use unique disposable SQLite files beside the test file and an ephemeral
loopback port, cleaning up afterward. They never open the default database.
If Node.js is absent the mocked DOM case is reported skipped; the Python
runtime still needs no extra dependency. Mocked DOM tests cover validation
before the modal, independent drafts, adding/removing/numbering, Other, No,
Yes with mandatory file, Cancel/Escape, errors/retry and repeated-click guard.
Email DOM assertions also cover conditional required/disabled fields, draft
retention, immutable pending snapshots, safe labelled multiline rendering,
legacy missing-details messages and Clear. They also assert that Email step
containers, inputs and buttons never exist, startup/toggle/reset never query
missing Email controls, mixed payloads contain only non-Email steps, and legacy
Email notes are read-only and unnumbered with no missing-steps warning.
No packages were installed.
HTML validation passed with zero errors/warnings and no external assets;
JavaScript syntax checks passed. No real-browser visual/accessibility or
end-to-end browser run was performed in the delivery environment. Native
focus trapping must still be exercised in your target browser. These tests
are not a malware scan and make no antivirus assurance.

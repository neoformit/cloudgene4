# QA findings

Exploratory QA sessions (`plans/E2E_TEST_PLAN.md` §4.2). One section per charter; never rewrite
another agent's section. Each confirmed finding has a red test in `e2e/tests/test_findings_*.py`.

## T07b — security & access control

Charter: security and access control (IDOR/object permissions, privilege escalation, CSRF,
path traversal, XSS/injection, secrets, auth lifecycle, light DoS) against the scripted suite's
blind spots. Stack: `rebuild` @ 83cd54f, E2E stack (`e2e/exploratory/serve.py`), seeded users
admin/alice/bob. Probe scripts: `e2e/exploratory/` (`matrix.py`, `probes_api.py`,
`probes_auth.py`, `probes_djangoadmin*.py`, `probes_injection.py`, `probes_xss.py`,
`probes_misc.py`, `probes_inline_html.py`). Red tests: `e2e/tests/test_findings_security.py`.

### B-01 — `/django-admin/` login bypasses the account lockout and yields a full API session (High)

**Severity:** High — the entire brute-force protection promised by SPEC §3.4
(`security.max_login_attempts` / `security.lockout_duration`, 429 `account_locked`) is
bypassable, and the accounts it protects best (admins) are exactly the ones reachable there.

**Minimal repro** (probe: `e2e/exploratory/probes_djangoadmin.py`):
1. Make an account an admin (`PATCH /api/admin/users/{id} {"is_admin": true}` — this sets
   `is_staff=True`, which is what the Django admin site requires).
2. Lock it out through the documented endpoint: 6 × `POST /api/auth/login` with a wrong password
   → `429 account_locked`, and a 7th attempt *with the correct password* is still 429.
3. `POST /django-admin/login/` with the **correct** password (plus the form's
   `csrfmiddlewaretoken`) → `302 /django-admin/`.
4. Send the resulting `sessionid` cookie to the API: `GET /api/auth/me` →
   `{"authenticated": true, "user": {...}}`, `GET /api/admin/dashboard` → `200`.

**Expected:** while the account is locked no login path may succeed, and wrong passwords at any
login surface must count towards `login_attempts`.
**Actual:** `/django-admin/login/` uses Django's own `AuthenticationForm`; it never touches
`User.login_attempts` / `locked_until`, is not rate-limited at all, and the session it creates is
the same `django.contrib.sessions` session the SPA API trusts. 8 wrong passwords there left the
account unlocked (`POST /api/auth/login` afterwards → 200).

**Evidence:**
```
API login while locked: 429 {"error":{"message":"Too many failed logins. ...","code":"account_locked"}}
django-admin login while locked -> 302 /django-admin/
/api/auth/me with that cookie: True dja5cd660
/api/admin/dashboard with that cookie: 200
```

**Suspected cause:** `cloudgene_django/urls.py` routes `path('django-admin/', admin.site.urls)`
and `django.contrib.admin` is in `INSTALLED_APPS` (`cloudgene_django/settings.py`), while the
lockout is implemented only in `accounts.views.LoginView`. SPEC §3.6 does not list the Django
admin as part of the product at all.
**Fix direction:** drop `django.contrib.admin` / the `django-admin/` route from the deployed
URLconf (or gate it behind an env flag that defaults to off); if it is kept, move the lockout into
an authentication backend / signal (`user_login_failed`) so every login surface counts.

### B-02 — a password change or password reset does not revoke the API token (Medium)

**Severity:** Medium — the account-recovery flow does not evict an attacker. Sessions *are*
invalidated (Django's session-auth hash), so the token is the one credential that survives.

**Minimal repro** (probe: `e2e/exploratory/probes_auth.py`):
1. As alice: `POST /api/me/token` → key `K`.
2. Change the password: `PATCH /api/me {"password", "password_confirm", "current_password"}`
   (or run the whole `POST /api/auth/password-reset` → `/api/auth/password-reset/{token}` flow).
3. `GET /api/me` with `Authorization: Token K` → **200**.

**Expected:** SPEC §3.4 makes the reset link single-use and treats a reset as account recovery;
a credential created before the reset must not keep working.
**Actual:** the DRF token row is untouched by both flows (`session: password change kills the
other session` passes, `token: password change revokes the API token` fails; same for reset).

**Evidence:** `token: password change revokes the API token  GET /api/me with the old token -> 200`
and `reset: password reset revokes the API token  GET /api/me with the pre-reset token -> 200`.

**Suspected cause:** `accounts/views.py` — `ProfileView.patch` / `PasswordResetConfirmView.post`
call `user.set_password()` + `save()` and never touch `rest_framework.authtoken.models.Token`.
**Fix direction:** `Token.objects.filter(user=user).delete()` in both paths (and mention it in the
UI), or hash-bind the token to the password like the session auth hash.

### B-03 — every user's API token key is readable in cleartext via `/django-admin/` (Medium)

**Severity:** Medium — contradicts SPEC §3.4/§3.6 ("the key is only ever returned here, once";
`GET /api/me` deliberately exposes only `api_token.created`). Any superuser — or anyone who gets
a superuser session, e.g. through B-01 — can copy a user's token and act as that user, invisibly.

**Minimal repro** (probe: `e2e/exploratory/probes_djangoadmin2.py`):
1. alice: `POST /api/me/token` → key `K`.
2. Log in at `/django-admin/login/` as the seeded superuser (`manage.py create_admin`).
3. `GET /django-admin/authtoken/tokenproxy/` → the changelist prints `K` in full.

**Expected:** no interface returns an existing token key.
**Actual:** `alice's token key readable in the Django admin: True`
(`sample: ['75d953336059c5c0797d0fba551ef2df325a6919', ...]`).

**Suspected cause:** `rest_framework.authtoken` registers its own `ModelAdmin`, which is
reachable because `django.contrib.admin` is installed and routed (same root cause as B-01).
DRF stores token keys in plaintext, so removing the admin surface is the practical fix.

### B-04 — job outputs are served with a sniffed content type; `?inline=1` renders user-controlled output as HTML on the app origin (Medium)

**Severity:** Medium — stored XSS in the application origin. The victim is whoever opens the
inline link, including an **admin** (admins may download any user's outputs), and `csrftoken` is
deliberately not `HttpOnly`, so the payload can drive authenticated state-changing API calls.

**Minimal repro** (probe: `e2e/exploratory/probes_inline_html.py`, red test uses a pre-seeded
output file so it needs no worker):
1. Any workflow whose output folder contains an `.html` file built from a user input (the probe
   installs a 12-line fixture app; real Cloudgene pipelines publish HTML reports).
2. alice submits it with `message = <script>document.title="XSS-T07B"</script>`.
3. `GET /api/jobs/{id}/outputs/{file_id}/?inline=1` →
   `200, Content-Type: text/html, Content-Disposition: inline; filename="report.html"`, payload
   present — as alice **and** as admin.

**Expected:** a download endpoint must not turn job artefacts into active content on the app's
own origin.
**Actual:** `FileResponse(open(path,'rb'), as_attachment=not inline, filename=output.name)` lets
Django guess the type from the file name; `X-Content-Type-Options: nosniff` does not help because
the declared type already *is* `text/html`.

**Suspected cause:** `jobs/views.py:JobViewSet.output_download`.
**Fix direction:** force `content_type='application/octet-stream'` (or an allowlist:
text/plain, application/json, image/*) unless the file type is known-safe, keep
`Content-Disposition: attachment` for everything else, and/or serve downloads from a separate
origin plus a `Content-Security-Policy: sandbox` header.

### B-05 — a text/string/textarea input accepts a file upload and uses its raw file name as the value (Low)

**Severity:** Low — input-validation inconsistency, no traversal or shell exposure (K3 holds),
but a required text input can be satisfied without any text and the value that reaches
`params.json` is an unsanitised client-supplied file name.

**Minimal repro:**
```
POST /api/jobs  (multipart)  workflow=hello  + file part named "message"
                              (filename "sneaky-name.txt")
→ 201, inputs: [{"id":"message","type":"text","value":"sneaky-name.txt","files":[]}]
→ the pipeline receives params.message = "sneaky-name.txt" and writes it to hello.txt
```
**Expected:** 400 `invalid` with `fields.message` — a file is not a value for a text input, and
`required` is not satisfied.
**Actual:** DRF merges `request.FILES` into `request.data`, so
`jobs/submission.py:_get(data, pid)` returns the `UploadedFile`; `str(raw)` is its `.name`.

**Suspected cause:** `jobs/submission.py:validate_inputs` (the non-file branch does not reject
file-like values). **Fix direction:** in `_get`, ignore values that are `UploadedFile`s for
non-file params (or read from `request.POST` for value inputs).

### Informational / accepted-by-design (no test)

- **I-1 Lockout is a login-time control only.** A locked account's *existing* session and its API
  token keep working (`GET /api/me` → 200). Consistent with SPEC §3.4 wording, but worth a
  decision: a lockout usually implies the account is frozen.
- **I-2 No `Content-Security-Policy`** on the SPA (`X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` are present). A CSP would
  contain B-04 and the intentional `v-html` surfaces.
- **I-3 Intentional HTML rendering (trust boundary).** `v-html` is used for admin-authored page
  HTML (`home`, `footer`, `/pages/{slug}`), the footer, and for `workflow.description` /
  input `label`s from `cloudgene.yaml`. Both are admin-controlled (installing a workflow already
  means arbitrary Nextflow execution), so this is by design — but it means *workflow YAML is
  privileged input*: anything a pipeline author writes is executed in every visitor's browser.
  Verified escaped everywhere user-controlled data appears: job names, `::message::` text from a
  pipeline's stdout, user full names/e-mails in the admin lists (`e2e/exploratory/probes_xss.py`,
  6/6 checks; `ConfirmDialog` messages pass job names through a local `escapeHtml`).
- **I-4 No body-size limit for JSON endpoints.** `DATA_UPLOAD_MAX_MEMORY_SIZE = 10 MB` only
  applies to form parsing; an 11 MB JSON body to `POST /api/auth/register` is parsed fully
  (400 after 2.7 s). Multipart uploads are streamed and bounded by `server.max_upload_mb`.
- **I-5 Public surface beyond SPEC §3.6.** `/api/schema/` and `/api/schema/swagger-ui/` are
  anonymous (full API surface disclosure) and `/api/categories/` is public and undocumented.
- **I-6 Admin = arbitrary code execution, by design.** `POST /api/admin/workflows/install`
  accepts any path containing a `cloudgene.yaml` (`/etc` → 400 "No cloudgene.yaml found"), the
  installed app's `nextflow.config`/`nextflow.env` are admin-editable, and `nextflow.work_dir`
  may be any path. Nothing to fix; the trust boundary is "admin == root-equivalent".
- **I-7 Registration reveals whether a username / e-mail exists** (`This username is already
  taken.`), while login and password-reset do not (verified identical bodies / messages). This is
  the documented behaviour (`accounts/serializers.py` MSG_USERNAME_TAKEN, SPEC §3.4 K1) — flagged
  only so the choice is explicit. Login timing was measured (unknown 0.090 s vs existing 0.115 s
  with the E2E fast hasher; the unknown-user path does a dummy `set_password`, so the real
  deployment is equalised).

### Probed and found clean

- **Endpoint × role matrix** over every path/method in `schema.yaml` (66 operations ×
  anon/bob/alice/admin): anonymous → 401 on every protected endpoint (never 403), non-admin →
  403 on all 30 `/api/admin/*` operations, non-owner → 404 (never 403) on
  `/api/jobs/{id}[/status|/log|/outputs/{file_id}|/cancel]` and `DELETE /api/jobs/{id}`.
  Full matrix: `e2e/exploratory/matrix.py`, regression test `test_permission_matrix`.
- **IDOR:** alice's output id under bob's own job → 404; unknown/malformed job UUIDs → 404;
  `?user=` on `GET /api/jobs` is ignored; token auth is scoped exactly like the session.
- **Privilege escalation:** `PATCH /api/me` with `is_staff`/`is_superuser`/`is_active`/`is_admin`/
  `groups`/`username`/nested `user{}` → all ignored; `POST /api/auth/register` with the same keys
  → inactive, no groups; `PATCH /api/admin/users/{id} {"groups":["admin"]}` does not grant admin
  (managed only via `is_admin`); self-deactivation / self-demotion / self-delete-as-last-admin
  refused.
- **CSRF:** missing header, wrong header, and a cross-origin `Origin` are all 403 `csrf_failed` —
  including on `POST /api/auth/login` (login CSRF) and `POST /api/auth/logout`; token auth is
  correctly exempt; `sessionid` is `HttpOnly; SameSite=Lax`.
- **Sessions:** the session id rotates on login (no fixation), logout kills the old cookie,
  a password change kills the *other* sessions, deactivating or deleting a user kills both the
  session and the token.
- **Auth lifecycle:** password-reset tokens are single-use (2nd use → 400) and the request answer
  is identical for unknown e-mails; a reused activation key does not re-activate an
  admin-deactivated account; lockout counts case-varied usernames against the same account.
- **Path traversal:** `/api/pages/{slug}` with `..%2f`, `%2e%2e%2f`, `....//`, `%00`, absolute
  paths, upper case and `.html` suffixes → 404 (slug regex `^[a-z0-9][a-z0-9_-]{0,63}$` in
  `core/config.py`); `PUT /api/admin/pages/../../config/secret_key` → 404; output downloads
  re-validate the stored relative path (`jobs/outputs.py:safe_relative` + `_within`).
- **Injection (K3):** a job named ``$(touch …) `id` ; rm -rf / & | ../../etc/passwd %s ${HOME}``
  runs fine, is stored verbatim, never appears in a path (`jobs/<uuid>/`), is not in
  `params.json`, and creates no side effects; control characters are stripped; text inputs with
  quotes/`;`/traversal reach the pipeline as literal text (`nextflow` is spawned with an argv
  list, never a shell). SQL-ish payloads in `search`/`user`/`category`/`state` filters → 200/400,
  never 500.
- **Secrets:** `GET /api/admin/settings/mail` never returns `password` (only `password_set`), the
  value does not appear in `/api/admin/logs`; no password or token key is logged; `GET /api/me`
  exposes no hash/activation fields; non-admin payloads contain no other users' e-mail addresses;
  `config/secret_key` is not reachable through any endpoint; DEBUG is off (no traceback in any
  4xx/5xx body probed, unknown `/api/...` → JSON 404 envelope).
- **Limits:** `page_size` capped at 200 on `/api/jobs` and `/api/admin/logs`; over-long job names
  (>255) and text inputs (>100 000) rejected; deeply nested (200 levels) JSON handled without a
  500; invalid `page`/`page_size`/`state` handled with the error envelope.

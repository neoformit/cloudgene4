# Spec Constitution

These rules bind every file under `spec/`. A spec file that breaks a rule here is wrong, whatever
the code currently does. Only the spec maintainer (the orchestrating agent) edits this file;
sub-agents propose changes (see Article 10).

## Article 1 — Purpose and authority

1.1 `spec/` is the normative description of Cloudgene (Django + DRF backend, Vue 3 SPA, and its
production deployment). When code and spec disagree, the disagreement is a defect in one of them
and MUST be recorded (Article 6), never silently resolved.

1.2 The spec describes **behaviour and interfaces**, not implementation trivia. It names source
files so a reader can find the code, but a requirement MUST still make sense if the code inside a
module is rewritten.

1.3 User-facing documentation in `docs/` sits above the spec and is out of scope: the spec does not
restate or specify it. If the spec contradicts `docs/`, flag it as an open question.
`plans/` (SPEC.md, TASKS.md, QA_FINDINGS.md, …) is historical input only; `spec/` supersedes it.

## Article 2 — Structure

2.1 The spec has three sections: `spec/backend/`, `spec/frontend/`, `spec/deployment/`. Each
section has a `README.md` index, an `api-contract.md` and a `tests.md`.

2.2 Each spec file covers one cohesive area and is sized so that **one sub-agent can action it
alone** (implement, fix or verify it) with no other spec file open beyond this constitution, the
relevant `api-contract.md`, and the files it explicitly links.

2.3 Each fact has exactly one home. Other files link to it (`[ref](../backend/jobs-api.md#…)`)
rather than restating it.

## Article 3 — Spec file template

Every spec file (other than `README.md`) MUST contain these headings, in this order. A section
with nothing to say states "None."

```
# <Title>
## Purpose            — one paragraph: what this area does and why.
## Scope              — source files/directories covered; explicit out-of-scope items.
## Dependencies       — other spec files and contract operations this area relies on.
## Requirements       — numbered, testable requirements (Article 4).
## Interfaces         — data shapes, functions, commands, endpoints (by operationId), events.
## Behaviour          — flows, state machines, edge cases, error handling.
## Acceptance tests   — the tests that prove the requirements (Article 7).
## Known gaps         — where the code today diverges from the requirements (Article 6).
## Open questions     — unresolved decisions for the maintainer.
```

## Article 4 — Requirements

4.1 Requirements use RFC 2119 keywords (MUST, MUST NOT, SHOULD, MAY) and are individually
testable. A requirement without one of these keywords is invalid and MUST be rewritten. "Works correctly", "is fast" and similar are not requirements.

4.2 Every requirement has a stable ID: `<SECTION>-<AREA>-<NNN>`, e.g. `BE-JOB-004`, `FE-FORM-012`,
`DEP-NGINX-002`. SECTION is `BE`, `FE` or `DEP`; AREA is the code assigned to the file in its
section `README.md`. IDs are never reused or renumbered; retired requirements are marked
`(withdrawn)`.

4.3 A requirement states the observable outcome, including the failure outcome (status code, error
code, UI message, exit code) where one exists.

## Article 5 — API contract between frontend and backend

5.1 **The single source of truth for every HTTP interface between the frontend and the backend is
the OpenAPI document `schema.yaml`, generated from the backend's DRF serializers by drf-spectacular
and committed to the repository. Neither side may define an API shape anywhere else.** Concretely:

  a. Every `/api/` operation has an explicit serializer (request and response) and a stable
     `operationId`. The OpenAPI document routes themselves (`/api/schema/`,
     `/api/schema/swagger-ui/`) are exempt. Fields that cannot be typed statically (for example
     a default value whose type depends on the input type) are allowed only if listed as
     accepted untyped fields in `backend/api-contract.md`; any other untyped or free-form field is
     a defect. `backend/api-contract.md` lists every operation by `operationId`;
     `frontend/api-contract.md` lists, by the same `operationId`, the frontend API-module function
     that calls it, or states why the SPA does not call it. The two operation lists MUST match.
  b. An interface change happens in one change set, in this order: backend serializer/view →
     regenerate `schema.yaml` (`python manage.py spectacular --file schema.yaml --validate`) →
     frontend API module, fixtures and views → both `api-contract.md` files.
  c. CI fails when `schema.yaml` is stale against the code (backend staleness test).
  d. Backend contract tests validate real responses against the `schema.yaml` component for that
     operation, including the error envelope on error paths.
  e. Frontend contract tests and fixtures validate against the components **loaded from
     `schema.yaml`**, not hand-written JSON Schemas. A fixture that the schema rejects fails the
     build.
  f. Only frontend API modules (`frontend/src/api/*.js`) call the HTTP client; views and stores call
     API-module functions.

5.2 All errors use the one error envelope defined in `backend/api-contract.md`; the frontend reads
errors only through the helpers defined in `frontend/api-client.md`.

5.3 Paths, methods, field names, types, nullability, enums, pagination and status codes in either
`api-contract.md` MUST be quoted from `schema.yaml`, not paraphrased. Interim rule: until `schema.yaml` enumerates error
statuses per operation, `backend/api-contract.md` lists them from the code and marks them as
taken from code.

## Article 6 — Recording the current state

6.1 Specs are written from the code as it is, then corrected to what it should be. Where the code
fails a requirement, the file's **Known gaps** lists it: requirement ID, what the code does,
file/line reference, severity (`blocker`, `major`, `minor`). A gap that maps to no single
requirement uses `—` in the requirement column.

6.2 Do not invent features. A requirement that has no code yet is allowed only if it is marked
`(planned)` and a Known gap points at it.

## Article 7 — Tests

7.1 Every MUST requirement is covered by at least one named test (existing or planned) listed under
the file's **Acceptance tests**, with its layer: `unit` (Django/vitest), `contract`, `e2e`
(Playwright full stack), `smoke` (a script in `scripts/` that exits non-zero on failure) or
`config` (static checks of deploy and CI files).
A deployment requirement that binds the operator's host or procedure rather than the repository
(for example monitoring, host file modes, backup/restore order, cluster filesystem setup) may
instead cite `—` with the note "host obligation" and a manual verification step; `tests.md`
counts these separately as accepted untested items, not as gaps. A host-obligation row MUST state the
manual verification step and its expected result. A requirement on repository content (deploy
files, scripts, settings, code) MUST NOT be a host obligation. Planned tests are marked `(planned)` and MAY be named by their intended
`path::Class::method`; the name is a placeholder until the test exists, and `tests.md` lists it as
a gap. Acceptance tests tables have a Layer column and list one requirement ID per row (or an
explicit comma-separated ID list, never a range). Tests are cited by exact name:
`path::Class::method` for Python, `path › describe › it` with exact titles for vitest. `smoke` and `config` tests may be cited as a
script path plus step name (for example `scripts/smoke_gunicorn.sh` › "health"); a requirement on
an operator procedure (install or upgrade order) may be covered by a planned procedure-level smoke
script.

7.2 Each section's `tests.md` defines that section's test strategy, the commands that run it, and a
traceability table mapping every requirement ID to its tests. A requirement with no test is listed
there as a gap. Planned tests of one kind have one home per section (module, class or script),
named in that section's `tests.md`; spec files cite planned tests only under that home.

7.3 Behaviour that crosses frontend and backend (anything a user does in the browser that reaches
the API) MUST have at least one e2e test.

## Article 8 — Security and data invariants

8.1 Every requirement for an endpoint or view states who may use it (anonymous, authenticated
user, owner, admin) and what others receive.

8.2 User input that reaches the filesystem, a shell, a template or HTML output has a requirement
naming how it is constrained or escaped.

## Article 9 — Style

9.1 Plain, short sentences. Tables for inventories. Code blocks only for shapes, commands and
examples. No marketing language.

9.2 Reference code as `path/to/file.py` or `path/to/file.py:123`; link spec files relatively.

## Article 10 — Amending this constitution

10.1 Sub-agents MUST NOT edit this file. They put proposed amendments in their final report as:
`AMENDMENT: <article> — <proposed text> — <reason>`.

10.2 The maintainer applies amendments it agrees with and records them in the changelog below.
Amendments it is unsure of go under **Pending amendments** for later human review.

## Changelog

- 2026-10-21 — v1 adopted.
- 2026-10-21 — v1.1: 5.1a exempts the OpenAPI routes and allows a listed set of untyped fields;
  5.3 interim rule for error statuses taken from code; 6.1 `—` for gaps with no requirement;
  7.1 naming of planned tests. (Proposed by backend sub-agents.)
- 2026-10-21 — v1.2: 4.1 makes keyword-less requirements invalid.
- 2026-10-21 — v1.3: 7.1 fixes the Acceptance tests citation format. Files written before v1.3
  may use older formats until they are next edited.
- 2026-10-21 — v1.4: 7.1 adds the `smoke` and `config` test layers, host obligations, and script
  citations for smoke/config tests.
- 2026-10-22 — v1.5: 7.1 host obligations need a manual step and cannot cover repository
  content; 7.2 one home per kind of planned test.

## Pending amendments

For later human review. Not in force.

- **P1 — Per-operation error responses in `schema.yaml` (Article 5.3).** Require every operation
  to declare its error statuses (via `extend_schema(responses=...)`) and retire the 5.3 interim
  rule. Raised because `schema.yaml` today documents only `default: Error`, so status codes
  cannot be quoted from it. Unsure: it is a sizeable backend change and may belong in a task
  list rather than the constitution.
- **P2 — Shared non-HTTP contracts (Article 5).** Field validation rules are shared between
  backend and frontend through `accounts/validation_cases.json`, outside `schema.yaml`. Decide
  whether the constitution should name this as a second sanctioned contract mechanism (shared
  case files tested on both sides), or require those rules to move into `schema.yaml`
  (patterns, min/max lengths). Raised from the accounts spec.
- **P3 — Automated traceability check (Article 7.2).** Each `tests.md` traceability table is
  checked by a script in the unit suite (every requirement has a row; every test cited as
  existing exists). Unsure: it means adding tooling code to the repo, and the tables
  are currently built by a one-off parse. The check should also cover `spec/deployment/`,
  including resolving smoke-script step titles.
- **P4 — Component tests for view states (new Article 7.4).** Frontend views have component tests
  for loading, empty and error states; e2e alone does not satisfy requirements on states the full
  stack cannot produce deterministically. Raised because 0 of 21 views have component tests and
  about 60 MUST requirements depend on them. Unsure: it sets a testing investment level
  that the team should choose.

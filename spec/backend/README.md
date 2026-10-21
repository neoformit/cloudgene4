# Backend spec

Django + DRF backend: `cloudgene_django/`, `core/`, `accounts/`, `workflows/`, `jobs/`,
`admin_panel/`. All files follow [the constitution](../constitution.md).

| File | Area code | Covers |
|------|-----------|--------|
| [overview.md](overview.md) | ARCH | Apps, processes (web/worker), request flow, URL routing, settings module |
| [api-contract.md](api-contract.md) | API | Conventions (envelope, pagination, slashes, auth schemes) and the full operation catalogue from `schema.yaml` |
| [data-model.md](data-model.md) | DATA | All models, constraints, migrations |
| [configuration.md](configuration.md) | CONF | `core/config.py`, `settings.yaml` schema, read/write rules |
| [authentication.md](authentication.md) | AUTH | Session + CSRF, token auth, login/logout/me, auth backends, throttling |
| [accounts.md](accounts.md) | ACCT | Registration, activation, password reset, profile, API token, account deletion, validation |
| [access-control.md](access-control.md) | ACL | Groups, permission classes, workflow access by group, admin role |
| [workflow-definition.md](workflow-definition.md) | WDEF | `cloudgene.yaml` parsing and validation (`workflows/definition.py`) |
| [workflow-registry.md](workflow-registry.md) | WREG | Registry, install/sync, workflow models, template utils |
| [workflows-api.md](workflows-api.md) | WAPI | Public and admin workflow endpoints |
| [job-submission.md](job-submission.md) | JSUB | Submission validation, uploads, job naming, workspace layout, step variables |
| [job-queue-worker.md](job-queue-worker.md) | QUEUE | Job states, queue limits, claim, heartbeat, cancel, recovery |
| [job-runner.md](job-runner.md) | RUN | Nextflow and command-step execution, environment, exit handling |
| [job-progress-outputs.md](job-progress-outputs.md) | PROG | Trace/annotation parsing, progress, outputs, logs |
| [jobs-api.md](jobs-api.md) | JAPI | Job list/detail/status/cancel/delete/download endpoints |
| [admin-api.md](admin-api.md) | ADM | Admin dashboard, users, groups, jobs, settings, logs endpoints |
| [server-pages-mail.md](server-pages-mail.md) | SRV | Server info, navbar, pages, maintenance, health, mail |
| [logging.md](logging.md) | LOG | Application logging, formatters, admin log capture |
| [management-commands.md](management-commands.md) | CMD | All `manage.py` commands |
| [tests.md](tests.md) | TEST | Test strategy, commands, traceability |

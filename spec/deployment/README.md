# Deployment spec

Production deployment and operations: `deploy/`, `scripts/`, deployment-relevant parts of
`cloudgene_django/settings.py`, `home/`, and the full-stack test harness in `e2e/`. All files
follow [the constitution](../constitution.md).

| File | Area code | Covers |
|------|-----------|--------|
| [overview.md](overview.md) | ARCH | Topology (nginx → gunicorn web, worker, DB, filesystem), host requirements, supported platforms |
| [api-contract.md](api-contract.md) | API | Operational contracts: env vars, ports/sockets, proxy headers, health endpoint, static/SPA paths, filesystem paths, process signals |
| [environment-config.md](environment-config.md) | ENV | Every environment variable, defaults, `.env` loading, secret key, `cloudgene.env.example` |
| [web-server.md](web-server.md) | WEB | gunicorn config, workers/timeouts, upload limits |
| [reverse-proxy.md](reverse-proxy.md) | PROXY | nginx config: TLS, HSTS, proxy headers, upload size, static, timeouts |
| [process-management.md](process-management.md) | PROC | systemd units for web, worker, cleanup timer; restart, stop, sandboxing |
| [database.md](database.md) | DB | PostgreSQL (prod) vs SQLite (dev), connection settings, migrations on deploy, backups |
| [static-assets.md](static-assets.md) | STATIC | SPA build, collectstatic, whitenoise, caching headers, SPA fallback |
| [cloudgene-home.md](cloudgene-home.md) | HOME | `CLOUDGENE_HOME` layout, permissions, pages/apps/config, job workspaces, retention cleanup |
| [workflow-runtime.md](workflow-runtime.md) | RT | Java/Nextflow host requirements, `nextflow.config`/`nextflow.env`, command-step runtime, resource isolation |
| [security-hardening.md](security-hardening.md) | SEC | `check --deploy`, cookies, CSRF trusted origins, ALLOWED_HOSTS, password hashing, file permissions |
| [observability.md](observability.md) | OBS | Log formats/locations, log rotation, health monitoring, worker heartbeat alerts |
| [install-upgrade.md](install-upgrade.md) | INST | First install, admin bootstrap, workflow install, upgrade and rollback procedure |
| [test-harness.md](test-harness.md) | HARN | `scripts/test.sh`, `smoke_gunicorn.sh`, the e2e stack harness (`e2e/stack.py`, conftest, fixtures apps, exploratory probes) |
| [tests.md](tests.md) | TEST | Test strategy, commands, traceability for deployment requirements |

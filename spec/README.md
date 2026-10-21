# Cloudgene spec

Normative specification for Cloudgene. Start with the [constitution](constitution.md).

- [backend/](backend/README.md) — Django + DRF API, worker, workflows, jobs
- [frontend/](frontend/README.md) — Vue 3 SPA
- [deployment/](deployment/README.md) — production deployment, operations and test harness

The frontend/backend interface is defined once, in `schema.yaml`, and indexed in
[backend/api-contract.md](backend/api-contract.md) and
[frontend/api-contract.md](frontend/api-contract.md) (constitution Article 5).

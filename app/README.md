---
title: Log Anomaly Detection Platform
emoji: 🚨
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Log Anomaly Detection Platform

Production-shaped FastAPI service for classifying log/security events,
serving the actual fine-tuned model registered by
[Reproducible Fine-Tuning Pipeline](https://github.com/sugarhillconsultants/reproducible-finetuning-pipeline)
(`oromeop/log-classifier-tiny@v1.0.0`), with JWT auth, an async
database recording every prediction, and background-task audit logging
and anomaly alerting.

Same container also deploys to Azure Container Apps, with real
canary-rollout automation gated on live failure-rate monitoring — see
the parent repo's [architecture doc](https://github.com/sugarhillconsultants/log-anomaly-platform/blob/main/docs/architecture.md).

## Endpoints

- `GET /` — status, including which model version is loaded
- `GET /health` — readiness probe target
- `POST /token` — get a JWT (form fields: `username`, `password`)
- `POST /events` — classify a log event (requires `Authorization: Bearer <token>`)
- `GET /events/{id}` — retrieve a previously classified event (requires auth)

# Architecture: How This Ties Projects 2 and 3 Together

This project is deliberately not built from scratch — it's the
integration point for the other two portfolio projects, plus the two
pieces neither of them covered.

## What comes from [Reproducible Fine-Tuning Pipeline](https://github.com/sugarhillconsultants/reproducible-finetuning-pipeline)

The actual model this app serves: `oromeop/log-classifier-tiny@v1.0.0`,
loaded directly from the Hub in `app/main.py`'s `get_classifier()`. This
isn't a placeholder or a re-trained copy — it's the exact model that
pipeline's F1 gate approved and registered. If that pipeline runs again
and registers a new tagged version, updating `MODEL_REVISION` in
`main.py` and redeploying is the entire integration step.

## What comes from [Multi-Cloud MLOps Showcase](https://github.com/sugarhillconsultants/multi-cloud-mlops-showcase)

The infrastructure pattern: Bicep-provisioned ACR (admin disabled),
Container Apps with managed-identity `AcrPull`, OIDC-based GitHub
Actions auth, dual deployment to Azure Container Apps and a Hugging
Face Space from the same image. Two specific lessons from that
project's real debugging session are built in from the start here
rather than rediscovered:

- The `useAcrImage` toggle in `infra/modules/container-app.bicep`,
  breaking the managed-identity/AcrPull circular dependency on first
  deploy.
- `minReplicas: 1`, not `0` — Project 3 hit repeated cold-start `504`s
  from scale-to-zero; this project trades a small always-on cost for a
  reliably responsive app, a reasonable choice for something meant to
  be clicked on by a reviewer.

## What's actually new here

**JWT auth and an async database.** Project 3's showcase app
deliberately had no auth or persistence, to keep that project focused
purely on infrastructure. Here, every classified event requires a
valid token and is recorded in a real (if SQLite-backed) database via
async SQLAlchemy 2.0 — `app/auth.py`, `app/database.py`.

**Real canary rollback, not a documented stub.** Project 3's
`canary_deployment_rings.sh` has a `check_failure_rate()` function
explicitly left as a placeholder, with a comment noting it would query
Application Insights in a real implementation. `deploy/canary_rollback.py`
here actually does that — a real `LogsQueryClient` call against Azure
Monitor, with an actual KQL query, actually gating whether traffic
progresses through 10% → 50% → 100% or rolls back. This is the
concrete difference between "the pipeline has a step called canary
rollout" and "the pipeline will actually stop a bad deploy without a
human watching a dashboard."

## Known gap, stated honestly

The canary script currently determines "bad" purely from HTTP-level
failure rate (`success == false` in the `requests` table) — it has no
visibility into whether the model itself is producing worse
*predictions*, only whether the API is erroring. A more complete
version would also track prediction-confidence distribution or a
sampled-accuracy signal against known-labeled traffic, catching a
"technically working but quietly wrong" model the same way this
project's own README elsewhere argues matters. Not implemented here —
worth treating as the natural next increment.

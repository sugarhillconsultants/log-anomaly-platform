# Log Anomaly Detection Platform

**Status: fully verified end-to-end, including the real CI/CD pipeline,
the live canary rollout, and a working cross-project data feed to
[Model Observability Dashboard](https://github.com/sugarhillconsultants/model-observability-dashboard)**
— every job in `.github/workflows/deploy.yml` has actually run and
passed against real infrastructure: test-gated CI, dual-cloud
deployment, a genuine 10%→50%→100% canary rollout gated on a live
Application Insights query, and a real `/events/recent-features`
endpoint confirmed serving real prediction data end to end. Getting
here took eleven distinct real incidents across application code, CI
configuration, deployment mechanics, and integration work with a
downstream project. Full account: [`docs/incidents.md`](docs/incidents.md).

The flagship of a three-project MLOps portfolio — this is where the
other two projects' outputs actually get used together. Full
integration details: [`docs/architecture.md`](docs/architecture.md).

- **[Reproducible Fine-Tuning Pipeline](https://github.com/sugarhillconsultants/reproducible-finetuning-pipeline)** →
  provides the actual model this app serves
- **[Multi-Cloud MLOps Showcase](https://github.com/sugarhillconsultants/multi-cloud-mlops-showcase)** →
  provides the infrastructure and deployment pattern, with two of its
  real debugging lessons built in from the start
- **This project adds:** JWT auth, an async database logging every
  prediction, and a canary rollout wired to a *live* Application
  Insights query — not a documented placeholder.
- **[Model Observability Dashboard](https://github.com/sugarhillconsultants/model-observability-dashboard)**
  now depends on this repo in turn: `GET /events/recent-features`
  (added below) exposes real confidence/text-length data so that
  project's drift detection has genuine production data to compare
  against, rather than a placeholder or invented distribution.

## What's actually in this repo

| Path | What it does |
|---|---|
| `app/main.py` | FastAPI app loading `oromeop/log-classifier-tiny@v1.0.0` from the Hub, JWT-protected `/events` endpoints, plus `/events/recent-features` (added to feed [Project 4](https://github.com/sugarhillconsultants/model-observability-dashboard)'s drift detection with real confidence/text-length data) |
| `app/auth.py` | JWT authentication (`OAuth2PasswordBearer`) |
| `app/database.py` | Async SQLAlchemy 2.0 — every classified event persisted |
| `app/background.py` | Post-response audit logging and high-confidence anomaly alerting |
| `infra/*.bicep` | ACR, Container Apps, monitoring — with Project 3's circular-dependency and cold-start fixes included from the start |
| `deploy/canary_rollback.py` | **Real** progressive rollout (10%→50%→100%) gated on a live Azure Monitor query, with automatic rollback |
| `tests/test_main.py` | Auth, protected-endpoint, and classification tests (model mocked for speed/determinism) |
| `.github/workflows/deploy.yml` | Test-gated, OIDC-authenticated, dual-cloud deploy with the canary step wired in |
| `docs/architecture.md` | How this ties to the other two projects, plus an honest stated gap |

## Verified results

Every layer of this platform has actually been exercised against live
infrastructure, not just described:

```
POST /token → real JWT issued
POST /events {"text": "Failed password for invalid user root..."}
  → {"event_id":1, "predicted_label":"security_anomaly", "confidence":0.619}
POST /events {"text": "User alice logged in successfully..."}
  → {"event_id":2, "predicted_label":"normal", "confidence":0.737}
GET /events/1 (with auth) → correctly retrieves the first record
GET /events (no auth) → correctly rejected with 401

GitHub Actions — every job passing:
  test → build-and-push → deploy-container-apps-canary
  (real 10% → 50% → 100% ramp, gated on a live App Insights query)
  → deploy-huggingface-space

GET /events/recent-features (with auth), after fixing a route-order bug
  → {"n":2,"confidence":[0.737,0.619],"text_length":[47,54],
     "predicted_labels":["normal","security_anomaly"]}
```

The model genuinely distinguishes anomalous from normal log lines
(not just returning one label regardless of input), auth is genuinely
enforced, persistence genuinely round-trips through the async
database (within a single deployment's lifetime — see incident #11 on
why that caveat matters), the canary rollout genuinely ramped traffic
and genuinely queried live telemetry to decide whether to continue,
and the new endpoint added for Project 4 genuinely serves real
prediction data after a real route-ordering bug was found and fixed.

## Honestly, what it took to get here

Eleven real incidents, documented in full in
[`docs/incidents.md`](docs/incidents.md):
- Two lessons carried over correctly from Project 3 (a circular
  IAM dependency, a readiness-probe/port mismatch) — built in from
  the start this time, and confirmed to not recur.
- A `passlib`/modern-`bcrypt` incompatibility crashing the app at
  import time, before Uvicorn ever started.
- A genuine design bug in this project's own code: a field-name
  mismatch between the database model (`id`) and the API response
  model (`event_id`) — the first application-logic bug (as opposed
  to tooling/dependency friction) across all three portfolio projects.
- A subtle Container Apps trap: deploying with a mutable `:latest`
  tag silently prevented two consecutive, genuinely-fixed rebuilds
  from ever actually taking effect.
- Two real CI configuration bugs, found the moment the actual
  GitHub Actions pipeline was run for the first time: a
  `working-directory`/`PYTHONPATH` mismatch, and a `TestClient` used
  without triggering the app's `lifespan` startup handler.
- A pure process failure, not a code bug: a fix validated live in
  Cloud Shell was never committed before the ephemeral session ended,
  silently discarding it.
- The same Azure OIDC subject-mismatch from Project 2, recurring on
  this repo's own federated credentials.
- **The richest incident in this entire portfolio**: four compounding
  bugs in the canary rollout itself (a revision-name length limit, a
  revisions-mode default that made canary splitting impossible, a
  *persistent* ingress traffic rule that kept auto-promoting every new
  revision even after fixing the mode, and a workspace-identifier
  format mismatch that then left the app in a partially-split traffic
  state) — each found one at a time by watching the actual rollout fail
  against live traffic, not by code review.
- A classic FastAPI route-ordering bug when adding
  `/events/recent-features` for Project 4: a literal path defined
  *after* a path-parameter route (`/events/{event_id}`) got silently
  shadowed by it, since the parameter pattern matches any string.
- An honest architectural limitation, not a bug to hide: event history
  lives in a local SQLite file that doesn't survive a container
  redeploy, so it reset to empty after every fix this session —
  confirmed deliberately rather than assumed, then documented as a
  real constraint on how much history Project 4 can ever see.

## What I'd add next

- **Move off local SQLite to a persistent database** (e.g. Azure
  Database for PostgreSQL) — incident #11 showed plainly that event
  history currently resets on every redeploy, which caps how much
  history Project 4's drift detection can ever see.
- Wire up the honest gap noted in `docs/architecture.md` — prediction-
  quality signal in the canary gate, not just HTTP failure rate.
- A GitHub Actions job that automatically bumps `MODEL_REVISION` in
  `main.py` when Project 2's pipeline registers a new tagged version,
  closing the loop between the two repos entirely.

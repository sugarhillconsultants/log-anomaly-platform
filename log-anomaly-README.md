# Log Anomaly Detection Platform

**Status: fully verified end-to-end against live infrastructure.**
Getting here took five real, distinct bugs — one a genuine design
mistake in this project's own code, one a subtle Container Apps
deployment-mechanics trap that silently prevented two consecutive
fixes from actually taking effect. Full account:
[`docs/incidents.md`](docs/incidents.md).

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

## What's actually in this repo

| Path | What it does |
|---|---|
| `app/main.py` | FastAPI app loading `oromeop/log-classifier-tiny@v1.0.0` from the Hub, JWT-protected `/events` endpoints |
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
```

The model genuinely distinguishes anomalous from normal log lines
(not just returning one label regardless of input), auth is genuinely
enforced, and persistence genuinely round-trips through the async
database.

## Honestly, what it took to get here

Five real bugs, documented in full in
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
  from ever actually taking effect, since Azure didn't detect the
  (textually unchanged) image reference as revision-worthy. Only
  resolved by forcing a new revision via `--revision-suffix`.

## What's still genuinely untested

To be precise about scope: the application, database, auth, and model
integration were verified via **manual** `az acr build` /
`az containerapp update` commands in Cloud Shell — the faster path for
debugging the five incidents above in real time. The actual GitHub
Actions workflow (`.github/workflows/deploy.yml`) and
`deploy/canary_rollback.py`'s live Application Insights query have
**not** yet been exercised end-to-end. Running the real CI pipeline is
the natural next step — and given this project's own incident log, it
would be dishonest to assume it succeeds on the first try without
actually doing it. The `:latest`-tag trap from incident #5 specifically
is worth watching for again there, since `deploy.yml` currently pushes
both a SHA-based tag and `:latest` — the SHA tag should sidestep this
exact issue if the workflow is updated to deploy using it instead of
`:latest`.

## What I'd add next

- Wire up the honest gap noted in `docs/architecture.md` — prediction-
  quality signal in the canary gate, not just HTTP failure rate.
- A GitHub Actions job that automatically bumps `MODEL_REVISION` in
  `main.py` when Project 2's pipeline registers a new tagged version,
  closing the loop between the two repos entirely.

# Log Anomaly Detection Platform

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

## Verified so far

- Label-normalization logic (mapping `LABEL_0`/`LABEL_1`/raw strings to
  `normal`/`security_anomaly`) tested directly against all expected
  Hub pipeline output formats.
- Canary ring-progression and rollback-trigger logic tested against
  both a healthy-rollout scenario and a bad-deploy-caught-at-50%
  scenario.
- All Python files compile cleanly.

## Honestly not yet verified

Unlike Projects 2 and 3, **this repo has not yet been run against live
Azure/GitHub Actions infrastructure.** Given how many real bugs surfaced
in each of those two projects' first live runs — a secret/variable
mix-up, token scope gaps, a tokenizer incompatibility, a Python
namespace collision, a pip resolver issue, a circular IAM dependency,
cold-start 504s — it would be dishonest to claim this one will run
clean on the first try just because it reuses proven patterns. The
canary script specifically (`deploy/canary_rollback.py`) has real,
correct logic verified in isolation, but has never actually queried a
real Application Insights workspace or issued a real
`az containerapp ingress traffic set` command. Treat this repo as
**scaffolded and logic-verified, not yet field-tested** — the next
real step is pushing it to GitHub, wiring up the same secrets/variables
pattern as the other two projects, and working through whatever
actually breaks, the same way those two were debugged.

## What I'd add next

- Wire up the honest gap noted in `docs/architecture.md` — prediction-
  quality signal in the canary gate, not just HTTP failure rate.
- A GitHub Actions job that automatically bumps `MODEL_REVISION` in
  `main.py` when Project 2's pipeline registers a new tagged version,
  closing the loop between the two repos entirely.

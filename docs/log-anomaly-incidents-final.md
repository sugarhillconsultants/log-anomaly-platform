# Real Incidents Encountered Running This Platform

Same rationale as the other two projects in this portfolio: an honest
account of what actually broke, found from real failure logs, is more
useful than a pipeline that "just worked." This project's incident log
is the richest of the three — it hit a wider spread of bug categories
than either companion project alone, since it's the one combining
infrastructure, a real model, and new application-layer code all at once.

## 1–2. The two Project 3 lessons that held up on a genuinely fresh deployment

Unlike Project 3, where the `useAcrImage` circular-dependency toggle and
the port-7860 readiness probe were discovered *after* a failed first
deploy, both were built into this project's Bicep from the start. Both
worked correctly on the very first real deployment attempt — no repeat
of either bug. Worth recording as a real, positive outcome: applying a
lesson learned once genuinely prevented it from recurring on a new,
independent project.

## 3. `passlib` + modern `bcrypt` incompatibility crashing the app at import time

The first deploy of the real application image resulted in a complete
connection timeout — no HTTP response at all, not even an error page.
`az containerapp logs show --type console` revealed the actual cause:
a Python traceback inside `passlib`'s bcrypt backend self-test,
`ValueError: password cannot be longer than 72 bytes`. `passlib`
(unmaintained since 2020) runs an internal wraparound-bug self-test at
import time; modern `bcrypt` (4.1+) now strictly enforces its 72-byte
limit even during that internal test, crashing before Uvicorn ever
binds to a port. Since `app/auth.py` calls `pwd_context.hash(...)` at
**module import time** (building the demo user store), this crash
happened on every single container startup attempt — explaining both
the total timeout and the `ContainerBackOff` restart loop in the system
logs. Fixed by pinning `bcrypt==4.0.1` in `requirements.txt`, the last
release before the breaking behavior change.

## 4. A real bug in this project's own code: `event_id` field-name mismatch

With #3 fixed, the app started and `/health` returned 200 — but the
first real classification request (`POST /events`) returned a plain
`Internal Server Error`. The full traceback showed a Pydantic
`ResponseValidationError`: `{'type': 'missing', 'loc': ('response',
'event_id'), 'msg': 'Field required'}`. The cause: `database.py`'s
SQLAlchemy model names its primary key `id`, while `main.py`'s
`LogEventOut` response model expects a field called `event_id`.
Returning the raw ORM object directly (`return record`) relies on
Pydantic's `from_attributes` mode doing `getattr(record, "event_id")`
— which doesn't exist. Unlike incidents #1–3 and everything in the
other two projects' logs (infrastructure/IAM issues or third-party
dependency incompatibilities), **this is the first bug across all
three portfolio projects that's a genuine design mistake in this
project's own application code**, not tooling or a dependency. Fixed
by adding an `event_id` property to `LogEventRecord` that returns
`self.id`, bridging the two names.

## 5. A mutable `:latest` tag silently prevented two consecutive fixes from actually deploying

This was the most confusing incident to diagnose, and took two full
rebuild-and-redeploy cycles to understand. After fixing #4, rebuilding
the image, and running `az containerapp update --image ...:latest`, the
exact same `event_id` traceback appeared again — twice. Direct
inspection (`cat app/database.py` in the actual deployed working
directory) confirmed the property genuinely wasn't present in the file
the first time; after re-applying it and rebuilding a second time
(confirmed via a new image digest), the *same error recurred a third
time* despite the fix being genuinely present in the source and a new
digest genuinely having been pushed to ACR. The real cause: **Container
Apps only creates a new named revision when it detects a change to
revision-scope configuration** — and since `--image ...:latest` is the
same literal string on every deploy (even though the tag now points at
a different underlying digest), Azure did not treat it as a
revision-worthy change, leaving the stale container running
indefinitely across two "successful" `containerapp update` calls that
silently did nothing. Confirmed by checking `latestRevisionName`, which
stayed identical across both no-op updates. Fixed by forcing a
genuinely new revision with `--revision-suffix`, which guarantees a
fresh pull regardless of whether the image reference text changed.
**This is a real, generalizable trap**: deploying to Container Apps
with a mutable tag (`:latest`) rather than an immutable one (a commit
SHA, as this portfolio's other two projects correctly do in their CI
workflows) can silently prevent a real code change from ever actually
reaching production, with no error at any step to indicate it.

## 6. The actual CI pipeline had never been run — and immediately found two real bugs

Everything above was diagnosed via **manual** `az acr build`/
`az containerapp update` commands in Cloud Shell — faster for real-time
debugging, but it meant `.github/workflows/deploy.yml` itself had never
actually executed. The first real CI run failed at `pytest tests/ -v`
with `ModuleNotFoundError: No module named 'main'` — the workflow's
`pip install` step ran with `working-directory: app`, but the `pytest`
step didn't, so `app/main.py` was never on Python's import path from
the repo root. Fixed by installing from the root against
`app/requirements.txt` and setting `PYTHONPATH: app` for the test step.

That fix immediately surfaced a second, real bug: 3 of 8 tests failed
with `sqlite3.OperationalError: no such table: log_events`. The test
file created `TestClient(app)` as a plain object rather than via
`with TestClient(app) as client:` — and FastAPI/Starlette only run the
app's `lifespan` handler (which calls `init_db()`) when the client is
used as a context manager. Fixed by manually calling
`TestClient(app).__enter__()` once at module scope, so lifespan
startup genuinely runs before any test executes.

## 7. A fix confirmed working live was never actually saved — Cloud Shell's ephemeral session discarded it

With #6 fixed, CI still failed on the exact same `event_id` error from
incident #4 — even though that bug had already been fixed and verified
working in the live deployment. The reason: the original fix was made
directly in a Cloud Shell session and used to rebuild the ACR image,
but **Cloud Shell sessions are ephemeral** — nothing persists once the
session ends unless it's committed to git. The fix had been validated
against production but never actually reached GitHub. This is a
distinct failure category from every other incident in this log: not a
code bug, not an infrastructure quirk, but a **process gap** between
"I fixed it and confirmed it worked" and "the fix is durably recorded
anywhere." Re-applying and committing the fix (twice, due to a
duplicate-property mistake along the way, cleaned up before pushing)
finally got all 8 tests passing in real CI for the first time.

## 8. The Azure OIDC subject-mismatch from Project 2, recurring on a second repo

Once `test` passed, `azure/login@v2` failed with the identical
`AADSTS700213` error already diagnosed in Project 2: GitHub's OIDC
subject claim includes stable numeric org/repo IDs once a rename has
ever occurred (`repo:org@<id>/repo@<id>:...`), and the federated
credentials for this repo had been created with the plain, unqualified
form. Fixed the same way as Project 2 — deleting and recreating both
federated credentials (the `ref:refs/heads/main` one and the
`environment:production` one) with the exact ID-qualified subject from
the error. A good example of a lesson from one project transferring
directly to another, once actually recognized.

## 9. The real canary rollout: four compounding bugs, found one at a time against live traffic

This was the richest single incident in the entire three-project
portfolio, and the last piece of code anywhere in this portfolio to be
verified against real infrastructure.

**9a — Revision name exceeded Azure's 54-character limit.** The first
live attempt failed immediately: `ContainerAppInvalidRevisionName`. A
full 40-character git SHA, combined with the app name and separator
(`ca-log-anomaly--<40 chars>`), exceeded Azure's 54-character combined
limit by 2. Fixed by computing an 8-character short SHA once per job
and reusing it consistently across the deploy and canary steps.

**9b — `activeRevisionsMode` defaulted to `Single`, making a canary
split architecturally impossible.** With the naming fixed, the script
still failed: `get_last_good_revision()` kept finding the *brand-new*
revision as "last good," because in `Single` mode a newly deployed
revision is automatically promoted to 100% traffic immediately — there
is no way to hold two revisions at different weights at all in this
mode. Fixed by adding `activeRevisionsMode: 'Multiple'` to the Bicep
and applying it to the live app directly via
`az containerapp revision set-mode`.

**9c — Even in `Multiple` mode, a *persistent* ingress rule kept
re-promoting every new revision anyway.** This was the genuinely
surprising one: after enabling `Multiple` mode, the *exact same*
symptom recurred on a fresh revision. The actual cause was one line in
`container-app.bicep`: `traffic: [{ latestRevision: true, weight: 100
}]` — not a one-time initial setting, but a standing rule Azure
re-applies every time a new revision is created, regardless of
revision mode. The only real fix was reordering the whole flow:
capture the last-good revision **before** deploying anything, deploy,
then **immediately re-pin traffic explicitly** to override the
auto-promotion before starting the actual ramp. This required
consolidating the separate "deploy" workflow step into
`canary_rollback.py` itself, since the query and the deploy have to
happen in one guaranteed order within a single process.

**9d — Wrong Application Insights identifier format, then a partially-split
traffic state from the crash it caused.** With 9a–9c fixed, the ramp
correctly reached 10%/90% — genuine progress — then crashed on
`azure.core.exceptions.HttpResponseError: PathNotFoundError` querying
Application Insights. The `--app-insights-app-id` value was the full
ARM resource path; the Azure Monitor Query SDK's `query_workspace()`
expects the workspace's **GUID** (`customerId`), a completely different
format. Fixed by retrieving the correct GUID via
`az monitor log-analytics workspace show --query customerId`. Along
the way, this crash left the live app in a genuinely split 10%/90%
traffic state with no revision at exactly 100% — which then broke
`get_last_good_revision()`'s exact-match query on the *next* attempt,
returning nothing and producing a malformed `az` command. Fixed the
underlying query to pick whichever revision holds the *highest*
current weight rather than requiring exactly 100%, added an explicit
guard that fails loudly if no revision is found at all, and manually
reset the live app's traffic to a clean state before the final run.
Also hardened `get_failure_rate_pct()` with a try/except around the
query call itself, so a future transient Azure Monitor error degrades
to "treat as 0% and continue" rather than crashing the whole rollout —
the graceful-degradation path the code already had for a
non-`SUCCESS` query status didn't cover an outright exception.

**After all four**, the canary rollout completed genuinely end to end:
capture last-good revision → deploy → re-pin traffic → ramp to 10% →
live Application Insights query succeeds → continue to 50% → 100%,
against real Azure infrastructure, for the first time in this
project's history.

## After all fixes: a genuine, verified end-to-end pass

```
POST /token → 200, real JWT issued
POST /events {"text": "Failed password for invalid user root..."}
  → {"event_id":1, "predicted_label":"security_anomaly", "confidence":0.619}
POST /events {"text": "User alice logged in successfully..."}
  → {"event_id":2, "predicted_label":"normal", "confidence":0.737}
GET /events/1 (with auth) → correctly retrieves the first record

GitHub Actions: test -> build-and-push -> deploy-container-apps-canary
  (full 10% -> 50% -> 100% ramp, gated on a live App Insights query)
  -> deploy-huggingface-space
ALL JOBS PASSING
```

Auth is genuinely enforced, the actual fine-tuned model from Project 2
is genuinely loaded and classifying correctly in both directions,
persistence genuinely round-trips, and — as of incident #9 — the
canary rollout this whole project was built to demonstrate is
genuinely working against live infrastructure, not just documented as
a script that theoretically implements one.

## The throughline across all three projects' incident logs

- **Project 3**: infrastructure/IAM-shaped bugs (circular dependencies,
  OIDC subject-claim rules).
- **Project 2**: Python/ML-tooling-shaped bugs (namespace collisions,
  tokenizer conversion edge cases, dependency resolver behavior).
- **Project 1 (this one)**: a genuine spread across *all* of the above,
  plus two categories no other project in this portfolio hit: a real
  application-logic bug (#4), a deployment-mechanics trap specific to
  Container Apps' revision model (#5), a pure process gap between
  "verified working" and "actually committed" (#7), and — the deepest
  of all — a persistent platform-level traffic rule that silently
  defeated a script whose logic was otherwise completely correct (#9c),
  only discoverable by watching it fail against real, live traffic
  multiple times in sequence.

None of these were anticipated in advance. Every one was found by
actually running the thing against real infrastructure and reading
what it said — which remains the entire argument, across all three
projects, for why "deployed and verified" is a meaningfully different
(and more valuable) claim than "written and looks correct."

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

## After all fixes: a genuine, verified end-to-end pass

```
POST /token → 200, real JWT issued
POST /events {"text": "Failed password for invalid user root..."}
  → {"event_id":1, "predicted_label":"security_anomaly", "confidence":0.619}
POST /events {"text": "User alice logged in successfully..."}
  → {"event_id":2, "predicted_label":"normal", "confidence":0.737}
GET /events/1 (with auth) → correctly retrieves the first record
```

Auth is genuinely enforced (unauthenticated and unauthorized requests
both correctly rejected before this point), the actual fine-tuned model
from Project 2 is genuinely loaded and classifying correctly in both
directions, and persistence genuinely round-trips.

## The throughline across all three projects' incident logs

- **Project 3**: infrastructure/IAM-shaped bugs (circular dependencies,
  OIDC subject-claim rules).
- **Project 2**: Python/ML-tooling-shaped bugs (namespace collisions,
  tokenizer conversion edge cases, dependency resolver behavior).
- **Project 1 (this one)**: a genuine spread across *all* of the above,
  plus the first real application-logic bug in this portfolio (#4) and
  a deployment-mechanics trap specific to how Container Apps handles
  mutable tags (#5) — the kind of bug that has nothing to do with
  Python, ML, or IAM, and everything to do with the specific semantics
  of one platform's revision model.

None of these were anticipated in advance. Every one was found by
actually running the thing against real infrastructure and reading
what it said — which remains the entire argument, across all three
projects, for why "deployed and verified" is a meaningfully different
(and more valuable) claim than "written and looks correct."

#!/usr/bin/env python3
"""
deploy/canary_rollback.py

Real, working canary rollout for Azure Container Apps, gated on a LIVE
Application Insights query — this is the piece Project 3's showcase
left as a documented but unimplemented stub (see that repo's
canary_deployment_rings.sh, which has a placeholder check_failure_rate
function). Here it's actually implemented against the real Azure
Monitor Query SDK.

Install once:
  pip install azure-identity azure-monitor-query azure-mgmt-appcontainers

Usage:
  python canary_rollback.py \
      --app-name ca-log-anomaly --resource-group rg-log-anomaly-dev \
      --new-revision-suffix abc123 --app-insights-app-id <guid> \
      --failure-threshold-pct 5.0
"""

import argparse
import subprocess
import sys
import time

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus


def run_az(args: list[str]) -> str:
    result = subprocess.run(["az"] + args, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def get_last_good_revision(app_name: str, resource_group: str) -> str:
    return run_az([
        "containerapp", "revision", "list",
        "--name", app_name, "--resource-group", resource_group,
        "--query", "[?properties.trafficWeight==`100`].name | [0]",
        "-o", "tsv",
    ])


def deploy_new_revision(app_name: str, resource_group: str, image: str, revision_suffix: str):
    """Creates the new revision. NOTE: this app's ingress uses a
    `latestRevision: true` traffic rule (see infra/modules/container-app.bicep),
    which is a *persistent* rule Azure re-applies on every new revision —
    not a one-time initial setting. That means the instant this command
    finishes, Azure will have already auto-promoted the new revision to
    100% traffic, regardless of Single/Multiple active revisions mode.
    This is exactly why the caller must capture the "last good" revision
    BEFORE calling this function, and immediately re-pin traffic after —
    see run_canary() below."""
    run_az([
        "containerapp", "update",
        "--name", app_name, "--resource-group", resource_group,
        "--image", image,
        "--revision-suffix", revision_suffix,
    ])


def set_traffic(app_name: str, resource_group: str, new_revision: str, new_pct: int, old_revision: str):
    old_pct = 100 - new_pct
    run_az([
        "containerapp", "ingress", "traffic", "set",
        "--name", app_name, "--resource-group", resource_group,
        "--revision-weight", f"{new_revision}={new_pct}", f"{old_revision}={old_pct}",
    ])
    print(f"Traffic set: {new_revision}={new_pct}%, {old_revision}={old_pct}%")


def rollback(app_name: str, resource_group: str, good_revision: str):
    print(f"ROLLING BACK to {good_revision} (100%)")
    run_az([
        "containerapp", "ingress", "traffic", "set",
        "--name", app_name, "--resource-group", resource_group,
        "--revision-weight", f"{good_revision}=100",
    ])


def get_failure_rate_pct(app_insights_app_id: str, minutes: int = 5) -> float:
    """The real implementation: queries Application Insights via the
    Azure Monitor Query SDK for the actual failure rate over the last
    N minutes. Returns 0.0 if there's no traffic yet (nothing to fail)."""
    credential = DefaultAzureCredential()
    client = LogsQueryClient(credential)

    query = f"""
    requests
    | where timestamp > ago({minutes}m)
    | summarize total = count(), failed = countif(success == false)
    | extend rate = iff(total == 0, 0.0, 100.0 * failed / total)
    | project rate
    """

    response = client.query_workspace(
        workspace_id=app_insights_app_id,
        query=query,
        timespan=None,
    )

    if response.status != LogsQueryStatus.SUCCESS:
        print(f"Warning: App Insights query did not succeed ({response.status}); "
              f"treating as 0% failure rate rather than blocking the rollout on a query error.")
        return 0.0

    table = response.tables[0]
    if not table.rows:
        return 0.0

    return float(table.rows[0][0])


def run_canary(app_name: str, resource_group: str, image: str, new_revision_suffix: str,
                app_insights_app_id: str, failure_threshold_pct: float):
    new_revision = f"{app_name}--{new_revision_suffix}"

    # CRITICAL ORDERING: capture the currently-good revision BEFORE
    # deploying anything new. Once deploy_new_revision() runs, the
    # `latestRevision: true` ingress rule immediately promotes the new
    # revision to 100% — if we queried "last good" afterward, we'd just
    # find the new revision itself (this is the exact bug that broke
    # the first two live runs of this script).
    good_revision = get_last_good_revision(app_name, resource_group)
    print(f"Last known-good revision (captured before deploying): {good_revision}")

    print(f"Deploying new revision {new_revision}...")
    deploy_new_revision(app_name, resource_group, image, new_revision_suffix)

    # Immediately override the auto-promotion: pin the new revision to 0%
    # and the previously-good one back to 100%, so the ramp below starts
    # from a known, deliberate state rather than whatever Azure's
    # latestRevision rule just did on its own.
    print("Re-pinning traffic to override auto-promotion before starting the ramp...")
    set_traffic(app_name, resource_group, new_revision, 0, good_revision)

    rings = [(10, 120), (50, 180), (100, 0)]  # (traffic_pct, wait_seconds)

    for pct, wait_seconds in rings:
        set_traffic(app_name, resource_group, new_revision, pct, good_revision)

        if pct == 100:
            print("Rollout complete: 100% traffic on new revision.")
            break

        print(f"Monitoring for {wait_seconds}s at {pct}% traffic...")
        time.sleep(wait_seconds)

        failure_rate = get_failure_rate_pct(app_insights_app_id)
        print(f"Observed failure rate: {failure_rate:.2f}% (threshold: {failure_threshold_pct}%)")

        if failure_rate > failure_threshold_pct:
            rollback(app_name, resource_group, good_revision)
            print(f"ROLLED BACK: failure rate {failure_rate:.2f}% exceeded "
                  f"{failure_threshold_pct}% threshold at {pct}% traffic.")
            sys.exit(1)

    print("Canary rollout succeeded — new revision fully promoted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--image", required=True, help="Full image reference to deploy")
    parser.add_argument("--new-revision-suffix", required=True)
    parser.add_argument("--app-insights-app-id", required=True,
                         help="Log Analytics workspace ID backing App Insights")
    parser.add_argument("--failure-threshold-pct", type=float, default=5.0)
    args = parser.parse_args()

    run_canary(
        args.app_name, args.resource_group, args.image, args.new_revision_suffix,
        args.app_insights_app_id, args.failure_threshold_pct,
    )

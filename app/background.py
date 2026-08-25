"""
app/background.py

Work that happens after a response is returned, without making the
caller wait — audit logging and anomaly alerting.
"""

import time


def write_audit_log(event_id: int, predicted_label: str, username: str):
    time.sleep(0.5)  # simulates a slower audit-store write
    with open("audit.log", "a") as f:
        f.write(f"event_id={event_id} label={predicted_label} by={username}\n")


def send_alert_if_anomalous(event_id: int, predicted_label: str, confidence: float):
    if predicted_label == "security_anomaly" and confidence > 0.85:
        time.sleep(0.2)  # simulates a webhook call
        print(f"[ALERT] High-confidence security anomaly: event_id={event_id} "
              f"(confidence={confidence:.2f})")

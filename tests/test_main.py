"""
tests/test_main.py

Tests gating CI. The real Hub model is mocked so tests are fast,
deterministic, and don't require network access — same pattern used in
Project 3's showcase app.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

with patch("main.get_classifier") as mock_get_classifier:
    mock_get_classifier.return_value = lambda text, truncation=True: [
        {"label": "LABEL_1", "score": 0.91}
        if "failed password" in text.lower() or "unauthorized" in text.lower()
        else {"label": "LABEL_0", "score": 0.87}
    ]
    from main import app

client = TestClient(app)


def get_auth_token():
    response = client.post("/token", data={"username": "analyst", "password": "changeme123"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_root_reports_model_identity():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert "oromeop/log-classifier-tiny" in body["model"]


def test_login_success():
    token = get_auth_token()
    assert isinstance(token, str) and len(token) > 0


def test_login_failure():
    response = client.post("/token", data={"username": "analyst", "password": "wrongpassword"})
    assert response.status_code == 401


def test_create_event_requires_auth():
    response = client.post("/events", json={"text": "some log line"})
    assert response.status_code == 401


def test_create_event_normal():
    token = get_auth_token()
    response = client.post(
        "/events",
        json={"text": "User alice logged in successfully", "source": "ssh"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["predicted_label"] == "normal"


def test_create_event_security_anomaly():
    token = get_auth_token()
    response = client.post(
        "/events",
        json={"text": "Failed password for invalid user root", "source": "ssh"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["predicted_label"] == "security_anomaly"


def test_get_event_not_found():
    token = get_auth_token()
    response = client.get("/events/99999", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["predicted_label"] == "not_found"


def test_create_event_rejects_empty_text():
    token = get_auth_token()
    response = client.post(
        "/events", json={"text": ""}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422

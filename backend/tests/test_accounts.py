"""Account roles and compatibility of existing merchant workspaces."""

import sqlite3

from app.services.saas_store import SaaSStore
from tests.conftest import sign_in_account


def test_legacy_workspaces_remain_merchants(tmp_path):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE organizations (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "slug TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO organizations VALUES (?, ?, ?, ?)",
            ("legacy", "Existing shop", "existing-shop", "2026-01-01"),
        )
    assert SaaSStore(database).get_organization("legacy")["kind"] == "merchant"
    assert SaaSStore(database).get_organization("legacy")["kind"] == "merchant"


def test_customer_and_merchant_workspaces_are_separate(api_client):
    merchant = sign_in_account(api_client, account_type="merchant")["workspaces"][0]
    assert merchant["kind"] == "merchant"
    assert merchant["role"] == "owner"
    assert api_client.get("/api/workspace").status_code == 200
    assert api_client.post("/api/auth/logout").status_code == 204
    assert api_client.get("/api/auth/me").status_code == 401

    customer = sign_in_account(api_client, account_type="customer")["workspaces"][0]
    assert customer["kind"] == "customer"
    assert customer["id"] != merchant["id"]
    assert api_client.get("/api/jobs/history").status_code == 200
    assert api_client.get("/api/workspace").status_code == 403
    assert api_client.post("/api/workspace/api-keys", json={"name": "Test key"}).status_code == 403
    assert api_client.get(
        "/api/jobs/history", headers={"X-Organization-Id": merchant["id"]}
    ).status_code == 401


def test_signup_rejects_global_admin_selection(api_client):
    response = api_client.post("/api/auth/register", json={
        "full_name": "Test user",
        "email": "role-test@example.test",
        "password": "test-password-2026",
        "account_type": "admin",
    })
    assert response.status_code == 422


def test_platform_overview_requires_configured_owner_session(api_client, settings):
    path = "/api/platform/overview"
    assert api_client.get(path).status_code == 401

    merchant = sign_in_account(api_client, account_type="merchant")
    assert merchant["platform_owner"] is False
    assert api_client.get(path).status_code == 403
    api_key = api_client.post("/api/workspace/api-keys", json={"name": "Test key"}).json()["secret"]
    api_client.post("/api/auth/logout")
    sign_in_account(api_client, account_type="customer")
    assert api_client.get(path).status_code == 403
    api_client.post("/api/auth/logout")

    body = {"email": "pending@example.test", "full_name": "Pending user", "password": "test-password-2026", "account_type": "customer"}
    assert api_client.post("/api/auth/register", json=body).status_code == 201
    assert api_client.get(path, headers={"Authorization": f"Bearer {api_key}"}).status_code == 401
    setup = "/api/auth/platform-setup"
    credentials = {"email": "platform@example.test", "password": "test-password-2026"}
    setup_body = {**credentials, "full_name": "Platform owner"}
    assert api_client.post(setup, json={**setup_body, "token": "wrong"}).status_code == 403
    settings.platform_setup_token = "one-time-platform-setup-token-for-tests"
    setup_body["token"] = settings.platform_setup_token
    assert api_client.post(setup, json={**setup_body, "email": merchant["user"]["email"]}).status_code == 409
    assert api_client.post(setup, json=setup_body).status_code == 201
    assert api_client.post(setup, json={**setup_body, "email": "second@example.test"}).status_code == 409
    assert api_client.post("/api/auth/login", json=credentials).status_code == 403
    assert api_client.post("/api/auth/platform-login", json={
        "email": merchant["user"]["email"], "password": "test-password-2026",
    }).status_code == 403
    reset = api_client.post("/api/auth/password-reset/request", json={"email": credentials["email"]})
    assert reset.json()["preview_url"] is None
    logged_in = api_client.post("/api/auth/platform-login", json=credentials)
    assert logged_in.json()["platform_owner"] is True
    assert logged_in.json()["workspaces"] == []
    assert api_client.get("/api/auth/me").json()["platform_owner"] is True
    assert api_client.get("/api/workspace").status_code == 401

    response = api_client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    overview = response.json()
    assert overview["counts"] == {
        "total": 3, "customers": 2, "merchants": 1, "unverified": 1,
        "merchant_workspaces": 1, "stores": 0, "tryon_requests": 0,
    }
    assert set(overview["accounts"][0]) == {"id", "full_name", "email", "kind", "verified", "created_at"}
    assert overview["accounts"][0]["verified"] is False
    assert api_client.get(path, params={"page": 2}).json()["accounts"] == []

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from evidence_agent import auth, main
from evidence_agent.models import AuditRun
from evidence_agent.quotas import QuotaExceeded
from evidence_agent.store import FirestoreEvidenceStore

client = TestClient(main.app)
headers = {"Authorization": "Bearer identity", "X-Firebase-AppCheck": "browser-proof"}


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "evidence-agent")
    monkeypatch.setenv("AUTH_MODE", "firebase")
    monkeypatch.setattr(auth, "_initialize_firebase", Mock())
    monkeypatch.setattr(
        auth.auth, "verify_id_token", Mock(return_value={"uid": "owner", "email_verified": True})
    )
    monkeypatch.setattr(auth.app_check, "verify_token", Mock(return_value={"app_id": "web-app"}))
    store = Mock(spec=FirestoreEvidenceStore)
    store.reserve_audit_start.return_value = True
    engine = Mock()
    engine.start.return_value = AuditRun(tree_id="owned-tree", owner_id="owner")
    dispatcher = Mock()
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "dispatcher", dispatcher)
    return store, engine, dispatcher


@pytest.fixture
def body():
    return {"tree": {"id": "owned-tree", "owner_id": "owner", "people": [], "relationships": []}}


def test_cors_accepts_browser_verification_header():
    response = client.options(
        "/v1/audits",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,x-firebase-appcheck",
        },
    )
    assert response.status_code == 200
    assert "X-Firebase-AppCheck" in response.headers["access-control-allow-headers"]


@pytest.mark.parametrize(
    ("supplied_headers", "expected"),
    [({}, 401), ({"Authorization": "Bearer identity"}, 403), (headers, 202)],
)
def test_start_requires_identity_and_browser_proof(production, body, supplied_headers, expected):
    store, engine, dispatcher = production
    response = client.post("/v1/audits", json=body, headers=supplied_headers)
    assert response.status_code == expected
    if expected == 202:
        store.reserve_audit_start.assert_called_once_with("owner", "owned-tree")
        engine.start.assert_called_once()
        dispatcher.dispatch.assert_called_once()
    else:
        store.reserve_audit_start.assert_not_called()
        engine.start.assert_not_called()
        dispatcher.dispatch.assert_not_called()


@pytest.mark.parametrize("proof", ["identity", "browser"])
def test_invalid_credentials_never_start_work(production, body, proof):
    store, engine, dispatcher = production
    verifier = auth.auth.verify_id_token if proof == "identity" else auth.app_check.verify_token
    verifier.side_effect = ValueError("invalid proof")
    response = client.post("/v1/audits", json=body, headers=headers)
    assert response.status_code == (401 if proof == "identity" else 403)
    store.reserve_audit_start.assert_not_called()
    engine.start.assert_not_called()
    dispatcher.dispatch.assert_not_called()


def test_unverified_identity_cannot_start_paid_research(production, body):
    store, engine, dispatcher = production
    auth.auth.verify_id_token.return_value = {"uid": "owner", "email_verified": False}
    response = client.post("/v1/audits", json=body, headers=headers)
    assert response.status_code == 403
    store.reserve_audit_start.assert_not_called()
    engine.start.assert_not_called()
    dispatcher.dispatch.assert_not_called()


def test_cloud_run_rejects_local_header_mode(production, body, monkeypatch):
    _, engine, _ = production
    monkeypatch.setenv("AUTH_MODE", "header")
    response = client.post("/v1/audits", json=body, headers={"X-Rootstory-User": "owner"})
    assert response.status_code == 503
    engine.start.assert_not_called()


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (QuotaExceeded("Daily person research allowance reached", 86_399), 429),
        (PermissionError("wrong stored owner"), 403),
        (RuntimeError("offline"), 503),
    ],
)
def test_quota_or_ownership_failure_never_creates_or_dispatches_run(
    production, body, result, expected
):
    store, engine, dispatcher = production
    if isinstance(result, Exception):
        store.reserve_audit_start.side_effect = result
    else:
        store.reserve_audit_start.return_value = result
    response = client.post("/v1/audits", json=body, headers=headers)
    assert response.status_code == expected
    if expected == 429:
        assert response.headers["Retry-After"] == "86399"
        assert response.json()["error"] == {
            "code": "ai_quota_exceeded",
            "message": "Daily person research allowance reached",
            "retryAfterSeconds": 86_399,
        }
    engine.start.assert_not_called()
    dispatcher.dispatch.assert_not_called()


def test_administrator_identity_cannot_bypass_person_research_quota(production, body):
    store, engine, dispatcher = production
    auth.auth.verify_id_token.return_value = {
        "uid": "owner",
        "email_verified": True,
        "admin": True,
        "owner": True,
    }
    store.reserve_audit_start.side_effect = QuotaExceeded("Daily allowance reached", 43_200)
    response = client.post("/v1/audits", json=body, headers=headers)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "43200"
    engine.start.assert_not_called()
    dispatcher.dispatch.assert_not_called()


def test_production_cannot_fall_back_to_memory_limits(production, body, monkeypatch):
    _, engine, _ = production
    monkeypatch.setattr(main, "store", main.MemoryEvidenceStore())
    response = client.post("/v1/audits", json=body, headers=headers)
    assert response.status_code == 503
    engine.start.assert_not_called()


@pytest.mark.parametrize(("field", "count"), [("people", 501), ("relationships", 2001)])
def test_payload_cardinality_limits_apply_before_work(production, body, field, count):
    store, engine, _ = production
    body["tree"][field] = [{"id": str(index)} for index in range(count)]
    assert client.post("/v1/audits", json=body, headers=headers).status_code == 422
    store.reserve_audit_start.assert_not_called()
    engine.start.assert_not_called()


def test_streamed_payload_is_bounded_without_content_length(production):
    store, engine, _ = production
    response = client.post(
        "/v1/audits",
        content=iter([b" " * (512 * 1024)] * 3),
        headers={**headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    auth.auth.verify_id_token.assert_not_called()
    store.reserve_audit_start.assert_not_called()
    engine.start.assert_not_called()


def test_cloud_run_worker_endpoint_fails_closed_without_dispatcher(production, monkeypatch):
    monkeypatch.setattr(main, "dispatcher", None)
    monkeypatch.delenv("EVIDENCE_WORKER_TOKEN", raising=False)
    response = client.post("/v1/internal/audits/any-run/work")
    assert response.status_code == 401


def test_worker_credential_remains_separate_from_browser_proof(production, monkeypatch):
    _, engine, _ = production
    monkeypatch.setenv("EVIDENCE_WORKER_TOKEN", "internal-worker-credential")
    response = client.post("/v1/internal/audits/any-run/work", headers=headers)
    assert response.status_code == 401
    engine.plan.assert_not_called()


def test_valid_worker_credential_does_not_need_browser_proof(production, monkeypatch):
    store, engine, dispatcher = production
    monkeypatch.setenv("EVIDENCE_WORKER_TOKEN", "internal-worker-credential")
    store.get_run.return_value = AuditRun(id="any-run", tree_id="owned-tree", owner_id="owner")
    engine.plan.return_value = AuditRun(
        id="any-run", tree_id="owned-tree", owner_id="owner", status="completed"
    )
    response = client.post(
        "/v1/internal/audits/any-run/work",
        headers={"X-Evidence-Worker-Token": "internal-worker-credential"},
    )
    assert response.status_code == 200
    engine.plan.assert_called_once_with("any-run")
    dispatcher.dispatch.assert_not_called()
    auth.auth.verify_id_token.assert_not_called()
    auth.app_check.verify_token.assert_not_called()


def test_health_stays_public_with_strict_browser_auth(production):
    assert client.get("/health").status_code == 200

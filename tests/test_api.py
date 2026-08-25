from fastapi.testclient import TestClient

from evidence_agent.main import app

client = TestClient(app)


def test_health_and_agent_card():
    assert client.get("/health").status_code == 200
    card = client.get("/.well-known/agent.json").json()
    assert card["skills"][0]["id"] == "audit_family_tree_evidence"


def test_start_requires_matching_owner():
    body = {"tree": {"id": "t-api", "owner_id": "owner", "people": [], "relationships": []}}
    assert client.post("/v1/audits", json=body).status_code == 401
    assert (
        client.post(
            "/v1/audits", json=body, headers={"X-Rootstory-User": "someone-else"}
        ).status_code
        == 403
    )


def test_start_and_read_audit():
    body = {
        "tree": {
            "id": "t-api-owned",
            "owner_id": "owner",
            "people": [{"id": "p1", "name": "Test Person"}],
            "relationships": [],
        }
    }
    response = client.post("/v1/audits", json=body, headers={"X-Rootstory-User": "owner"})
    assert response.status_code == 202
    run_id = response.json()["id"]
    result = client.get(f"/v1/audits/{run_id}", headers={"X-Rootstory-User": "owner"})
    assert result.status_code == 200
    assert result.json()["status"] == "completed"

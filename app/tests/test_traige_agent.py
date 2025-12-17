from fastapi.testclient import TestClient
from app.triage_agent import app

client = TestClient(app)

def post(payload):
    return client.post("/triage/invoke", json=payload)


def test_basic_flow():
    payload = {"ticket_text": "Order ORD1001 arrived damaged"}
    res = post(payload).json()

    assert "reply" in res
    assert "issue_type" in res


def test_update_status_issue():
    payload = {
        "ticket_text": "please update order ORD1003 to delivered",
        "order_id": "ORD1003",
        "query": "mark this as delivered"
    }
    res = post(payload).json()

    assert res["issue_type"] in ["update_status", "general_question"]


def test_fetch_order():
    payload = {
        "ticket_text": "check status for order ORD1002",
        "order_id": "ORD1002"
    }
    res = post(payload).json()

    assert res["order_id"] == "ORD1002"


def test_missing_order():
    payload = {"ticket_text": "check status for order ORD9999"}
    res = post(payload)

    assert res.status_code in [200, 404]


def test_general_question():
    payload = {"ticket_text": "Do you ship internationally?"}
    res = post(payload).json()

    assert res["issue_type"] in ["general_question", None]


def test_response_structure():
    payload = {"ticket_text": "Order ORD1001 arrived damaged"}
    res = post(payload).json()

    assert set(res.keys()) == {
        "reply",
        "issue_type",
        "order_id",
        "evidence",
        "recommendation"
    }

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from message_bus import MessageBus
from agents.engineer_agent import EngineerAgent

FAKE_SPEC = {
    "value_proposition": "GigHub connects founders with freelancers for 48-hour micro-tasks.",
    "personas": [{"name": "Alice", "role": "Founder", "pain_point": "No devs"}],
    "features": [{"name": "Task Board", "description": "Browse tasks", "priority": 1}],
    "user_stories": [{"as_a": "founder", "i_want": "post tasks", "so_that": "get work done"}]
}
FAKE_HTML = "<html><head><title>GigHub</title></head><body><h1>GigHub</h1></body></html>"

def _mock_response(status_code, json_data):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock

def test_engineer_sends_pr_url_to_ceo():
    bus = MessageBus()
    bus.send("ceo", "engineer", "task", {"product_spec": FAKE_SPEC})
    agent = EngineerAgent(bus)

    sha_resp = _mock_response(200, {"object": {"sha": "abc123"}})
    branch_resp = _mock_response(201, {})
    file_resp = _mock_response(201, {})
    issue_resp = _mock_response(201, {"html_url": "https://github.com/user/repo/issues/1", "number": 1})
    pr_resp = _mock_response(201, {"html_url": "https://github.com/user/repo/pull/1"})

    with patch("agents.engineer_agent.call_llm", return_value=FAKE_HTML), \
         patch("agents.engineer_agent.requests.get", return_value=sha_resp), \
         patch("agents.engineer_agent.requests.post", side_effect=[branch_resp, issue_resp, pr_resp]), \
         patch("agents.engineer_agent.requests.put", return_value=file_resp):
        agent.run()

    messages = bus.receive("ceo")
    assert len(messages) == 1
    msg = messages[0]
    assert msg["message_type"] == "result"
    assert msg["from_agent"] == "engineer"
    assert msg["payload"]["pr_url"] == "https://github.com/user/repo/pull/1"
    assert msg["payload"]["issue_url"] == "https://github.com/user/repo/issues/1"
    assert "html_content" in msg["payload"]

def test_engineer_does_nothing_with_no_messages():
    bus = MessageBus()
    agent = EngineerAgent(bus)
    agent.run()
    assert bus.receive("ceo") == []

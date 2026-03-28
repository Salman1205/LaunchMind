import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from message_bus import MessageBus
from agents.qa_agent import QAAgent

FAKE_HTML = "<html><h1>GigHub</h1><p>Connect with freelancers</p></html>"
FAKE_COPY = {
    "tagline": "Get it done in 48 hours.",
    "description": "GigHub is fast.",
    "cold_email_subject": "Ship faster",
    "cold_email_body": "Hi, try GigHub.",
    "twitter": "GigHub rocks",
    "linkedin": "GigHub is great",
    "instagram": "GigHub 🚀"
}
FAKE_SPEC = {"value_proposition": "GigHub connects founders with freelancers."}
FAKE_REVIEW = json.dumps({
    "html_verdict": "pass",
    "html_issues": ["Missing meta description", "CTA button not prominent enough"],
    "copy_verdict": "pass",
    "copy_issues": ["Cold email lacks specific CTA"],
    "overall_verdict": "pass"
})

def test_qa_agent_returns_verdict():
    bus = MessageBus()
    bus.send("ceo", "qa", "task", {
        "html_content": FAKE_HTML,
        "copy": FAKE_COPY,
        "product_spec": FAKE_SPEC,
        "pr_url": "https://github.com/user/repo/pull/1",
    })
    agent = QAAgent(bus)

    mock_pr_resp = MagicMock()
    mock_pr_resp.status_code = 200
    mock_pr_resp.json.return_value = {"head": {"sha": "deadbeef"}}
    mock_pr_resp.raise_for_status = MagicMock()

    mock_comment_resp = MagicMock()
    mock_comment_resp.status_code = 201
    mock_comment_resp.raise_for_status = MagicMock()

    with patch("agents.qa_agent.call_llm", return_value=FAKE_REVIEW), \
         patch("agents.qa_agent.requests.get", return_value=mock_pr_resp), \
         patch("agents.qa_agent.requests.post", return_value=mock_comment_resp):
        agent.run()

    messages = bus.receive("ceo")
    assert len(messages) == 1
    msg = messages[0]
    assert msg["message_type"] == "result"
    assert msg["from_agent"] == "qa"
    report = msg["payload"]["review_report"]
    assert "overall_verdict" in report
    assert report["overall_verdict"] in ("pass", "fail")
    assert "html_issues" in report
    assert "copy_issues" in report

def test_qa_agent_does_nothing_with_no_messages():
    bus = MessageBus()
    agent = QAAgent(bus)
    agent.run()
    assert bus.receive("ceo") == []

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from message_bus import MessageBus
from agents.marketing_agent import MarketingAgent

FAKE_SPEC = {
    "value_proposition": "GigHub connects founders with freelancers for 48-hour micro-tasks.",
    "personas": [{"name": "Alice", "role": "Founder", "pain_point": "No devs"}],
    "features": [{"name": "Task Board", "description": "Browse tasks", "priority": 1}],
    "user_stories": []
}
FAKE_COPY = json.dumps({
    "tagline": "Get it done in 48 hours.",
    "description": "GigHub is the fastest way to ship small features.",
    "cold_email_subject": "Ship faster with GigHub",
    "cold_email_body": "Hi, I wanted to introduce GigHub.",
    "twitter": "Introducing GigHub! #startup",
    "linkedin": "Excited to announce GigHub.",
    "instagram": "Your idea, shipped in 48 hours. 💻"
})

def test_marketing_agent_sends_result_to_ceo():
    bus = MessageBus()
    bus.send("ceo", "marketing", "task", {
        "product_spec": FAKE_SPEC,
        "pr_url": "https://github.com/user/repo/pull/1"
    })
    agent = MarketingAgent(bus)

    mock_sg_instance = MagicMock()
    mock_sg_instance.client.mail.send.post.return_value.status_code = 202
    mock_sg_class = MagicMock(return_value=mock_sg_instance)

    mock_slack_instance = MagicMock()
    mock_slack_instance.chat_postMessage.return_value = {"ok": True}
    mock_slack_class = MagicMock(return_value=mock_slack_instance)

    with patch("agents.marketing_agent.call_llm", return_value=FAKE_COPY), \
         patch("agents.marketing_agent.SendGridAPIClient", mock_sg_class), \
         patch("agents.marketing_agent.WebClient", mock_slack_class):
        agent.run()

    messages = bus.receive("ceo")
    assert len(messages) == 1
    msg = messages[0]
    assert msg["message_type"] == "result"
    assert msg["from_agent"] == "marketing"
    copy = msg["payload"]["copy"]
    assert "tagline" in copy
    assert "cold_email_subject" in copy
    assert "twitter" in copy

def test_marketing_agent_handles_revision_request():
    bus = MessageBus()
    bus.send("ceo", "marketing", "revision_request", {
        "product_spec": FAKE_SPEC,
        "pr_url": "https://github.com/user/repo/pull/1",
        "feedback": "Make the tagline punchier"
    })
    agent = MarketingAgent(bus)

    mock_sg_instance = MagicMock()
    mock_sg_instance.client.mail.send.post.return_value.status_code = 202
    mock_sg_class = MagicMock(return_value=mock_sg_instance)
    mock_slack_instance = MagicMock()
    mock_slack_class = MagicMock(return_value=mock_slack_instance)

    with patch("agents.marketing_agent.call_llm", return_value=FAKE_COPY), \
         patch("agents.marketing_agent.SendGridAPIClient", mock_sg_class), \
         patch("agents.marketing_agent.WebClient", mock_slack_class):
        agent.run()

    messages = bus.receive("ceo")
    assert len(messages) == 1

def test_marketing_agent_does_nothing_with_no_messages():
    bus = MessageBus()
    agent = MarketingAgent(bus)
    agent.run()
    assert bus.receive("ceo") == []

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch
from message_bus import MessageBus
from agents.product_agent import ProductAgent

FAKE_LLM_SPEC = json.dumps({
    "value_proposition": "GigHub connects founders with freelancers for 48-hour micro-tasks.",
    "personas": [
        {"name": "Alice", "role": "Startup Founder", "pain_point": "Can't afford full-time devs for small tasks"},
        {"name": "Bob", "role": "Freelance Developer", "pain_point": "Needs flexible short-term paid work"}
    ],
    "features": [
        {"name": "Task Board", "description": "Browse open micro-tasks", "priority": 1},
        {"name": "Instant Pay", "description": "Payment on task approval", "priority": 2},
        {"name": "Skill Matching", "description": "Filter tasks by tech stack", "priority": 3},
        {"name": "48h Deadline Timer", "description": "Auto-expire unclaimed tasks", "priority": 4},
        {"name": "Reputation Score", "description": "Track completion rate", "priority": 5}
    ],
    "user_stories": [
        {"as_a": "founder", "i_want": "to post a task with a budget", "so_that": "I get it done without hiring full-time"},
        {"as_a": "developer", "i_want": "to browse tasks by language", "so_that": "I find work matching my skills"},
        {"as_a": "founder", "i_want": "to approve completed work", "so_that": "payment is released automatically"}
    ]
})


def test_product_agent_returns_spec():
    bus = MessageBus()
    bus.send("ceo", "product", "task", {
        "idea": "GigHub micro-task platform",
        "focus": "Define core user personas and top 5 features"
    })
    agent = ProductAgent(bus)
    with patch("agents.product_agent.call_llm", return_value=FAKE_LLM_SPEC):
        agent.run()
    ceo_messages = bus.receive("ceo")
    assert len(ceo_messages) == 1
    msg = ceo_messages[0]
    assert msg["message_type"] == "result"
    assert msg["from_agent"] == "product"
    spec = msg["payload"]["product_spec"]
    assert "value_proposition" in spec
    assert len(spec["personas"]) >= 2
    assert len(spec["features"]) >= 5
    assert len(spec["user_stories"]) >= 3


def test_product_agent_handles_revision_request():
    bus = MessageBus()
    bus.send("ceo", "product", "revision_request", {
        "idea": "GigHub micro-task platform",
        "focus": "Revise based on feedback",
        "feedback": "Add more specific pain points"
    })
    agent = ProductAgent(bus)
    with patch("agents.product_agent.call_llm", return_value=FAKE_LLM_SPEC):
        agent.run()
    ceo_messages = bus.receive("ceo")
    assert len(ceo_messages) == 1


def test_product_agent_does_nothing_with_no_messages():
    bus = MessageBus()
    agent = ProductAgent(bus)
    with patch("agents.product_agent.call_llm", return_value=FAKE_LLM_SPEC):
        agent.run()
    assert bus.receive("ceo") == []

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from message_bus import MessageBus
from agents.ceo_agent import CEOAgent

FAKE_TASKS = json.dumps({
    "product_task": {"idea": "GigHub micro-task platform", "focus": "Define core personas and top 5 features"},
    "engineer_task": {"focus": "Build a modern landing page"},
    "marketing_task": {"focus": "Write compelling growth copy"}
})
FAKE_REVIEW_OK = json.dumps({"verdict": "acceptable", "feedback": ""})
FAKE_REVIEW_FAIL = json.dumps({"verdict": "needs_revision", "feedback": "Missing specific pain points in personas."})
FAKE_QA_DECISION = json.dumps({
    "engineer_needs_revision": False,
    "marketing_needs_revision": False,
    "engineer_feedback": "",
    "marketing_feedback": ""
})

FAKE_SPEC = {
    "value_proposition": "GigHub connects founders with freelancers.",
    "personas": [{"name": "Alice", "role": "Founder", "pain_point": "No devs"}],
    "features": [{"name": "Task Board", "description": "Browse tasks", "priority": 1}],
    "user_stories": []
}

def test_ceo_sends_task_to_product():
    bus = MessageBus()
    agent = CEOAgent(bus, startup_idea="GigHub micro-task platform")
    with patch("agents.ceo_agent.call_llm", return_value=FAKE_TASKS):
        agent.decompose_and_send()
    product_msgs = bus.receive("product")
    assert len(product_msgs) == 1
    assert product_msgs[0]["message_type"] == "task"
    assert product_msgs[0]["from_agent"] == "ceo"

def test_ceo_review_acceptable_no_revision():
    bus = MessageBus()
    agent = CEOAgent(bus, startup_idea="GigHub")
    with patch("agents.ceo_agent.call_llm", return_value=FAKE_REVIEW_OK):
        result = agent.review_product_spec(FAKE_SPEC)
    assert result["verdict"] == "acceptable"
    assert bus.receive("product") == []

def test_ceo_review_fail_sends_revision_request():
    bus = MessageBus()
    agent = CEOAgent(bus, startup_idea="GigHub")
    with patch("agents.ceo_agent.call_llm", return_value=FAKE_REVIEW_FAIL):
        result = agent.review_product_spec(FAKE_SPEC)
    assert result["verdict"] == "needs_revision"
    revision_msgs = bus.receive("product")
    assert len(revision_msgs) == 1
    assert revision_msgs[0]["message_type"] == "revision_request"
    assert revision_msgs[0]["payload"]["feedback"] == "Missing specific pain points in personas."

def test_ceo_dispatches_to_engineer_and_marketing():
    bus = MessageBus()
    agent = CEOAgent(bus, startup_idea="GigHub")
    agent.dispatch_to_engineer_and_marketing(FAKE_SPEC, pr_url="")
    eng_msgs = bus.receive("engineer")
    mkt_msgs = bus.receive("marketing")
    assert len(eng_msgs) == 1
    assert eng_msgs[0]["message_type"] == "task"
    assert len(mkt_msgs) == 1
    assert mkt_msgs[0]["message_type"] == "task"

def test_ceo_qa_pass_no_revision():
    bus = MessageBus()
    agent = CEOAgent(bus, startup_idea="GigHub")
    report = {"overall_verdict": "pass", "html_issues": [], "copy_issues": []}
    with patch("agents.ceo_agent.call_llm", return_value=FAKE_QA_DECISION):
        decision = agent.review_qa_report(report, "<html/>", {}, "https://github.com/u/r/pull/1")
    assert not decision["engineer_needs_revision"]
    assert not decision["marketing_needs_revision"]
    assert bus.receive("engineer") == []
    assert bus.receive("marketing") == []

def test_ceo_decision_log_records_actions():
    bus = MessageBus()
    agent = CEOAgent(bus, startup_idea="GigHub")
    with patch("agents.ceo_agent.call_llm", return_value=FAKE_TASKS):
        agent.decompose_and_send()
    log = agent.get_decision_log()
    assert len(log) >= 1
    assert any("GigHub" in entry for entry in log)

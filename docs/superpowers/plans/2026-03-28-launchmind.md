# LaunchMind Multi-Agent System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 5-agent MAS that autonomously receives a startup idea and produces real GitHub PRs, Slack messages, and emails — with a CEO feedback loop that can request revisions.

**Architecture:** A shared-dict message bus routes structured JSON messages between agents. The CEO orchestrates by calling sub-agents sequentially, reviewing their outputs with an LLM, and optionally sending `revision_request` messages before proceeding. All platform actions (GitHub, Slack, SendGrid) are real.

**Tech Stack:** Python 3.11+, Anthropic Claude API (`claude-sonnet-4-5-20251001`), GitHub REST API, Slack Web API (Block Kit), SendGrid, `python-dotenv`, `requests`, `slack_sdk`, `sendgrid`

---

## Startup Idea (fill in before starting)

Pick any concrete idea. Example used throughout this plan:
> **GigHub** — A platform where startup founders post small, paid coding micro-tasks and freelance developers claim and complete them in 48 hours.

Replace "GigHub" and its description with your group's idea in `config.py`.

---

## File Structure

```
launchmind/
├── agents/
│   ├── __init__.py
│   ├── ceo_agent.py          # Orchestrator: decomposes idea, reviews outputs, runs feedback loop
│   ├── product_agent.py      # Generates product spec JSON
│   ├── engineer_agent.py     # Generates HTML, commits to GitHub, opens PR
│   ├── marketing_agent.py    # Generates copy, sends email, posts to Slack
│   └── qa_agent.py           # Reviews HTML + copy, posts PR review comments
├── message_bus.py            # Shared dict bus with append/read/history
├── llm_client.py             # Thin wrapper around Anthropic API
├── config.py                 # Loads .env, exposes constants
├── main.py                   # Entry point — runs full pipeline
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Task 1: Project Bootstrap

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `config.py`
- Create: `agents/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
anthropic>=0.25.0
python-dotenv>=1.0.0
requests>=2.31.0
slack_sdk>=3.27.0
sendgrid>=6.11.0
```

- [ ] **Step 2: Create `.env.example`**

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
GITHUB_TOKEN=ghp_your_token_here
GITHUB_REPO=your-username/launchmind-your-group
SLACK_BOT_TOKEN=xoxb-your-token-here
SLACK_CHANNEL=#launches
SENDGRID_API_KEY=SG.your-key-here
SENDGRID_FROM_EMAIL=verified@yourdomain.com
EMAIL_TO=your-test-inbox@gmail.com
```

- [ ] **Step 3: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
*.pyo
.DS_Store
```

- [ ] **Step 4: Create `config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]          # e.g. "alice/launchmind-team1"
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#launches")
SENDGRID_API_KEY = os.environ["SENDGRID_API_KEY"]
SENDGRID_FROM_EMAIL = os.environ["SENDGRID_FROM_EMAIL"]
EMAIL_TO = os.environ["EMAIL_TO"]

STARTUP_IDEA = (
    "GigHub — A platform where startup founders post small, paid coding micro-tasks "
    "and freelance developers claim and complete them in 48 hours."
)
```

- [ ] **Step 5: Create `agents/__init__.py`** (empty file)

```python
# agents package
```

- [ ] **Step 6: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without errors.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example .gitignore config.py agents/__init__.py
git commit -m "chore: bootstrap project structure and dependencies"
```

---

## Task 2: Message Bus

**Files:**
- Create: `message_bus.py`
- Create: `tests/test_message_bus.py`

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` (empty), then `tests/test_message_bus.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from message_bus import MessageBus

def test_send_and_receive():
    bus = MessageBus()
    bus.send("ceo", "product", "task", {"idea": "test idea"})
    messages = bus.receive("product")
    assert len(messages) == 1
    msg = messages[0]
    assert msg["from_agent"] == "ceo"
    assert msg["to_agent"] == "product"
    assert msg["message_type"] == "task"
    assert msg["payload"]["idea"] == "test idea"
    assert "message_id" in msg
    assert "timestamp" in msg

def test_multiple_messages():
    bus = MessageBus()
    bus.send("ceo", "product", "task", {"idea": "a"})
    bus.send("product", "ceo", "result", {"spec": "b"})
    assert len(bus.receive("product")) == 1
    assert len(bus.receive("ceo")) == 1

def test_history_contains_all_messages():
    bus = MessageBus()
    bus.send("ceo", "product", "task", {"idea": "x"})
    bus.send("ceo", "engineer", "task", {"spec": "y"})
    assert len(bus.get_history()) == 2

def test_parent_message_id():
    bus = MessageBus()
    msg_id = bus.send("ceo", "product", "task", {"idea": "z"})
    reply_id = bus.send("product", "ceo", "result", {}, parent_message_id=msg_id)
    history = bus.get_history()
    reply = next(m for m in history if m["message_id"] == reply_id)
    assert reply["parent_message_id"] == msg_id
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_message_bus.py -v
```

Expected: `ImportError: cannot import name 'MessageBus' from 'message_bus'`

- [ ] **Step 3: Implement `message_bus.py`**

```python
import uuid
from datetime import datetime, timezone
from typing import Optional


class MessageBus:
    """
    Shared in-memory message bus for agent communication.
    Agents read from their own inbox; all messages are also in _history.
    """

    def __init__(self):
        self._inboxes: dict[str, list[dict]] = {}
        self._history: list[dict] = []

    def send(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        payload: dict,
        parent_message_id: Optional[str] = None,
    ) -> str:
        """Enqueue a message and return its message_id."""
        message_id = str(uuid.uuid4())
        message = {
            "message_id": message_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "message_type": message_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "parent_message_id": parent_message_id,
        }
        self._inboxes.setdefault(to_agent, []).append(message)
        self._history.append(message)
        print(f"[BUS] {from_agent} → {to_agent} [{message_type}] id={message_id[:8]}")
        return message_id

    def receive(self, agent_name: str) -> list[dict]:
        """Return and clear all messages waiting for agent_name."""
        messages = self._inboxes.get(agent_name, [])
        self._inboxes[agent_name] = []
        return messages

    def get_history(self) -> list[dict]:
        """Return all messages ever sent (for logging and demo)."""
        return list(self._history)

    def print_history(self) -> None:
        """Pretty-print the full message log."""
        print("\n=== FULL MESSAGE HISTORY ===")
        for msg in self._history:
            pid = msg.get("parent_message_id") or "-"
            print(
                f"  [{msg['timestamp'][:19]}] "
                f"{msg['from_agent']:12} → {msg['to_agent']:12} "
                f"[{msg['message_type']:20}] "
                f"id={msg['message_id'][:8]} parent={pid[:8] if pid != '-' else '-'}"
            )
        print("============================\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_message_bus.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add message_bus.py tests/
git commit -m "feat: implement shared message bus with full history"
```

---

## Task 3: LLM Client

**Files:**
- Create: `llm_client.py`
- Create: `tests/test_llm_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_client.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from llm_client import call_llm

def test_call_llm_returns_string():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello world")]
    with patch("llm_client.anthropic_client.messages.create", return_value=mock_response):
        result = call_llm("You are helpful.", "Say hello.")
    assert result == "Hello world"

def test_call_llm_passes_prompts():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]
    with patch("llm_client.anthropic_client.messages.create", return_value=mock_response) as mock_create:
        call_llm("system prompt", "user prompt")
        call_args = mock_create.call_args
        assert call_args.kwargs["system"] == "system prompt"
        assert call_args.kwargs["messages"][0]["content"] == "user prompt"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_llm_client.py -v
```

Expected: `ImportError: No module named 'llm_client'`

- [ ] **Step 3: Implement `llm_client.py`**

```python
import anthropic
from config import ANTHROPIC_API_KEY

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MODEL = "claude-sonnet-4-5-20251001"


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> str:
    """
    Call the Claude API and return the text response.
    Raises anthropic.APIError on failure — callers should handle this.
    """
    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_llm_client.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add llm_client.py tests/test_llm_client.py
git commit -m "feat: add LLM client wrapper for Anthropic API"
```

---

## Task 4: Product Agent

**Files:**
- Create: `agents/product_agent.py`
- Create: `tests/test_product_agent.py`

The Product Agent receives a `task` message from CEO, calls the LLM to generate a product spec, and returns a `result` message.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_product_agent.py
import sys, os, json
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

def test_product_agent_does_nothing_with_no_messages():
    bus = MessageBus()
    agent = ProductAgent(bus)
    with patch("agents.product_agent.call_llm", return_value=FAKE_LLM_SPEC):
        agent.run()  # should not crash
    assert bus.receive("ceo") == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_product_agent.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `agents/product_agent.py`**

```python
import json
from message_bus import MessageBus
from llm_client import call_llm

SYSTEM_PROMPT = """You are a senior product manager. Given a startup idea, produce a detailed product specification as a JSON object.

The JSON must have exactly these fields:
- value_proposition: string (one sentence)
- personas: array of objects with keys: name, role, pain_point (at least 2 personas)
- features: array of objects with keys: name, description, priority (1=highest, at least 5 features)
- user_stories: array of objects with keys: as_a, i_want, so_that (exactly 3 stories)

Respond with ONLY valid JSON. No markdown, no explanation, no code fences."""


class ProductAgent:
    def __init__(self, bus: MessageBus):
        self.bus = bus

    def run(self):
        messages = self.bus.receive("product")
        for msg in messages:
            if msg["message_type"] not in ("task", "revision_request"):
                continue
            print(f"\n[PRODUCT] Processing message type={msg['message_type']}")
            payload = msg["payload"]
            idea = payload.get("idea", "")
            focus = payload.get("focus", "")
            feedback = payload.get("feedback", "")

            user_prompt = f"Startup idea: {idea}\nFocus: {focus}"
            if feedback:
                user_prompt += f"\nPrevious feedback to address: {feedback}"

            raw = call_llm(SYSTEM_PROMPT, user_prompt)
            print(f"[PRODUCT] Raw LLM output:\n{raw[:300]}...")

            try:
                spec = json.loads(raw)
            except json.JSONDecodeError:
                # Strip markdown fences if present
                cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                spec = json.loads(cleaned)

            print(f"[PRODUCT] Spec generated: {spec['value_proposition']}")
            self.bus.send(
                from_agent="product",
                to_agent="ceo",
                message_type="result",
                payload={"product_spec": spec},
                parent_message_id=msg["message_id"],
            )
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_product_agent.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/product_agent.py tests/test_product_agent.py
git commit -m "feat: implement Product agent with LLM spec generation"
```

---

## Task 5: Engineer Agent (GitHub Integration)

**Files:**
- Create: `agents/engineer_agent.py`
- Create: `tests/test_engineer_agent.py`

The Engineer Agent receives the product spec, generates an HTML landing page, creates a GitHub branch, commits the file, opens a PR, and reports back to CEO.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engineer_agent.py
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

def _make_mock_response(status_code, json_data):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock

def test_engineer_sends_pr_url_to_ceo():
    bus = MessageBus()
    bus.send("ceo", "engineer", "task", {"product_spec": FAKE_SPEC})
    agent = EngineerAgent(bus)

    sha_response = _make_mock_response(200, {"object": {"sha": "abc123"}})
    branch_response = _make_mock_response(201, {})
    file_response = _make_mock_response(201, {})
    issue_response = _make_mock_response(201, {"html_url": "https://github.com/user/repo/issues/1", "number": 1})
    pr_response = _make_mock_response(201, {"html_url": "https://github.com/user/repo/pull/1"})

    with patch("agents.engineer_agent.call_llm", return_value=FAKE_HTML), \
         patch("agents.engineer_agent.requests.get", return_value=sha_response), \
         patch("agents.engineer_agent.requests.post", side_effect=[branch_response, issue_response, pr_response]), \
         patch("agents.engineer_agent.requests.put", return_value=file_response):
        agent.run()

    messages = bus.receive("ceo")
    assert len(messages) == 1
    msg = messages[0]
    assert msg["message_type"] == "result"
    assert "pr_url" in msg["payload"]
    assert "issue_url" in msg["payload"]
    assert "html_content" in msg["payload"]
    assert msg["payload"]["pr_url"] == "https://github.com/user/repo/pull/1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_engineer_agent.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `agents/engineer_agent.py`**

```python
import base64
import os
import requests
from message_bus import MessageBus
from llm_client import call_llm
from config import GITHUB_TOKEN, GITHUB_REPO

GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
BRANCH_NAME = "agent-landing-page"

HTML_SYSTEM_PROMPT = """You are a frontend developer. Generate a complete, working HTML landing page for a startup.

Include:
- A compelling headline (the product name)
- A subheadline (the value proposition)
- A features section listing all features
- A call-to-action button ("Get Early Access")
- Inline CSS styling (modern, clean, professional)

Respond with ONLY the raw HTML. No markdown. No explanation."""

PR_BODY_PROMPT = """Write a GitHub pull request description for a landing page commit.
Mention the product name, what the page includes, and that it was generated by the EngineerAgent.
Keep it under 150 words."""


class EngineerAgent:
    def __init__(self, bus: MessageBus):
        self.bus = bus

    def run(self):
        messages = self.bus.receive("engineer")
        for msg in messages:
            if msg["message_type"] not in ("task", "revision_request"):
                continue
            print(f"\n[ENGINEER] Processing message type={msg['message_type']}")
            spec = msg["payload"]["product_spec"]
            feedback = msg["payload"].get("feedback", "")

            html = self._generate_html(spec, feedback)
            issue_url, issue_number = self._create_github_issue(spec)
            pr_url = self._commit_and_open_pr(html, spec, issue_number)

            print(f"[ENGINEER] PR opened: {pr_url}")
            print(f"[ENGINEER] Issue created: {issue_url}")

            self.bus.send(
                from_agent="engineer",
                to_agent="ceo",
                message_type="result",
                payload={
                    "pr_url": pr_url,
                    "issue_url": issue_url,
                    "html_content": html,
                    "branch": BRANCH_NAME,
                },
                parent_message_id=msg["message_id"],
            )

    def _generate_html(self, spec: dict, feedback: str = "") -> str:
        user_prompt = (
            f"Product name extracted from value proposition: {spec['value_proposition']}\n"
            f"Features: {spec['features']}\n"
            f"Personas: {spec['personas']}\n"
        )
        if feedback:
            user_prompt += f"\nFeedback to address: {feedback}"
        html = call_llm(HTML_SYSTEM_PROMPT, user_prompt, max_tokens=3000)
        # Strip markdown fences if LLM wraps in them
        if html.strip().startswith("```"):
            html = html.strip().removeprefix("```html").removeprefix("```").removesuffix("```").strip()
        return html

    def _create_github_issue(self, spec: dict) -> tuple[str, int]:
        issue_body = (
            f"## Initial Landing Page\n\n"
            f"**Value Proposition:** {spec['value_proposition']}\n\n"
            f"**Features to showcase:**\n"
            + "\n".join(f"- {f['name']}: {f['description']}" for f in spec['features'])
            + "\n\n_Created by EngineerAgent_"
        )
        r = requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/issues",
            headers=GITHUB_HEADERS,
            json={"title": "Initial landing page", "body": issue_body},
        )
        r.raise_for_status()
        data = r.json()
        return data["html_url"], data["number"]

    def _get_main_sha(self) -> str:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/git/ref/heads/main",
            headers=GITHUB_HEADERS,
        )
        r.raise_for_status()
        return r.json()["object"]["sha"]

    def _commit_and_open_pr(self, html: str, spec: dict, issue_number: int) -> str:
        sha = self._get_main_sha()

        # Create branch
        requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/git/refs",
            headers=GITHUB_HEADERS,
            json={"ref": f"refs/heads/{BRANCH_NAME}", "sha": sha},
        )
        # If branch already exists, the 422 is fine — we continue

        # Commit file
        encoded = base64.b64encode(html.encode()).decode()
        requests.put(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/index.html",
            headers=GITHUB_HEADERS,
            json={
                "message": "feat: add landing page generated by EngineerAgent",
                "content": encoded,
                "branch": BRANCH_NAME,
                "author": {"name": "EngineerAgent", "email": "agent@launchmind.ai"},
            },
        )

        # Open PR
        pr_body = call_llm(
            "You write concise GitHub PR descriptions.",
            f"{PR_BODY_PROMPT}\nProduct: {spec['value_proposition']}\nCloses #{issue_number}",
            max_tokens=200,
        )
        r = requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/pulls",
            headers=GITHUB_HEADERS,
            json={
                "title": "Initial landing page",
                "body": pr_body + f"\n\nCloses #{issue_number}",
                "head": BRANCH_NAME,
                "base": "main",
            },
        )
        r.raise_for_status()
        return r.json()["html_url"]
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_engineer_agent.py -v
```

Expected: 1 test PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/engineer_agent.py tests/test_engineer_agent.py
git commit -m "feat: implement Engineer agent with GitHub PR integration"
```

---

## Task 6: Marketing Agent (Slack + SendGrid)

**Files:**
- Create: `agents/marketing_agent.py`
- Create: `tests/test_marketing_agent.py`

The Marketing Agent receives the product spec + PR URL, generates copy with an LLM, sends a real email, and posts a Slack Block Kit message.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_marketing_agent.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
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
    "description": "GigHub is the fastest way to ship small features. Post a task, pay on approval.",
    "cold_email_subject": "Ship faster with GigHub",
    "cold_email_body": "Hi, I wanted to introduce GigHub — a platform built for founders like you.",
    "twitter": "Introducing GigHub 🚀 Post micro-tasks, get them done in 48h. #startup #buildinpublic",
    "linkedin": "Excited to announce GigHub — where startup founders meet talented freelancers for quick wins.",
    "instagram": "Your idea, shipped in 48 hours. Meet GigHub. 💻⚡"
})

def test_marketing_agent_sends_result_to_ceo():
    bus = MessageBus()
    bus.send("ceo", "marketing", "task", {
        "product_spec": FAKE_SPEC,
        "pr_url": "https://github.com/user/repo/pull/1"
    })
    agent = MarketingAgent(bus)

    mock_sg = MagicMock()
    mock_sg.return_value.client.mail.send.post.return_value.status_code = 202

    mock_slack = MagicMock()
    mock_slack.return_value.chat_postMessage.return_value = {"ok": True}

    with patch("agents.marketing_agent.call_llm", return_value=FAKE_COPY), \
         patch("agents.marketing_agent.SendGridAPIClient", mock_sg), \
         patch("agents.marketing_agent.WebClient", mock_slack):
        agent.run()

    messages = bus.receive("ceo")
    assert len(messages) == 1
    msg = messages[0]
    assert msg["message_type"] == "result"
    copy = msg["payload"]["copy"]
    assert "tagline" in copy
    assert "cold_email_subject" in copy
    assert "twitter" in copy
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_marketing_agent.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `agents/marketing_agent.py`**

```python
import json
from slack_sdk import WebClient
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from message_bus import MessageBus
from llm_client import call_llm
from config import SLACK_BOT_TOKEN, SLACK_CHANNEL, SENDGRID_API_KEY, SENDGRID_FROM_EMAIL, EMAIL_TO

COPY_SYSTEM_PROMPT = """You are a growth marketer. Given a product spec, generate marketing copy as JSON.

The JSON must have exactly these fields:
- tagline: string (under 10 words, punchy)
- description: string (2-3 sentences for a landing page)
- cold_email_subject: string (email subject line)
- cold_email_body: string (cold outreach email body, 3-4 paragraphs, ends with a CTA)
- twitter: string (tweet under 280 chars)
- linkedin: string (LinkedIn post, 2-3 sentences, professional)
- instagram: string (Instagram caption with emojis)

Respond with ONLY valid JSON. No markdown, no explanation."""


class MarketingAgent:
    def __init__(self, bus: MessageBus):
        self.bus = bus

    def run(self):
        messages = self.bus.receive("marketing")
        for msg in messages:
            if msg["message_type"] not in ("task", "revision_request"):
                continue
            print(f"\n[MARKETING] Processing message type={msg['message_type']}")
            payload = msg["payload"]
            spec = payload["product_spec"]
            pr_url = payload.get("pr_url", "")
            feedback = payload.get("feedback", "")

            copy = self._generate_copy(spec, feedback)
            self._send_email(copy)
            self._post_to_slack(copy, pr_url)

            self.bus.send(
                from_agent="marketing",
                to_agent="ceo",
                message_type="result",
                payload={"copy": copy},
                parent_message_id=msg["message_id"],
            )

    def _generate_copy(self, spec: dict, feedback: str = "") -> dict:
        user_prompt = (
            f"Value proposition: {spec['value_proposition']}\n"
            f"Personas: {spec['personas']}\n"
            f"Features: {spec['features']}\n"
        )
        if feedback:
            user_prompt += f"\nFeedback to address: {feedback}"
        raw = call_llm(COPY_SYSTEM_PROMPT, user_prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(cleaned)

    def _send_email(self, copy: dict) -> None:
        print(f"[MARKETING] Sending email: {copy['cold_email_subject']}")
        message = Mail(
            from_email=SENDGRID_FROM_EMAIL,
            to_emails=EMAIL_TO,
            subject=copy["cold_email_subject"],
            html_content=f"<p>{copy['cold_email_body'].replace(chr(10), '<br>')}</p>",
        )
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.client.mail.send.post(request_body=message.get())
        print(f"[MARKETING] Email sent, status={response.status_code}")

    def _post_to_slack(self, copy: dict, pr_url: str) -> None:
        print(f"[MARKETING] Posting to Slack channel {SLACK_CHANNEL}")
        client = WebClient(token=SLACK_BOT_TOKEN)
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"New Launch: {copy['tagline']}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": copy["description"]},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*GitHub PR:* <{pr_url}|View PR>"},
                    {"type": "mrkdwn", "text": "*Status:* Ready for review"},
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Twitter:* {copy['twitter']}"},
            },
        ]
        client.chat_postMessage(channel=SLACK_CHANNEL, blocks=blocks)
        print("[MARKETING] Slack message posted.")
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_marketing_agent.py -v
```

Expected: 1 test PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/marketing_agent.py tests/test_marketing_agent.py
git commit -m "feat: implement Marketing agent with Slack Block Kit and SendGrid email"
```

---

## Task 7: QA Agent (GitHub PR Review Comments)

**Files:**
- Create: `agents/qa_agent.py`
- Create: `tests/test_qa_agent.py`

The QA Agent reviews the Engineer's HTML and Marketing's copy, posts inline PR comments on GitHub, and returns a structured verdict to the CEO.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_qa_agent.py
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

    mock_pr_response = MagicMock()
    mock_pr_response.status_code = 200
    mock_pr_response.json.return_value = {"id": 42, "commit_id": "deadbeef"}

    with patch("agents.qa_agent.call_llm", return_value=FAKE_REVIEW), \
         patch("agents.qa_agent.requests.get", return_value=mock_pr_response), \
         patch("agents.qa_agent.requests.post", return_value=mock_pr_response):
        agent.run()

    messages = bus.receive("ceo")
    assert len(messages) == 1
    msg = messages[0]
    assert msg["message_type"] == "result"
    report = msg["payload"]["review_report"]
    assert "overall_verdict" in report
    assert report["overall_verdict"] in ("pass", "fail")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_qa_agent.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `agents/qa_agent.py`**

```python
import json
import requests
from message_bus import MessageBus
from llm_client import call_llm
from config import GITHUB_TOKEN, GITHUB_REPO

GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

QA_SYSTEM_PROMPT = """You are a QA reviewer for a software startup. Review the HTML landing page and marketing copy.

Return a JSON object with exactly these fields:
- html_verdict: "pass" or "fail"
- html_issues: array of specific issues found in the HTML (at least 2 items always)
- copy_verdict: "pass" or "fail"
- copy_issues: array of specific issues in the marketing copy (at least 1 item)
- overall_verdict: "pass" or "fail" (fail if either html or copy fails)

Be specific. Reference the value proposition when checking consistency.
Respond with ONLY valid JSON."""


class QAAgent:
    def __init__(self, bus: MessageBus):
        self.bus = bus

    def run(self):
        messages = self.bus.receive("qa")
        for msg in messages:
            if msg["message_type"] != "task":
                continue
            print(f"\n[QA] Running review...")
            payload = msg["payload"]
            html = payload["html_content"]
            copy = payload["copy"]
            spec = payload["product_spec"]
            pr_url = payload["pr_url"]

            report = self._review(html, copy, spec)
            self._post_pr_comments(pr_url, report)

            print(f"[QA] Overall verdict: {report['overall_verdict']}")
            self.bus.send(
                from_agent="qa",
                to_agent="ceo",
                message_type="result",
                payload={"review_report": report},
                parent_message_id=msg["message_id"],
            )

    def _review(self, html: str, copy: dict, spec: dict) -> dict:
        user_prompt = (
            f"Value proposition: {spec['value_proposition']}\n\n"
            f"HTML landing page:\n{html[:2000]}\n\n"
            f"Marketing copy:\n{json.dumps(copy, indent=2)}"
        )
        raw = call_llm(QA_SYSTEM_PROMPT, user_prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(cleaned)

    def _get_pr_details(self, pr_url: str) -> tuple[int, str]:
        """Extract PR number from URL and get the latest commit SHA."""
        pr_number = int(pr_url.rstrip("/").split("/")[-1])
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/pulls/{pr_number}",
            headers=GITHUB_HEADERS,
        )
        r.raise_for_status()
        commit_id = r.json()["head"]["sha"]
        return pr_number, commit_id

    def _post_pr_comments(self, pr_url: str, report: dict) -> None:
        try:
            pr_number, commit_id = self._get_pr_details(pr_url)
        except Exception as e:
            print(f"[QA] Could not fetch PR details: {e}")
            return

        issues = report.get("html_issues", []) + report.get("copy_issues", [])
        # Post at least 2 inline comments on the HTML file
        lines_to_comment = [5, 10]
        for i, issue in enumerate(issues[:2]):
            body = f"**QA Review:** {issue}"
            payload = {
                "body": body,
                "commit_id": commit_id,
                "path": "index.html",
                "line": lines_to_comment[i],
                "side": "RIGHT",
            }
            r = requests.post(
                f"https://api.github.com/repos/{GITHUB_REPO}/pulls/{pr_number}/comments",
                headers=GITHUB_HEADERS,
                json=payload,
            )
            if r.status_code in (200, 201):
                print(f"[QA] Posted PR comment: {issue[:60]}...")
            else:
                print(f"[QA] Failed to post comment (status {r.status_code}): {r.text[:100]}")
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_qa_agent.py -v
```

Expected: 1 test PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/qa_agent.py tests/test_qa_agent.py
git commit -m "feat: implement QA agent with GitHub PR review comments"
```

---

## Task 8: CEO Agent (Orchestrator + Feedback Loop)

**Files:**
- Create: `agents/ceo_agent.py`
- Create: `tests/test_ceo_agent.py`

This is the hardest agent. It:
1. Decomposes the startup idea into tasks (LLM call #1)
2. Sends tasks to Product, Engineer, Marketing agents
3. Reviews Product spec (LLM call #2) — if poor, sends `revision_request`
4. Collects Engineer + Marketing results
5. Sends Engineer + Marketing output to QA agent
6. If QA verdict is `fail`, sends `revision_request` to the relevant agent (LLM call #3)
7. Posts a final Slack summary

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ceo_agent.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, call
from message_bus import MessageBus
from agents.ceo_agent import CEOAgent

FAKE_TASKS = json.dumps({
    "product_task": {"idea": "GigHub micro-task platform", "focus": "Define core personas and top 5 features"},
    "engineer_task": {"focus": "Build a modern landing page"},
    "marketing_task": {"focus": "Write compelling growth copy"}
})
FAKE_REVIEW_OK = json.dumps({"verdict": "acceptable", "feedback": ""})
FAKE_REVIEW_FAIL = json.dumps({"verdict": "needs_revision", "feedback": "Missing specific pain points in personas."})

FAKE_SPEC = {
    "value_proposition": "GigHub connects founders with freelancers.",
    "personas": [{"name": "Alice", "role": "Founder", "pain_point": "No devs"}],
    "features": [{"name": "Task Board", "description": "Browse tasks", "priority": 1}],
    "user_stories": []
}

def _seed_product_result(bus, spec):
    bus.send("product", "ceo", "result", {"product_spec": spec})

def _seed_engineer_result(bus):
    bus.send("engineer", "ceo", "result", {
        "pr_url": "https://github.com/user/repo/pull/1",
        "issue_url": "https://github.com/user/repo/issues/1",
        "html_content": "<html><h1>GigHub</h1></html>",
    })

def _seed_marketing_result(bus):
    bus.send("marketing", "ceo", "result", {
        "copy": {"tagline": "Ship in 48h", "description": "GigHub is fast.", "cold_email_subject": "x", "cold_email_body": "x", "twitter": "x", "linkedin": "x", "instagram": "x"}
    })

def _seed_qa_result(bus, verdict="pass"):
    bus.send("qa", "ceo", "result", {
        "review_report": {
            "html_verdict": verdict,
            "html_issues": ["Issue 1"],
            "copy_verdict": verdict,
            "copy_issues": ["Issue 2"],
            "overall_verdict": verdict,
        }
    })

def test_ceo_sends_tasks_to_agents():
    bus = MessageBus()
    agent = CEOAgent(bus, startup_idea="GigHub micro-task platform")

    with patch("agents.ceo_agent.call_llm", return_value=FAKE_TASKS):
        agent.decompose_and_send()

    product_msgs = bus.receive("product")
    engineer_msgs = bus.receive("engineer")
    marketing_msgs = bus.receive("marketing")
    assert len(product_msgs) == 1
    assert product_msgs[0]["message_type"] == "task"
    assert len(engineer_msgs) == 0   # engineer gets spec later, not now
    assert len(marketing_msgs) == 0  # marketing gets spec later too

def test_ceo_review_acceptable_proceeds():
    bus = MessageBus()
    agent = CEOAgent(bus, startup_idea="GigHub")

    with patch("agents.ceo_agent.call_llm", return_value=FAKE_REVIEW_OK):
        result = agent.review_product_spec(FAKE_SPEC)

    assert result["verdict"] == "acceptable"
    assert bus.receive("product") == []  # no revision request

def test_ceo_review_fail_sends_revision():
    bus = MessageBus()
    agent = CEOAgent(bus, startup_idea="GigHub")

    with patch("agents.ceo_agent.call_llm", return_value=FAKE_REVIEW_FAIL):
        result = agent.review_product_spec(FAKE_SPEC)

    assert result["verdict"] == "needs_revision"
    revision_msgs = bus.receive("product")
    assert len(revision_msgs) == 1
    assert revision_msgs[0]["message_type"] == "revision_request"
    assert "feedback" in revision_msgs[0]["payload"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_ceo_agent.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `agents/ceo_agent.py`**

```python
import json
from slack_sdk import WebClient
from message_bus import MessageBus
from llm_client import call_llm
from config import SLACK_BOT_TOKEN, SLACK_CHANNEL

DECOMPOSE_SYSTEM = """You are a startup CEO. Break a startup idea into tasks for your team.
Return a JSON object with these keys:
- product_task: object with "idea" and "focus" strings
- engineer_task: object with "focus" string
- marketing_task: object with "focus" string
Respond with ONLY valid JSON."""

REVIEW_SPEC_SYSTEM = """You are a critical CEO reviewing a product specification.
Evaluate whether the spec is specific, actionable, and complete.
Return a JSON object with:
- verdict: "acceptable" or "needs_revision"
- feedback: string (empty if acceptable, specific feedback if needs_revision)
Respond with ONLY valid JSON."""

REVIEW_QA_SYSTEM = """You are a CEO reviewing a QA report. Determine which agent needs to revise its work.
Return a JSON object with:
- engineer_needs_revision: boolean
- marketing_needs_revision: boolean
- engineer_feedback: string (empty if no revision needed)
- marketing_feedback: string (empty if no revision needed)
Respond with ONLY valid JSON."""


class CEOAgent:
    def __init__(self, bus: MessageBus, startup_idea: str):
        self.bus = bus
        self.startup_idea = startup_idea
        self._decisions: list[str] = []

    def log(self, decision: str):
        print(f"[CEO] {decision}")
        self._decisions.append(decision)

    def decompose_and_send(self):
        self.log(f"Decomposing idea: {self.startup_idea}")
        raw = call_llm(DECOMPOSE_SYSTEM, f"Startup idea: {self.startup_idea}")
        try:
            tasks = json.loads(raw)
        except json.JSONDecodeError:
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            tasks = json.loads(cleaned)

        self.log(f"Sending task to Product agent: {tasks['product_task']}")
        self.bus.send("ceo", "product", "task", {
            "idea": self.startup_idea,
            **tasks["product_task"],
        })

    def review_product_spec(self, spec: dict, max_retries: int = 1) -> dict:
        self.log("Reviewing product spec with LLM...")
        raw = call_llm(REVIEW_SPEC_SYSTEM, f"Product spec:\n{json.dumps(spec, indent=2)}")
        try:
            review = json.loads(raw)
        except json.JSONDecodeError:
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            review = json.loads(cleaned)

        self.log(f"Product spec verdict: {review['verdict']}")
        if review["verdict"] == "needs_revision":
            self.log(f"Requesting revision: {review['feedback']}")
            self.bus.send("ceo", "product", "revision_request", {
                "idea": self.startup_idea,
                "focus": "Revise based on feedback",
                "feedback": review["feedback"],
            })
        return review

    def dispatch_to_engineer_and_marketing(self, spec: dict, pr_url: str = ""):
        self.log("Dispatching product spec to Engineer and Marketing agents")
        self.bus.send("ceo", "engineer", "task", {"product_spec": spec})
        self.bus.send("ceo", "marketing", "task", {"product_spec": spec, "pr_url": pr_url})

    def review_qa_report(self, report: dict, engineer_html: str, marketing_copy: dict,
                          engineer_pr_url: str) -> dict:
        self.log(f"Reviewing QA verdict: {report['overall_verdict']}")
        if report["overall_verdict"] == "pass":
            return {"engineer_needs_revision": False, "marketing_needs_revision": False,
                    "engineer_feedback": "", "marketing_feedback": ""}

        user_prompt = (
            f"QA report:\n{json.dumps(report, indent=2)}\n\n"
            f"What should the Engineer and Marketing agents fix?"
        )
        raw = call_llm(REVIEW_QA_SYSTEM, user_prompt)
        try:
            decision = json.loads(raw)
        except json.JSONDecodeError:
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            decision = json.loads(cleaned)

        if decision.get("engineer_needs_revision"):
            self.log(f"Requesting Engineer revision: {decision['engineer_feedback']}")
            self.bus.send("ceo", "engineer", "revision_request", {
                "product_spec": {"value_proposition": ""},  # re-send spec if needed
                "feedback": decision["engineer_feedback"],
                "pr_url": engineer_pr_url,
            })

        if decision.get("marketing_needs_revision"):
            self.log(f"Requesting Marketing revision: {decision['marketing_feedback']}")
            self.bus.send("ceo", "marketing", "revision_request", {
                "product_spec": {"value_proposition": ""},
                "feedback": decision["marketing_feedback"],
                "pr_url": engineer_pr_url,
            })
        return decision

    def post_final_summary(self, spec: dict, pr_url: str, email_sent: bool):
        self.log("Posting final summary to Slack")
        summary = (
            f"*LaunchMind Pipeline Complete* :rocket:\n\n"
            f"*Startup:* {spec.get('value_proposition', 'N/A')}\n"
            f"*GitHub PR:* <{pr_url}|View Pull Request>\n"
            f"*Email sent:* {'Yes' if email_sent else 'No'}\n\n"
            f"*CEO Decisions Log:*\n" + "\n".join(f"  • {d}" for d in self._decisions[-5:])
        )
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(
            channel=SLACK_CHANNEL,
            blocks=[
                {"type": "header", "text": {"type": "plain_text", "text": "LaunchMind: Pipeline Complete"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
            ],
        )
        self.log("Final summary posted to Slack.")

    def get_decision_log(self) -> list[str]:
        return list(self._decisions)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_ceo_agent.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/ceo_agent.py tests/test_ceo_agent.py
git commit -m "feat: implement CEO orchestrator with LLM review and feedback loop"
```

---

## Task 9: Main Entry Point (Full Pipeline)

**Files:**
- Create: `main.py`

This wires all agents together in the correct order:
CEO → Product → (review) → Engineer + Marketing (parallel) → QA → (review) → Slack summary.

- [ ] **Step 1: Implement `main.py`**

```python
import time
from message_bus import MessageBus
from agents.ceo_agent import CEOAgent
from agents.product_agent import ProductAgent
from agents.engineer_agent import EngineerAgent
from agents.marketing_agent import MarketingAgent
from agents.qa_agent import QAAgent
from config import STARTUP_IDEA


def wait_for_message(bus: MessageBus, agent_name: str, timeout: int = 3) -> list[dict]:
    """Poll bus for messages to agent_name. In a dict-based bus this is instant."""
    messages = bus.receive(agent_name)
    return messages


def run():
    print("=" * 60)
    print("   LAUNCHMIND — Multi-Agent Startup Pipeline")
    print("=" * 60)
    print(f"Startup idea: {STARTUP_IDEA}\n")

    bus = MessageBus()
    ceo = CEOAgent(bus, startup_idea=STARTUP_IDEA)
    product_agent = ProductAgent(bus)
    engineer_agent = EngineerAgent(bus)
    marketing_agent = MarketingAgent(bus)
    qa_agent = QAAgent(bus)

    # ── Phase 1: CEO decomposes idea → sends task to Product ──────────────
    ceo.decompose_and_send()

    # ── Phase 2: Product agent generates spec ─────────────────────────────
    product_agent.run()

    # ── Phase 3: CEO reviews spec (feedback loop) ─────────────────────────
    product_result = bus.receive("ceo")
    if not product_result:
        print("[MAIN] ERROR: No response from Product agent.")
        return

    spec = product_result[0]["payload"]["product_spec"]
    review = ceo.review_product_spec(spec)

    if review["verdict"] == "needs_revision":
        print("[MAIN] Product spec needs revision — running Product agent again...")
        product_agent.run()
        product_result2 = bus.receive("ceo")
        if product_result2:
            spec = product_result2[0]["payload"]["product_spec"]
            print("[MAIN] Using revised product spec.")

    # ── Phase 4: CEO dispatches to Engineer and Marketing ─────────────────
    ceo.dispatch_to_engineer_and_marketing(spec)

    # ── Phase 5: Engineer agent (GitHub PR) ──────────────────────────────
    print("\n[MAIN] Running Engineer agent...")
    engineer_agent.run()
    engineer_msgs = bus.receive("ceo")
    if not engineer_msgs:
        print("[MAIN] ERROR: No response from Engineer agent.")
        return
    engineer_payload = engineer_msgs[0]["payload"]
    pr_url = engineer_payload["pr_url"]
    html_content = engineer_payload["html_content"]
    print(f"[MAIN] PR URL: {pr_url}")

    # ── Phase 6: Update Marketing task with PR URL ────────────────────────
    # Marketing was already sent a task without PR URL; update its inbox
    # by sending the PR URL via CEO → Marketing
    bus.send("ceo", "marketing", "task", {
        "product_spec": spec,
        "pr_url": pr_url,
    })
    # Clear the first task that was sent without PR URL
    _ = bus.receive("marketing")  # discard old task (already processed below)

    # Actually: resend correctly with PR URL
    bus.send("ceo", "marketing", "task", {
        "product_spec": spec,
        "pr_url": pr_url,
    })

    # ── Phase 7: Marketing agent (Slack + Email) ──────────────────────────
    print("\n[MAIN] Running Marketing agent...")
    marketing_agent.run()
    marketing_msgs = bus.receive("ceo")
    if not marketing_msgs:
        print("[MAIN] ERROR: No response from Marketing agent.")
        return
    marketing_payload = marketing_msgs[0]["payload"]
    copy = marketing_payload["copy"]

    # ── Phase 8: QA agent ─────────────────────────────────────────────────
    print("\n[MAIN] Running QA agent...")
    bus.send("ceo", "qa", "task", {
        "html_content": html_content,
        "copy": copy,
        "product_spec": spec,
        "pr_url": pr_url,
    })
    qa_agent.run()
    qa_msgs = bus.receive("ceo")
    qa_report = qa_msgs[0]["payload"]["review_report"] if qa_msgs else {"overall_verdict": "pass"}

    # ── Phase 9: CEO reviews QA report (second feedback loop) ────────────
    revision_decision = ceo.review_qa_report(qa_report, html_content, copy, pr_url)

    if revision_decision.get("engineer_needs_revision"):
        print("[MAIN] Engineer revision requested — running Engineer agent again...")
        engineer_agent.run()

    if revision_decision.get("marketing_needs_revision"):
        print("[MAIN] Marketing revision requested — running Marketing agent again...")
        marketing_agent.run()

    # ── Phase 10: CEO posts final summary to Slack ─────────────────────────
    print("\n[MAIN] Posting final summary to Slack...")
    ceo.post_final_summary(spec, pr_url, email_sent=True)

    # ── Final: Print full message history ─────────────────────────────────
    bus.print_history()
    print("\n[MAIN] Pipeline complete.")
    print(f"  GitHub PR:  {pr_url}")
    print(f"  Issue:      {engineer_payload.get('issue_url', 'N/A')}")
    print(f"  Slack:      Check your #{STARTUP_IDEA[:10]} channel")


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Do a dry-run with real credentials**

Make sure `.env` is populated, then:

```bash
python main.py
```

Expected: full pipeline runs, PR appears on GitHub, Slack shows two messages (marketing + CEO summary), email arrives in inbox.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: wire full agent pipeline in main.py"
```

---

## Task 10: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# LaunchMind — Multi-Agent Startup Pipeline

> **Startup idea:** GigHub — A platform where startup founders post small, paid coding micro-tasks and freelance developers claim and complete them in 48 hours.

Built for the Agentic AI course at FAST-NUCES. A network of 5 LLM-powered agents that autonomously define, build, and market a startup.

## Agent Architecture

```
User provides idea
       │
       ▼
   CEO Agent  ──── decomposes idea ────► Product Agent
       │                                      │
       │◄──── product spec ──────────────────┘
       │
       ├──── reviews spec (LLM) ────► revision_request? ──► Product Agent
       │
       ├──── dispatches spec ────────► Engineer Agent ────► GitHub PR
       │                         └──► Marketing Agent ───► Slack + Email
       │
       │◄──── results ──────────────────────────────────────┘
       │
       ├──── sends to QA ──────────► QA Agent ────► GitHub PR comments
       │
       │◄──── QA verdict ─────────────────────────────────────┘
       │
       ├──── reviews verdict (LLM) ─► revision_request? ──► Engineer / Marketing
       │
       └──── posts final summary ───► Slack
```

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/launchmind-YOUR-GROUP
cd launchmind-YOUR-GROUP
pip install -r requirements.txt
cp .env.example .env
# Fill in all values in .env
python main.py
```

## Environment Variables

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `GITHUB_TOKEN` | GitHub → Settings → Developer Settings → PAT (classic) |
| `GITHUB_REPO` | `your-username/repo-name` |
| `SLACK_BOT_TOKEN` | api.slack.com → Your App → OAuth & Permissions |
| `SLACK_CHANNEL` | `#launches` |
| `SENDGRID_API_KEY` | app.sendgrid.com → Settings → API Keys |
| `SENDGRID_FROM_EMAIL` | Your verified sender address |
| `EMAIL_TO` | Your test inbox |

## Platform Integrations

| Platform | What the agent does |
|---|---|
| GitHub | Opens issue, creates branch, commits `index.html`, opens PR, posts review comments |
| Slack | Marketing agent posts launch summary (Block Kit); CEO posts final pipeline summary |
| SendGrid | Marketing agent sends cold outreach email |

## Group Members

| Member | Agent |
|---|---|
| Member 1 | CEO Agent + Main pipeline |
| Member 2 | Engineer Agent + QA Agent |
| Member 3 | Product Agent + Marketing Agent |

## Links

- **GitHub PR:** [link to PR created by Engineer agent]
- **Slack workspace:** [invite link or screenshot]
```

- [ ] **Step 2: Commit README**

```bash
git add README.md
git commit -m "docs: add complete README with architecture and setup instructions"
```

---

## Task 11: Run All Tests

- [ ] **Step 1: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected output:
```
tests/test_ceo_agent.py::test_ceo_sends_tasks_to_agents PASSED
tests/test_ceo_agent.py::test_ceo_review_acceptable_proceeds PASSED
tests/test_ceo_agent.py::test_ceo_review_fail_sends_revision PASSED
tests/test_engineer_agent.py::test_engineer_sends_pr_url_to_ceo PASSED
tests/test_llm_client.py::test_call_llm_returns_string PASSED
tests/test_llm_client.py::test_call_llm_passes_prompts PASSED
tests/test_marketing_agent.py::test_marketing_agent_sends_result_to_ceo PASSED
tests/test_message_bus.py::test_send_and_receive PASSED
tests/test_message_bus.py::test_multiple_messages PASSED
tests/test_message_bus.py::test_history_contains_all_messages PASSED
tests/test_message_bus.py::test_parent_message_id PASSED
tests/test_product_agent.py::test_product_agent_returns_spec PASSED
tests/test_product_agent.py::test_product_agent_does_nothing_with_no_messages PASSED
tests/test_qa_agent.py::test_qa_agent_returns_verdict PASSED

14 passed
```

- [ ] **Step 2: Final commit**

```bash
git add .
git commit -m "test: verify all agent tests pass"
```

---

## Self-Review Against Spec

| Requirement | Covered in |
|---|---|
| CEO decomposes idea with LLM | Task 8, `decompose_and_send()` |
| CEO reviews each agent's output with LLM | Task 8, `review_product_spec()` + `review_qa_report()` |
| At least one feedback loop | `review_product_spec()` sends `revision_request` if needed |
| Structured JSON messages with all required fields | Task 2, `MessageBus.send()` |
| Product spec with all 4 fields | Task 4 |
| Engineer commits HTML to GitHub, opens PR | Task 5 |
| Marketing sends real email via SendGrid | Task 6 |
| Marketing posts Slack Block Kit message | Task 6 |
| QA posts inline PR review comments | Task 7 |
| QA sends verdict to CEO → CEO can request revisions | Task 7 + Task 8 |
| Final Slack summary from CEO | Task 8, `post_final_summary()` |
| Full message history printable | Task 2, `print_history()` |
| No hardcoded secrets | `config.py` + `.env` |
| `.env` in `.gitignore` | Task 1 |
| One file per agent in `agents/` | Tasks 4–8 |
| `main.py` entry point | Task 9 |
| `requirements.txt` | Task 1 |
| `.env.example` | Task 1 |
| README with architecture, setup, links | Task 10 |

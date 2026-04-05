# LaunchMind — Multi-Agent Startup Pipeline

> **Startup idea:** GigHub — A platform where startup founders post small, paid coding micro-tasks and freelance developers claim and complete them in 48 hours.

Built for the Agentic AI course at FAST-NUCES. A network of 5 LLM-powered agents that autonomously define, build, and market a startup — with real GitHub, Slack, and email integrations.

## Agent Architecture

```
User provides startup idea
         │
         ▼
     CEO Agent  ──── LLM decomposes idea ────► Product Agent
         │                                           │
         │◄──── product spec ───────────────────────┘
         │
         ├──── LLM reviews spec ──────────► revision_request? ──► Product Agent (retry)
         │
         ├──── dispatches spec ───────────► Engineer Agent ──► GitHub branch + commit + PR
         │                           └───► Marketing Agent ─► Slack Block Kit + SendGrid email
         │
         │◄──── results ─────────────────────────────────────────────────────┘
         │
         ├──── sends to QA ───────────────► QA Agent ──► GitHub PR inline comments
         │
         │◄──── QA verdict ──────────────────────────────────────────────────┘
         │
         ├──── LLM reviews verdict ───────► revision_request? ──► Engineer / Marketing (retry)
         │
         └──── posts final summary ───────► Slack #launches
```

## Message Schema

Every inter-agent message is a JSON object:

| Field | Type | Description |
|---|---|---|
| `message_id` | string | UUID |
| `from_agent` | string | Sender name |
| `to_agent` | string | Recipient name |
| `message_type` | string | `task`, `result`, `revision_request`, `confirmation` |
| `payload` | object | Content varies by message type |
| `timestamp` | string | ISO 8601 |
| `parent_message_id` | string | For reply tracing (optional) |

## Setup

### Prerequisites
- Python 3.11+
- GitHub account with a public repository
- Slack workspace with a bot
- SendGrid account (free tier)
- Anthropic API key

### Install

```bash
git clone https://github.com/YOUR_USERNAME/launchmind-YOUR-GROUP
cd launchmind-YOUR-GROUP
pip install -r requirements.txt
cp .env.example .env
# Fill in all values in .env
```

### Environment Variables

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `GITHUB_TOKEN` | GitHub → Settings → Developer Settings → PAT (classic), scopes: `repo`, `workflow` |
| `GITHUB_REPO` | `your-username/repo-name` |
| `SLACK_BOT_TOKEN` | api.slack.com → Your App → OAuth & Permissions (starts with `xoxb-`) |
| `SLACK_CHANNEL` | `#launches` |
| `SENDGRID_API_KEY` | app.sendgrid.com → Settings → API Keys |
| `SENDGRID_FROM_EMAIL` | Your verified sender email in SendGrid |
| `EMAIL_TO` | Your test inbox address |

### Run

```bash
python main.py
```

The pipeline takes ~2-3 minutes. You will see agent logs in the terminal as messages are sent and received.

## Platform Integrations

| Platform | Agent | Action |
|---|---|---|
| GitHub | Engineer | Creates issue, creates branch, commits `index.html`, opens PR |
| GitHub | QA | Posts inline review comments on the PR |
| Slack | Marketing | Posts product launch summary (Block Kit) to `#launches` |
| Slack | CEO | Posts final pipeline summary (Block Kit) to `#launches` |
| SendGrid | Marketing | Sends cold outreach email to `EMAIL_TO` |

## Project Structure

```
launchmind/
├── agents/
│   ├── ceo_agent.py          # Orchestrator with feedback loops
│   ├── product_agent.py      # Product spec generation
│   ├── engineer_agent.py     # GitHub PR creation
│   ├── marketing_agent.py    # Slack + email
│   └── qa_agent.py           # Code and copy review
├── message_bus.py            # Shared in-memory message bus
├── llm_client.py             # Anthropic API wrapper
├── config.py                 # Environment variable loader
├── main.py                   # Pipeline entry point
├── requirements.txt
├── .env.example
└── .gitignore
```

## Group Members

| Member | Agents Implemented |
|---|---|
| Muhammad Salman | All 5 agents (CEO, Product, Engineer, Marketing, QA) + Message Bus + Full Pipeline |

## Links

- **GitHub PR (created by Engineer agent):** https://github.com/Salman1205/LaunchMind/pull/13
- **Slack workspace invite:** https://join.slack.com/t/launchmind-talk/shared_invite/zt-3uspopnr4-LkuZlBP9_T8o5gU5EoiBSA
- **Demo video:** https://www.loom.com/share/e94fe0b4a3334cf68d801f52eb18aaf6

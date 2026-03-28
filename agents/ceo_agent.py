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

    def log(self, decision: str) -> None:
        print(f"[CEO] {decision}")
        self._decisions.append(decision)

    def decompose_and_send(self) -> None:
        self.log(f"Decomposing idea: {self.startup_idea}")
        raw = call_llm(DECOMPOSE_SYSTEM, f"Startup idea: {self.startup_idea}")
        try:
            tasks = json.loads(raw)
        except json.JSONDecodeError:
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            tasks = json.loads(cleaned)

        self.log("Sending task to Product agent")
        self.bus.send("ceo", "product", "task", {
            "idea": self.startup_idea,
            **tasks["product_task"],
        })

    def review_product_spec(self, spec: dict) -> dict:
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

    def dispatch_to_engineer_and_marketing(self, spec: dict, pr_url: str = "") -> None:
        self.log("Dispatching product spec to Engineer and Marketing agents")
        self.bus.send("ceo", "engineer", "task", {"product_spec": spec})
        self.bus.send("ceo", "marketing", "task", {"product_spec": spec, "pr_url": pr_url})

    def review_qa_report(
        self,
        report: dict,
        engineer_html: str,
        marketing_copy: dict,
        engineer_pr_url: str,
    ) -> dict:
        self.log(f"Reviewing QA verdict: {report['overall_verdict']}")
        if report["overall_verdict"] == "pass":
            return {
                "engineer_needs_revision": False,
                "marketing_needs_revision": False,
                "engineer_feedback": "",
                "marketing_feedback": "",
            }

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
                "product_spec": {"value_proposition": ""},
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

    def post_final_summary(self, spec: dict, pr_url: str, email_sent: bool) -> None:
        self.log("Posting final summary to Slack")
        summary = (
            f"*LaunchMind Pipeline Complete* :rocket:\n\n"
            f"*Startup:* {spec.get('value_proposition', 'N/A')}\n"
            f"*GitHub PR:* <{pr_url}|View Pull Request>\n"
            f"*Email sent:* {'Yes' if email_sent else 'No'}\n\n"
            f"*CEO Decision Log (last 5):*\n"
            + "\n".join(f"  • {d}" for d in self._decisions[-5:])
        )
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(
            channel=SLACK_CHANNEL,
            blocks=[
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "LaunchMind: Pipeline Complete"},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": summary},
                },
            ],
        )
        self.log("Final summary posted to Slack.")

    def get_decision_log(self) -> list[str]:
        return list(self._decisions)

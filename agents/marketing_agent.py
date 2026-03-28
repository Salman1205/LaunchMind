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

    def run(self) -> None:
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

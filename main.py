from message_bus import MessageBus
from agents.ceo_agent import CEOAgent
from agents.product_agent import ProductAgent
from agents.engineer_agent import EngineerAgent
from agents.marketing_agent import MarketingAgent
from agents.qa_agent import QAAgent
from config import STARTUP_IDEA


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
    print("\n[MAIN] Phase 1: CEO decomposes startup idea")
    ceo.decompose_and_send()

    # ── Phase 2: Product agent generates spec ─────────────────────────────
    print("\n[MAIN] Phase 2: Product agent generates spec")
    product_agent.run()

    # ── Phase 3: CEO reviews spec (feedback loop) ─────────────────────────
    print("\n[MAIN] Phase 3: CEO reviews product spec")
    product_results = bus.receive("ceo")
    if not product_results:
        print("[MAIN] ERROR: No response from Product agent. Exiting.")
        return

    spec = product_results[0]["payload"]["product_spec"]
    review = ceo.review_product_spec(spec)

    if review["verdict"] == "needs_revision":
        print("[MAIN] Product spec needs revision — running Product agent again...")
        product_agent.run()
        revised = bus.receive("ceo")
        if revised:
            spec = revised[0]["payload"]["product_spec"]
            print("[MAIN] Using revised product spec.")

    # ── Phase 4: CEO dispatches to Engineer and Marketing (no PR URL yet) ──
    print("\n[MAIN] Phase 4: CEO dispatches to Engineer + Marketing")
    ceo.dispatch_to_engineer_and_marketing(spec, pr_url="")

    # ── Phase 5: Engineer agent (GitHub PR) ──────────────────────────────
    print("\n[MAIN] Phase 5: Engineer agent runs (GitHub PR)")
    engineer_agent.run()
    engineer_msgs = bus.receive("ceo")
    if not engineer_msgs:
        print("[MAIN] ERROR: No response from Engineer agent. Exiting.")
        return
    engineer_payload = engineer_msgs[0]["payload"]
    pr_url = engineer_payload["pr_url"]
    html_content = engineer_payload["html_content"]
    print(f"[MAIN] PR URL: {pr_url}")
    print(f"[MAIN] Issue URL: {engineer_payload.get('issue_url', 'N/A')}")

    # ── Phase 6: Resend Marketing task WITH PR URL ─────────────────────────
    # Discard the task sent without PR URL, resend with PR URL
    bus.receive("marketing")  # drain old task
    bus.send("ceo", "marketing", "task", {
        "product_spec": spec,
        "pr_url": pr_url,
    })

    # ── Phase 7: Marketing agent (Slack + Email) ──────────────────────────
    print("\n[MAIN] Phase 7: Marketing agent runs (Slack + Email)")
    marketing_agent.run()
    marketing_msgs = bus.receive("ceo")
    if not marketing_msgs:
        print("[MAIN] ERROR: No response from Marketing agent. Exiting.")
        return
    marketing_payload = marketing_msgs[0]["payload"]
    copy = marketing_payload["copy"]
    email_sent = marketing_payload.get("email_sent", False)
    if not email_sent:
        print(f"[MAIN] WARNING: Marketing email was not sent. Reason: {marketing_payload.get('email_error', 'unknown')}")

    # ── Phase 8: QA agent ─────────────────────────────────────────────────
    print("\n[MAIN] Phase 8: QA agent reviews HTML and copy")
    bus.send("ceo", "qa", "task", {
        "html_content": html_content,
        "copy": copy,
        "product_spec": spec,
        "pr_url": pr_url,
    })
    qa_agent.run()
    qa_msgs = bus.receive("ceo")
    qa_report = (
        qa_msgs[0]["payload"]["review_report"]
        if qa_msgs
        else {"overall_verdict": "pass", "html_issues": [], "copy_issues": []}
    )

    # ── Phase 9: CEO reviews QA (second feedback loop) ────────────────────
    print("\n[MAIN] Phase 9: CEO reviews QA verdict")
    revision_decision = ceo.review_qa_report(qa_report, spec, html_content, copy, pr_url)

    if revision_decision.get("engineer_needs_revision"):
        print("[MAIN] Engineer revision requested — running Engineer agent again...")
        engineer_agent.run()
        revised_eng = bus.receive("ceo")
        if revised_eng:
            html_content = revised_eng[0]["payload"]["html_content"]

    if revision_decision.get("marketing_needs_revision"):
        print("[MAIN] Marketing revision requested — running Marketing agent again...")
        # Give Marketing the updated PR URL
        bus.receive("marketing")  # drain any stale message
        bus.send("ceo", "marketing", "revision_request", {
            "product_spec": spec,
            "pr_url": pr_url,
            "feedback": revision_decision.get("marketing_feedback", ""),
        })
        marketing_agent.run()

    # ── Phase 10: CEO posts final summary to Slack ─────────────────────────
    print("\n[MAIN] Phase 10: CEO posts final summary to Slack")
    ceo.post_final_summary(spec, pr_url, email_sent=email_sent)

    # ── Print full message history ─────────────────────────────────────────
    bus.print_history()

    print("\n" + "=" * 60)
    print("   PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  GitHub PR:   {pr_url}")
    print(f"  Issue URL:   {engineer_payload.get('issue_url', 'N/A')}")
    print(f"  Slack:       Check your Slack #launches channel")
    print(f"  Email:       Check your inbox at {__import__('config').EMAIL_TO}")
    print("=" * 60)


if __name__ == "__main__":
    run()

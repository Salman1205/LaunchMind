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

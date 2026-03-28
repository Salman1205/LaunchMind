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

def test_receive_clears_inbox():
    bus = MessageBus()
    bus.send("ceo", "product", "task", {"idea": "a"})
    bus.receive("product")
    assert bus.receive("product") == []

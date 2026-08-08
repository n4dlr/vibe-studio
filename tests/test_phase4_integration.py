import time
import pytest
from vibe_studio.core.message_bus import MessageBus, AgentMessage
from vibe_studio.editor.lsp_client import LSPClient
from vibe_studio.tools.search_tools import SearchTools
from vibe_studio.agents.self_learning_tests import SelfLearningTests


def test_message_bus_auto_timestamp_and_history():
    bus = MessageBus(history_depth=10)
    received = []

    def cb(msg: AgentMessage):
        received.append(msg)

    bus.subscribe("agent_event", cb)

    msg1 = AgentMessage(sender="agent1", topic="agent_event", payload={"action": "step1"})
    bus.publish(msg1)

    assert len(received) == 1
    assert received[0].timestamp > 0
    assert len(bus.get_history("agent_event")) == 1

    # Test unsubscribe
    bus.unsubscribe("agent_event", cb)
    bus.publish(AgentMessage(sender="agent1", topic="agent_event", payload={"action": "step2"}))
    assert len(received) == 1  # Not incremented
    assert len(bus.get_history("agent_event")) == 2  # History still records it


def test_lsp_client_event_correlation(tmp_path):
    client = LSPClient("python", tmp_path)
    assert not client.is_running
    # Verify request ID increment and lock safety
    req_id1 = client._next_id()
    req_id2 = client._next_id()
    assert req_id2 == req_id1 + 1


def test_search_tools_globbing(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def target_function(): pass\n")
    (tmp_path / "src" / "utils.js").write_text("function target_function() {}\n")

    st = SearchTools(tmp_path)
    res_py = st.search_text("target_function", include_patterns=["*.py"])
    assert len(res_py) == 1
    assert res_py[0]["file"].endswith(".py")

    res_all = st.search_text("target_function")
    assert len(res_all) == 2


def test_self_learning_tests_stub_generation(tmp_path):
    (tmp_path / "src").mkdir()
    f = tmp_path / "src" / "math_utils.py"
    f.write_text("""
def calculate_total(item_count: int, price_val: float, is_discounted: bool = False):
    return item_count * price_val
""")

    slt = SelfLearningTests()
    untested = slt.find_untested_functions(tmp_path)
    assert len(untested) == 1
    assert untested[0].function_name == "calculate_total"

    template = slt.generate_test_template(untested[0])
    assert "calculate_total" in template
    assert "test_calculate_total_auto_generated" in template
    assert "TODO" not in template  # Stubs are now clean and executable

    created = slt.generate_and_save_tests(tmp_path)
    assert len(created) == 1
    assert (tmp_path / created[0]).exists()

from pathlib import Path
import re

HTML = Path(__file__).resolve().parents[1].joinpath("src", "ui", "index.html").read_text(encoding="utf-8")

def test_redundant_local_models_item_removed_from_workspace():
    nav = HTML.split('<nav class="workspace-nav"', 1)[1].split("</nav>", 1)[0]
    assert 'id="nav-models"' not in nav
    assert "Modelos locais" not in nav

def test_hardware_view_has_back_to_conversation_button():
    assert 'id="hardware-view"' in HTML
    assert 'id="hardware-back"' in HTML
    assert "Voltar à conversa" in HTML

def test_hardware_navigation_opens_dedicated_view():
    assert '$("nav-hardware").onclick=()=>openHardwareView();' in HTML
    assert "function openHardwareView()" in HTML
    assert "function closeHardwareView()" in HTML

def test_hardware_selector_is_preserved():
    assert 'id="adaptiveHardwareSelector"' in HTML
    assert 'id="adaptiveHardwareDisclosure"' in HTML
    assert "A consultar o perfil de hardware e os runtimes disponíveis" in HTML

def test_model_manager_back_button_is_preserved():
    assert 'id="manager-back"' in HTML
    assert 'id="manager-view"' in HTML

def test_chat_stream_and_model_api_references_preserved():
    assert "/api/chat/stream" in HTML
    assert "/api/models" in HTML
    assert "/api/load" in HTML

def test_primary_navigation_items_remain_once():
    nav = HTML.split('<nav class="workspace-nav"', 1)[1].split("</nav>", 1)[0]
    for item in ["nav-new-chat", "nav-history", "nav-projects", "nav-agents",
                 "nav-performance", "nav-hardware", "nav-diagnostics"]:
        assert nav.count(f'id="{item}"') == 1

def test_script_tags_are_balanced():
    assert HTML.count("<script") == HTML.count("</script>")


def test_hardware_view_expands_selector_to_full_width():
    assert '#hardware-view #adaptiveHardwareDisclosure>summary{display:none!important}' in HTML
    assert '#hardware-view #adaptiveHardwareSelector{width:100%;max-width:none' in HTML
    assert 'disclosure.open=true;' in HTML

def test_hardware_view_has_bottom_return_to_chat_button():
    assert 'id="hardware-back-bottom"' in HTML
    assert 'Voltar ao chat' in HTML
    assert '$("hardware-back-bottom").onclick=closeHardwareView;' in HTML

def test_hardware_disclosure_state_is_restored_on_return():
    assert 'let hardwareOriginalDisclosureOpen=false;' in HTML
    assert 'disclosure.open=hardwareOriginalDisclosureOpen;' in HTML

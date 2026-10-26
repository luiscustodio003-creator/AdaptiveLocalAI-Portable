from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "src" / "ui" / "index.html").read_text(encoding="utf-8")

class Stage1InterfaceTests(unittest.TestCase):
    def test_main_navigation_items_exist_once(self):
        nav = HTML.split('<nav class="workspace-nav"', 1)[1].split("</nav>", 1)[0]
        expected = ["nav-new-chat", "nav-history", "nav-projects", "nav-agents", "nav-performance", "nav-hardware", "nav-diagnostics"]
        for element_id in expected:
            with self.subTest(element_id=element_id): self.assertEqual(nav.count(f'id="{element_id}"'), 1)
        self.assertNotIn('id="nav-models"', nav)
        self.assertNotIn("Modelos locais", nav)

    def test_model_selector_is_unique_and_in_composer(self):
        self.assertEqual(HTML.count('id="sel"'), 1)
        composer = HTML.index('class="composer-actions"'); selector = HTML.index('id="sel"'); send = HTML.index('id="go"')
        self.assertLess(composer, selector); self.assertLess(selector, send)

    def test_hardware_view_and_return_to_conversation(self):
        self.assertIn('id="hardware-view"', HTML); self.assertIn('id="hardware-back"', HTML)
        self.assertIn("Voltar à conversa", HTML)
        self.assertIn('$("nav-hardware").onclick=()=>openHardwareView();', HTML)
        self.assertIn("function openHardwareView()", HTML); self.assertIn("function closeHardwareView()", HTML)

    def test_model_manager_and_existing_apis_are_preserved(self):
        for needle in ['id="manager-back"','id="manager-view"','/api/chat/stream','/api/models','/api/load','/api/catalog','async function openManager()']:
            with self.subTest(needle=needle): self.assertIn(needle, HTML)

    def test_hardware_selector_is_preserved(self):
        self.assertIn('id="adaptiveHardwareSelector"', HTML); self.assertIn('id="adaptiveHardwareDisclosure"', HTML)

    def test_attachment_remains_explicitly_disabled(self):
        self.assertRegex(HTML, r'<button[^>]*id="attach-placeholder"[^>]*disabled')

    def test_code_copy_and_accessibility_are_preserved(self):
        for needle in ['function renderAssistantContent(target, value)','navigator.clipboard.writeText','id="toggle-sidebar"','id="sidebar-resizer"']:
            with self.subTest(needle=needle): self.assertIn(needle, HTML)

    def test_inline_javascript_has_balanced_script_tags(self):
        self.assertEqual(len(re.findall(r"<script\b", HTML, re.I)), len(re.findall(r"</script>", HTML, re.I)))

if __name__ == "__main__": unittest.main()

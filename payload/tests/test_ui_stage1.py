from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "src" / "ui" / "index.html"


class Stage1InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_main_navigation_items_exist_once(self):
        expected = [
            "nav-new-chat", "nav-history", "nav-projects", "nav-agents",
            "nav-models", "nav-performance", "nav-hardware", "nav-diagnostics",
        ]
        for element_id in expected:
            with self.subTest(element_id=element_id):
                self.assertEqual(self.html.count(f'id="{element_id}"'), 1)

    def test_model_selector_is_unique_and_in_composer(self):
        self.assertEqual(self.html.count('id="sel"'), 1)
        composer = self.html.index('class="composer-actions"')
        selector = self.html.index('id="sel"')
        send = self.html.index('id="go"')
        self.assertLess(composer, selector)
        self.assertLess(selector, send)

    def test_primary_navigation_is_kept_expanded_by_default(self):
        self.assertIn('card.classList.contains("nav-card")', self.html)
        self.assertIn('const initiallyCollapsed = card.classList.contains("nav-card")', self.html)

    def test_attachment_is_explicitly_disabled_for_future_stage(self):
        self.assertRegex(self.html, r'<button[^>]*id="attach-placeholder"[^>]*disabled')
        self.assertIn("Anexos serão integrados numa etapa futura", self.html)

    def test_existing_streaming_endpoint_is_preserved(self):
        self.assertIn('streamApi("/api/chat/stream"', self.html)
        self.assertIn('fetch(url,{method:"POST"', self.html)

    def test_existing_model_loading_and_catalog_are_preserved(self):
        self.assertIn('api("/api/load",{name})', self.html)
        self.assertIn('api("/api/models")', self.html)
        self.assertIn('api("/api/catalog")', self.html)
        self.assertIn("async function openManager()", self.html)

    def test_code_block_rendering_and_copy_are_preserved(self):
        self.assertIn("function renderAssistantContent(target, value)", self.html)
        self.assertIn("Copiar código", self.html)
        self.assertIn("navigator.clipboard.writeText", self.html)

    def test_history_and_projects_are_not_misrepresented_as_persistent(self):
        self.assertIn("O histórico persistente será implementado na Etapa 2", self.html)
        self.assertIn("Ainda não foram criadas pastas nem dados de projetos", self.html)

    def test_layout_controls_and_accessibility_remain(self):
        self.assertIn('id="toggle-sidebar"', self.html)
        self.assertIn('id="sidebar-resizer"', self.html)
        self.assertIn('aria-label="Selecionar modelo local"', self.html)

    def test_inline_javascript_has_balanced_script_tags(self):
        self.assertEqual(len(re.findall(r"<script\b", self.html, re.I)),
                         len(re.findall(r"</script>", self.html, re.I)))


if __name__ == "__main__":
    unittest.main()

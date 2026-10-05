import unittest
from unittest.mock import AsyncMock

from app.crawlers.company_crawler import CompanyCrawler
from app.extractors.website_text_extractor import WebsiteTextExtractor


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.extractor = WebsiteTextExtractor()

    def test_metadata_jsonld_and_footer_survive_noise_removal(self):
        html = '''<html><head><title>Cedar</title><meta name="description" content="Inventory software for retailers">
        <script type="application/ld+json">{"@graph":[{"@type":"Organization","name":"Cedar","numberOfEmployees":{"value":75},"address":{"addressLocality":"Pune"}}]}</script>
        <script>tracking_code()</script><style>css_noise</style></head><body>
        <nav>Menu noise <span hidden>Nested noise</span></nav><div hidden>Hidden noise</div>
        <h1>Cedar</h1><p>We build <strong>inventory</strong> software.</p>
        <footer><address>Registered office: Pune, India</address></footer></body></html>'''
        text = self.extractor.extract(html)
        for expected in ["Page title: Cedar", "Inventory software for retailers", '"value": 75', '"addressLocality": "Pune"', "# Cedar", "We build inventory software.", "Registered office: Pune, India"]:
            self.assertIn(expected, text)
        for noise in ["tracking_code", "css_noise", "Menu noise", "Nested noise", "Hidden noise"]:
            self.assertNotIn(noise, text)

    def test_bad_jsonld_does_not_discard_visible_content(self):
        for value in ['{bad json', '{"@type": null}', '42', 'null', '{"@type": [null, {}]}']:
            with self.subTest(value=value):
                text = self.extractor.extract(f'<script type="application/ld+json">{value}</script><p>Cedar builds software.</p>')
                self.assertIn("Cedar builds software.", text)

    def test_separate_entities_and_relative_links_are_preserved(self):
        text = self.extractor.extract('''<script type="application/ld+json">[
            {"@type":"Organization","name":"Cedar","numberOfEmployees":75},
            {"@type":"Organization","name":"Birch","numberOfEmployees":12},
            {"@type":"Person","name":"Unrelated person"}]</script>
            <h2>Products</h2><p><a href="/products">Inventory platform</a></p>''', "https://cedar.example/about")
        self.assertIn('[Inventory platform](https://cedar.example/products)', text)
        entities = [line for line in text.splitlines() if line.startswith("Structured website claims:")]
        self.assertEqual(len(entities), 2)
        self.assertNotIn("Birch", entities[0])
        self.assertNotIn("Unrelated person", text)

    def test_table_rows_keep_company_with_field_labels(self):
        text = self.extractor.extract('<table><tr><th>Company</th><th>Employees</th></tr><tr><td>Cedar</td><td>75</td></tr><tr><td>Birch</td><td>12</td></tr></table>')
        self.assertIn("Company: Cedar | Employees: 75", text)
        self.assertIn("Company: Birch | Employees: 12", text)

    def test_empty_html(self):
        self.assertEqual(self.extractor.extract(""), "")


class CrawlTests(unittest.IsolatedAsyncioTestCase):
    async def test_pages_retain_source_attribution_and_resolve_relative_links(self):
        client = AsyncMock()
        client.fetch.side_effect = ['<h1>Cedar</h1><a href="/about">About</a>', '<h1>About Cedar</h1><p>Headquartered in Pune.</p>']
        result = await CompanyCrawler(client, WebsiteTextExtractor()).crawl("https://cedar.example")
        self.assertEqual(result.source_urls, ["https://cedar.example", "https://cedar.example/about"])
        self.assertIn("Source: https://cedar.example/about\n", result.text)
        self.assertIn("[About](https://cedar.example/about)", result.text)

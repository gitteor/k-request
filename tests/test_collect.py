import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from scripts.collect import canonical, belongs, clean, score, validate, search
import json
import tempfile
import os
from scripts import collect
from pathlib import Path

class CollectorTests(unittest.TestCase):
    def test_budget_counts_attempts_and_resets(self):
        usage = {}
        for _ in range(32):
            collect.consume_budget(usage, '2026-09-21T00:00:00+00:00')
        with self.assertRaises(collect.BudgetExhausted):
            collect.consume_budget(usage, '2026-09-21T12:00:00+00:00')
        collect.consume_budget(usage, '2026-09-22T00:00:00+00:00')
        self.assertEqual(usage['monthly'], 33)
        usage['monthly'] = 1000
        with self.assertRaises(collect.BudgetExhausted):
            collect.consume_budget(usage, '2026-09-23T00:00:00+00:00')
        collect.consume_budget(usage, '2026-10-01T00:00:00+00:00')
        self.assertEqual(usage['monthly'], 1)

    def test_tracking_removed_but_post_identity_retained(self):
        self.assertEqual(canonical('https://example.com/board?id=9&utm_source=x#reply'), 'https://example.com/board?id=9')

    def test_host_and_path_boundary(self):
        self.assertTrue(belongs('https://www.reddit.com/r/kpophelp/comments/123', 'reddit.com/r/kpophelp'))
        self.assertFalse(belongs('https://reddit.com.evil.org/r/kpophelp', 'reddit.com/r/kpophelp'))
        self.assertFalse(belongs('https://reddit.com/r/kpophelper/a', 'reddit.com/r/kpophelp'))

    def test_intent_and_exclusion(self):
        self.assertGreaterEqual(score('Can you recommend a Korean proxy for shipping?', 'Korean proxy', [])[0],75)
        self.assertEqual(score('Korean proxy sponsored', 'Korean proxy', ['sponsored'])[0],0)
        self.assertLess(score('Korean entertainment industry news', 'Korea', [])[0],35)

    def test_html_and_unsafe_url(self):
        self.assertEqual(clean('<b>Hello</b> &amp; friends'), 'Hello & friends')
        with self.assertRaises(ValueError): canonical('javascript:alert(1)')

    def test_config(self):
        c=json.loads((Path(__file__).resolve().parents[1]/'config.json').read_text(encoding='utf-8'))
        validate(c)
        c['sources'][0]['domain']='reddit.com OR site:evil.com'
        with self.assertRaises(ValueError): validate(c)

    @patch('scripts.collect.time.sleep')
    @patch('scripts.collect.urlopen')
    def test_rate_limit_has_bounded_retry(self, open_mock, sleep_mock):
        open_mock.side_effect=HTTPError('https://example.com',429,'rate limit',{},None)
        with self.assertRaises(HTTPError): search('query','test-key','pm')
        self.assertEqual(open_mock.call_count,3)

    def test_collection_merges_duplicates_and_preserves_on_failure(self):
        c=json.loads((Path(__file__).resolve().parents[1]/'config.json').read_text(encoding='utf-8'))
        c['keywords']=['Korean proxy', 'Korea shipping']
        c['sources']=c['sources'][:1]
        c['sources'][0].pop('queries', None)
        row={'url':'https://reddit.com/r/kpophelp/comments/test', 'title':'Can you recommend Korean proxy shipping?', 'description':'How can I buy goods?'}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root=Path(folder)
            (root/'config.json').write_text(json.dumps(c),encoding='utf-8')
            output=root/'posts.json'
            with patch.object(collect,'ROOT',root), patch.object(collect,'OUT',output), patch.dict(os.environ,{'BRAVE_SEARCH_API_KEY':'test'}), patch.object(collect.time,'sleep'), patch.object(collect,'search',return_value=[row]):
                collect.main()
                first=json.loads(output.read_text(encoding='utf-8'))
                self.assertEqual(first['status'],'ok')
                self.assertEqual(len(first['posts']),1)
                self.assertEqual(len(first['posts'][0]['keywords']),2)
                with patch.object(collect,'search',side_effect=TimeoutError):
                    collect.main()
                failed=json.loads(output.read_text(encoding='utf-8'))
                self.assertEqual(failed['status'],'error')
                self.assertEqual(failed['posts'],first['posts'])
                self.assertEqual(failed['last_success'],first['last_success'])
                with patch.object(collect,'search',return_value=[]) as empty:
                    collect.main()
                    self.assertEqual(empty.call_count,2)
                    self.assertTrue(all(call.args[2] == c['freshness'] for call in empty.call_args_list))

if __name__ == '__main__': unittest.main()

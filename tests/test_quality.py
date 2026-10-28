import unittest
from scripts.quality import classify
from scripts.collect import query_tasks, identity, korea_day

STAMP = '2026-10-28T00:00:00+00:00'

def assess(title, excerpt='', date='2026-10-26T00:00:00Z'):
    return classify(dict(title=title, excerpt=excerpt, source_date=date,
                         url='https://reddit.com/r/kpophelp/comments/abc'), [], STAMP)

class QualityTests(unittest.TestCase):
    def test_explicit_recent_proxy_request(self):
        p=assess('Can anyone recommend a Korean proxy?', 'I want to buy Weverse merch.')
        self.assertEqual(p['tier'], 'priority')
        self.assertEqual(p['evidence']['barrier'], 'proxy')

    def test_negative_examples(self):
        for title in ['Korean proxy review', 'WTS Korean merch proxy', 'Korean shipping guide',
                      'My Korean cosmetics haul', 'Korean proxy survey', 'Shipping to Korea?']:
            with self.subTest(title=title):
                self.assertEqual(assess(title)['tier'], 'excluded')

    def test_reply_snippet_does_not_establish_author_request(self):
        p=assess('My favorite Korean albums', 'Can anyone recommend a Korean proxy? I want to buy merch.')
        self.assertNotEqual(p['tier'], 'priority')

    def test_buy_interest_without_barrier_needs_review(self):
        self.assertEqual(assess('Where can I buy Korean cosmetics?')['tier'],'review')

    def test_age_is_not_discovery_date(self):
        title='Can anyone recommend a Korean proxy?'
        for dt,tier in [(None,'review'),('invalid','review'),('2027-01-01','review'),
                        ('2026-10-10','followup'),('2023-01-01','archive')]:
            with self.subTest(date=dt):
                self.assertEqual(assess(title,date=dt)['tier'],tier)

    def test_channel_queries_interleave(self):
        c={'keywords':['fallback'],'sources':[{'name':'a','enabled':True,'queries':['a1','a2']},
             {'name':'b','enabled':True,'queries':['b1']},{'name':'off','enabled':False}]}
        self.assertEqual([q for _,q in query_tasks(c)],['a1','b1','a2'])

    def test_reddit_link_variants_are_one_lead(self):
        self.assertEqual(identity('https://www.reddit.com/r/kpophelp/comments/abc/title/comment/'),
                         identity('https://old.reddit.com/r/kpophelp/comments/abc/other_title/?utm_source=test'))

    def test_daily_metrics_use_korea_time(self):
        self.assertEqual(korea_day('2026-10-27T16:00:00Z'),'2026-10-28')

if __name__ == '__main__': unittest.main()

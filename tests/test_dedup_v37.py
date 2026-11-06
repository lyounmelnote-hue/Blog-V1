import unittest
from unittest.mock import patch
from src import daily


def row(category, url):
    return {'properties': {'분야': {'select': {'name': category}}, '원본 링크': {'url': url}}}


class DedupTests(unittest.TestCase):
    def test_tracking_params_and_host_case(self):
        a = daily.normalized_article_url('https://WWW.Example.COM/a/?utm_source=x&id=1&fbclid=z')
        b = daily.normalized_article_url('http://example.com/a?id=1')
        self.assertEqual(a, b)

    def test_date_category_count(self):
        self.assertEqual(daily.existing_category_counts([row('문화','https://a.com/a'),row('문화','https://a.com/b')])['문화'],2)

    def test_dedupe_across_categories(self):
        seen = daily.existing_day_urls([row('문화','https://example.com/a?utm_source=abc')])
        candidates = [{'title':'same','url':'https://example.com/a'}, {'title':'new','url':'https://example.com/b'}, {'title':'again','url':'https://example.com/b?fbclid=1'}]
        self.assertEqual([x['title'] for x in daily.dedupe_candidates(candidates,seen)], ['new'])

    def test_existing_category_skips_writes(self):
        with patch.object(daily,'existing_day_rows',return_value=[row('문화','https://example.com/a')]), \
             patch.object(daily,'curated_sources',return_value=[]), \
             patch.object(daily,'search',return_value=[]), \
             patch.object(daily.topic_dedupe,'historical_rows',return_value=[]), \
             patch.object(daily,'create_unverified_source') as create, \
             patch.dict('os.environ',{'DRY_RUN':'false','REVIEW_QUEUE':'true'}):
            daily.run()
            create.assert_not_called()

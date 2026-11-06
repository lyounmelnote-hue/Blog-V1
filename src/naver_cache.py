"""Run-scoped successful-response cache. No credentials or stale results persisted."""
from collections import Counter


class SearchCache:
    def __init__(self):
        self.responses = {}
        self.totals = {}
        self.calls = Counter()
        self.hits = Counter()

    @staticmethod
    def phrase(value):
        return ' '.join(value.split())

    def get(self, request, endpoint, phrase, count, headers):
        phrase = self.phrase(phrase)
        sort = 'date' if endpoint == 'news' else 'sim'
        key = (endpoint, phrase, count, sort)
        if key in self.responses:
            self.hits[endpoint] += 1
            return self.responses[key]
        # The total is independent of display size. Reuse collection totals for scoring.
        if endpoint == 'blog' and count == 1 and phrase in self.totals:
            self.hits['blog_total'] += 1
            return {'total': self.totals[phrase]}
        self.calls[endpoint] += 1
        data = request('GET', f'https://openapi.naver.com/v1/search/{endpoint}.json',
                       headers=headers, params={'query': phrase, 'display': count, 'sort': sort})
        self.responses[key] = data
        if endpoint == 'blog' and 'total' in data:
            self.totals[phrase] = data['total']
        return data

    def report(self):
        return {'logical_requests': dict(self.calls), 'cache_hits': dict(self.hits),
                'note': 'HTTP retries counted separately by read-only transport; total is result count, not search volume'}

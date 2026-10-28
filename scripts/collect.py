"""Search indexed public links; never scrape the source platforms."""
import hashlib
import html
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen
from urllib.error import HTTPError
try:
    from .quality import classify
except ImportError:
    from quality import classify

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'site/data/posts.json'

def now():
    return datetime.now(timezone.utc).isoformat()

def korea_day(stamp):
    return datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(timezone(timedelta(hours=9))).date().isoformat()

def clean(value):
    return html.unescape(re.sub(r'<[^>]*>', '', str(value or ''))).strip()

def canonical(url):
    p = urlsplit(url)
    if p.scheme not in ('https', 'http') or not p.hostname:
        raise ValueError('Invalid result URL')
    params = [(k, v) for k, v in parse_qsl(p.query) if not k.startswith('utm_') and k not in ('ref', 'source')]
    scheme = 'https' if p.hostname and p.hostname.endswith('heykorean.com') else p.scheme
    return urlunsplit((scheme, p.netloc.lower(), p.path.rstrip('/'), urlencode(params), ''))

def belongs(url, domain):
    p, d = urlsplit(url), urlsplit('https://' + domain)
    host = (p.hostname or '').lower()
    path = p.path.lower().rstrip('/')
    base = d.path.lower().rstrip('/')
    return (host == d.hostname or host.endswith('.' + d.hostname)) and (not base or path == base or path.startswith(base + '/'))

def identity(url):
    p = urlsplit(url)
    if p.hostname == 'reddit.com' or (p.hostname or '').endswith('.reddit.com'):
        m = re.search(r'/comments/([a-zA-Z0-9]+)', p.path)
        if m:
            return 'reddit_' + m.group(1).lower()
    return hashlib.sha256(canonical(url).encode()).hexdigest()[:20]

def score(text, keyword, excludes):
    t = text.casefold()
    if any(e.casefold() in t for e in excludes):
        return 0, []
    groups = [
        (25, '한국 상품 관련', ['korea', 'korean', '한국', 'k-pop', 'kpop', 'olive young', 'weverse']),
        (30, '배송·구매대행 필요', ['proxy', 'forwarding', 'kaddy', 'k-addy', '구매대행', '배송대행', '한국 주소', 'only ship', 'doesn’t ship', "doesn't ship", '해외배송']),
        (25, '질문·추천 요청', ['?', 'looking for', 'recommend', 'how can', 'how do', 'where can', 'help', '추천', '어떻게', '구할']),
        (20, '구매·배송 맥락', ['buy', 'purchase', 'shipping', 'ship to', 'order', '구매', '배송'])
    ]
    reasons, total = [], 0
    for points, label, words in groups:
        if any(w in t for w in words):
            total += points
            reasons.append(label)
    if keyword.casefold() in t and not total:
        return 35, ['설정 검색어 일치']
    return total, reasons

def validate(c):
    for field in ('keywords', 'exclude'):
        if not isinstance(c.get(field), list) or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in c[field]):
            raise ValueError('Invalid ' + field)
    if not 1 <= len(c['keywords']) <= 30:
        raise ValueError('Use 1–30 keywords')
    if not c.get('sources') or len(c['sources']) > 20:
        raise ValueError('Use 1–20 sources')
    for s in c['sources']:
        if not re.fullmatch(r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[a-zA-Z0-9_/-]+)?', s['domain']):
            raise ValueError('Invalid source domain')
        if 'queries' in s and (not isinstance(s['queries'], list) or not 1 <= len(s['queries']) <= 30 or any(not isinstance(q, str) or not q.strip() or len(q) > 200 for q in s['queries'])):
            raise ValueError('Invalid source queries')
    if c['freshness'] not in ('pd', 'pw', 'pm', 'py'):
        raise ValueError('Invalid freshness')
    for key, lo, hi in [('min_score', 0, 100), ('retention_days', 1, 365), ('max_queries', 1, 32)]:
        if type(c[key]) is not int or not lo <= c[key] <= hi:
            raise ValueError('Invalid ' + key)

def query_tasks(c):
    # Interleave channels; source-specific questions replace the generic Cartesian product.
    sources = [s for s in c['sources'] if s.get('enabled')]
    queries = [s.get('queries', c['keywords']) for s in sources]
    return [(s, qs[i]) for i in range(max(map(len, queries), default=0)) for s, qs in zip(sources, queries) if i < len(qs)]

def write_result(result):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(OUT)

class BudgetExhausted(Exception):
    pass

def consume_budget(usage, stamp):
    if usage.get('month') != stamp[:7]:
        usage.update(month=stamp[:7], monthly=0)
    if usage.get('day') != stamp[:10]:
        usage.update(day=stamp[:10], daily=0)
    if usage['monthly'] >= 1000 or usage['daily'] >= 32:
        raise BudgetExhausted()
    usage['monthly'] += 1
    usage['daily'] += 1

def search(query, key, freshness, before_request=lambda: None):
    params = {'q': query, 'count': 20}
    if freshness:
        params['freshness'] = freshness
    url = 'https://api.search.brave.com/res/v1/web/search?' + urlencode(params)
    for attempt in range(3):
        try:
            req = Request(url, headers={'Accept': 'application/json', 'X-Subscription-Token': key})
            before_request()
            with urlopen(req, timeout=30) as res:
                return json.load(res).get('web', {}).get('results', [])
        except HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))

def main():
    c = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    validate(c)
    previous = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {'posts': []}
    stamp = now()
    result = {**previous, 'last_attempt': stamp, 'errors': [], 'queries': 0}
    result['schema_version'] = 2
    result['query_report'] = []
    usage = result.setdefault('usage', {})
    limited = False
    def before_request():
        consume_budget(usage, now())
        # Checkpoint every attempted call, including retries.
        write_result(result)
    key = os.getenv('BRAVE_SEARCH_API_KEY')
    if not key:
        result.update(status='not_configured', errors=['검색 API 키 설정이 필요합니다.'])
    else:
        posts = {}
        for p in sorted(previous['posts'], key=lambda p: p['first_seen'], reverse=True):
            posts[identity(p['url'])] = p
        successes = 0
        tasks = query_tasks(c)
        # Rotate the capped budget so later queries are never permanently starved.
        start = previous.get('next_query', 0) % max(1, len(tasks))
        tasks = (tasks[start:] + tasks[:start])[:c['max_queries']]
        for source, keyword in tasks:
            result['queries'] += 1
            try:
                rows = search(f"site:{source['domain']} {keyword}", key, c['freshness'], before_request)
                successes += 1
                report = dict(source=source['name'], query=keyword, fetched=len(rows), priority=0, review=0)
                for row in rows:
                    try:
                        url = canonical(row['url'])
                    except (ValueError, KeyError):
                        continue
                    if not belongs(url, source['domain']):
                        continue
                    title, excerpt = clean(row.get('title')), clean(row.get('description'))
                    uid = identity(url)
                    old = posts.get(uid, {})
                    posts[uid] = dict(id=old.get('id', uid), url=url, title=title, excerpt=excerpt[:700], source=source['name'], category=source.get('category', '기타'),
                        keywords=sorted(set(old.get('keywords', []) + [keyword])),
                        first_seen=old.get('first_seen', stamp), last_seen=stamp,
                        expanded_search=False,
                        source_date=old.get('source_date') or row.get('page_age') or None,
                        content_updated=stamp if old.get('title') != title or old.get('excerpt') != excerpt[:700] else old.get('content_updated', stamp))
                    assessment = classify(posts[uid], c['exclude'], stamp, c['min_score'])
                    if assessment['tier'] in ('priority', 'review'):
                        report[assessment['tier']] += 1
                result['query_report'].append(report)
            except BudgetExhausted:
                result['queries'] -= 1
                limited = True
                break
            except Exception as e:
                result['errors'].append({'source': source['name'], 'keyword': keyword, 'error': type(e).__name__})
            time.sleep(1.1)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=c['retention_days'])).isoformat()
        result['posts'] = sorted([p for p in posts.values() if p['last_seen'] >= cutoff], key=lambda p: p['first_seen'], reverse=True)
        result['next_query'] = start + result['queries']
        result['status'] = 'ok' if successes and not result['errors'] else 'partial' if successes else 'error'
        if limited:
            result['status'] = 'budget_limited'
        if successes:
            result['last_success'] = stamp
    # Reassess retained records too: discovery time must never stand in for publication time.
    for post in result['posts']:
        post.update(classify(post, c['exclude'], stamp, c['min_score']))
    counts = {tier: sum(p['tier'] == tier for p in result['posts']) for tier in ('priority', 'review', 'followup', 'archive', 'excluded')}
    new = sum(p['tier'] == 'priority' and korea_day(p['first_seen']) == korea_day(stamp) for p in result['posts'])
    result['quality'] = dict(counts=counts, new_priority_today=new, target=10, review_limit=20, gap=max(0, 10-new),
        note='검색 제목·요약과 검색엔진 날짜 기반 후보입니다. 실제 미해결 수요 여부는 원문 확인이 필요합니다.')
    history = [h for h in result.get('quality_history', []) if h['date'] != korea_day(stamp)]
    result['quality_history'] = (history + [dict(date=korea_day(stamp), new_priority=new, counts=counts)])[-30:]
    write_result(result)
    print(f"Collection status: {result['status']}; queries: {result['queries']}; results: {len(result['posts'])}")

if __name__ == '__main__':
    main()

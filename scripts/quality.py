"""Conservative, explainable triage of search snippets, not verified sales leads."""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

def match(pattern, text):
    found = re.search(pattern, text, re.I)
    return found.group(0) if found else ''

CONTEXT = r'\bkorea[n]?\b|\bk[- ]?pop\b|\bk[- ]?beauty\b|weverse|bunjang|olive young|musinsa|yes24|aladin|withmuu|makestar|soundwave|ktown4u|한국|번개장터|올리브영'
REQUEST = r'\?|\b(?:looking for|anyone know|any recommendations|recommend me|can someone|can anyone|how (?:can|do|to)|where (?:can|do|to)|want to (?:buy|order)|trying to (?:buy|order)|need (?:a |help|some)|wtb|iso)\b|구하고|구할|사고 싶|사고싶|구매하고|찾고|추천|어떻게|방법|도와'
BARRIER = r'\b(?:proxy|proxies|forwarder|forwarding|kaddy|kaddys|k-addy|k-address)\b|korean address|korean phone|korean (?:bank|card)|only ships? (?:to|within|in) korea|(?:doesn.t|don.t|won.t|cannot|can.t) ship|no international shipping|shipping (?:is too|too|so) expensive|consolidat(?:e|ion)|구매대행|배송대행|배대지|한국 주소|해외배송.{0,12}(?:안|불가)|한국.{0,8}카드'
BUY = r'\b(?:buy|buying|purchase|order|ordering|merch|merchandise|album|albums|photocard|photocards|goods|cosmetics|skincare|makeup|plush|figure|figures|snacks)\b|구매|굿즈|화장품|택배|과자|배송'
SELLER = r'\b(?:wts|selling|for sale|we offer|our service|i offer|i run a|promo code|coupon code|sponsored|giveaway|join my|join our|group order open)\b|구매대행 업체|판매합니다|홍보|광고'
NONLEAD = r'\b(?:haul|review|unboxing|megathread|weekly thread|monthly thread|buying guide|shipping guide|already ordered|already bought|order arrived|package arrived|resolved|solved|worst experience|survey|market research)\b|후기|도착했|해결완료|설문'
INBOUND = r'\b(?:shipping|ship|send|moving) to korea\b|ship(?:ping)? within korea|한국으로.{0,10}(?:배송|택배)'

def classify(post, excludes, stamp, min_score=75):
    title, excerpt = post.get('title', ''), post.get('excerpt', '')
    text = title + ' ' + excerpt
    evidence = {k: match(p, text) for k, p in [('context', CONTEXT), ('request', REQUEST), ('barrier', BARRIER), ('purchase', BUY)]}
    title_request = match(REQUEST, title)
    blocked = ''
    if any(x.casefold() in text.casefold() for x in excludes):
        blocked = '제외 표현'
    elif match(SELLER, title):
        blocked = '판매·서비스 홍보'
    elif match(NONLEAD, title):
        blocked = '후기·정보·종료된 요청'
    elif match(INBOUND, title):
        blocked = '한국 내 배송 또는 한국행 배송'
    elif not evidence['context']:
        blocked = '한국 구매 맥락 부족'
    elif not evidence['barrier'] and not (title_request and evidence['purchase']):
        blocked = '구매·대행 요청 근거 부족'
    p = urlsplit(post.get('url', ''))
    if p.hostname and (p.hostname == 'reddit.com' or p.hostname.endswith('.reddit.com')) and '/comments/' not in p.path:
        blocked = '개별 게시글 아님'
    if p.hostname and p.hostname.endswith('heykorean.com') and ('ktown' in p.hostname or '/web/' in p.path):
        blocked = '기존 디렉터리 링크'
    age = None
    try:
        dt = datetime.fromisoformat(str(post.get('source_date')).replace('Z', '+00:00'))
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.fromisoformat(stamp.replace('Z', '+00:00')) - dt).total_seconds() / 86400
        if age < 0:
            age = None
    except (ValueError, TypeError):
        pass
    rank = (20 if evidence['context'] else 0) + (30 if title_request else 10 if evidence['request'] else 0) + (35 if evidence['barrier'] else 0) + (15 if evidence['purchase'] else 0)
    # A snippet may quote replies, not the author. Promote only title-confirmed requests.
    strong = bool(title_request and evidence['context'] and evidence['barrier'] and rank >= min_score)
    if blocked:
        tier, reason = 'excluded', blocked
    elif age is not None and age > 30:
        tier, reason = 'archive', '30일 초과 · 신규 대응 제외'
    elif age is None:
        tier, reason = 'review', '원문 날짜 확인 필요'
    elif strong and age <= 7:
        tier, reason = 'priority', '최근 7일 · 요청과 구매 장벽 단서'
    elif strong:
        tier, reason = 'followup', '8~30일 · 아직 필요한지 확인'
    else:
        tier, reason = 'review', '작성자 구매·배송 의사 확인 필요'
    return dict(score=0 if blocked else rank, tier=tier, decision=reason,
                evidence=evidence, age_days=round(age, 1) if age is not None else None,
                reasons=[v for v in [reason, '배송·구매대행 단서' if evidence['barrier'] else '구매 관심 단서'] if v],
                assessment_version=2)

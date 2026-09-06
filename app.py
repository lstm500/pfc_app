"""PFCえらび / Streamlit. Run: streamlit run app.py"""
import streamlit as st
import json, math, re, uuid, unicodedata, gzip, heapq
from datetime import date
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import urlparse, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import deque

STORES = ['セブンイレブン','ローソン','ファミリーマート','イオン・トップバリュ','その他スーパー']
STORE_GROUPS = {
    'コンビニ': ['セブンイレブン','ローソン','ファミリーマート','ナチュラルローソン','ローソンストア100','ミニストップ','デイリーヤマザキ','NewDays','セイコーマート','ポプラ'],
    'スーパー': ['オーケー（OKストア）','イオン・トップバリュ','イオンスタイル','まいばすけっと','マックスバリュ','ダイエー','ピーコックストア','西友','ライフ','サミット','マルエツ','マルエツ プチ','イトーヨーカドー','ヨークフーズ','ヨークマート','ヨークベニマル','オオゼキ','東急ストア','東武ストア','京急ストア','いなげや','コモディイイダ','文化堂','三徳','肉のハナマサ','業務スーパー','ベルク','ベルクス','ヤオコー','ロピア','コープ','成城石井','紀ノ国屋','クイーンズ伊勢丹','明治屋','ビオセボン','オーガニックスーパー ビオラル','万代','阪急オアシス','関西スーパー','平和堂','バロー','アピタ','ピアゴ','ゆめタウン','ゆめマート','サンリブ','ハローズ','ラ・ムー','ディオ','トライアル','コストコ','ドン・キホーテ','その他スーパー'],
}
STORES += [name for names in STORE_GROUPS.values() for name in names if name not in STORES]

def store_label(name):
    count=sum(d['store']==name for d in st.session_state.catalog)
    return f'{name}  ·  {count}商品' if count else f'{name}  ·  商品未登録'

CATEGORIES = ['肉・サラダチキン','魚・魚介','卵・大豆','サラダ','ご飯・麺・パン','ヨーグルト・乳製品','飲料','お菓子・バー','その他']
DOMAINS = {'www.sej.co.jp':STORES[0], 'www.lawson.co.jp':STORES[1], 'mldata.lawson.co.jp':STORES[1], 'www.family.co.jp':STORES[2], 'www.topvalu.net':STORES[3]}

def item(i,store,name,cat,p,f,c,k,price,unit,url,note=''):
    return dict(id=i,store=store,name=name,category=cat,p=p,f=f,c=c,kcal=k,price=price,unit=unit,url=url,checked='2026-09-06',note=note)

SEEDS = [
item('s1',STORES[0],'７プレミアム サラダチキン プレーン',CATEGORIES[0],24.1,None,0.,114.,278.64,'公式掲載単位（店頭表示で要確認）','https://www.sej.co.jp/products/a/item/250701/','脂質・栄養表示の単位は未確認。公式ページに情報表示不可の文言もあるため取扱いを要確認。'),
item('s2',STORES[0],'たんぱく質が摂れる鶏むね肉サラダ',CATEGORIES[3],21.8,10.9,4.4,199.,483.84,'1食','https://www.sej.co.jp/products/a/item/104758','地域限定。公式ページに情報表示不可の文言もあるため取扱いを要確認。'),
item('l1',STORES[1],'たんぱく質30.3g サラダチキン プレーン',CATEGORIES[0],30.3,2.1,.2,141.,279.,'1包装（110g）','https://mldata.lawson.co.jp/recommend/original/detail/1507463_1996.html'),
item('f1',STORES[2],'たんぱく質22.6g 国産鶏のサラダチキン 3種のハーブ＆スパイス',CATEGORIES[0],22.6,None,None,None,298.,'1商品（商品名に記載）','https://www.family.co.jp/goods/sidedishes/2230566.html','Pは商品名から確認。F・C・カロリーは未確認。'),
item('f2',STORES[2],'たんぱく質10.6g サラダチキンバー 3種のチーズ',CATEGORIES[0],10.6,None,None,None,None,'1商品（商品名に記載）','https://www.family.co.jp/goods/sidedishes/2230696.html','Pは商品名から確認。他の栄養値・価格は未確認。'),
item('t1',STORES[3],'トップバリュ プレーンヨーグルト 400g',CATEGORIES[5],13.2,2.8,18.,148.,149.04,'1包装（400g）','https://www.topvalu.net/items/detail/4902121964383/','公式100g当たり表示を4倍して1包装に換算。食べる量が100gなら個数を0.25に設定。')
]

def ratios(d):
    if any(d.get(x) is None for x in ('p','f','c')): return None
    v=[d['p']*4,d['f']*9,d['c']*4]; total=sum(v)
    return [x/total*100 for x in v] if total else None

def distance(d,target):
    r=ratios(d)
    return sum(abs(a-b) for a,b in zip(r,target)) if r else float('inf')

def norm(s): return unicodedata.normalize('NFKC',s).casefold()

def filter_items(rows,stores,q,cat,minp,maxf,maxk,budget):
    return [d for d in rows if d['store'] in stores
            and all(w in norm(d['name']+' '+d['note']) for w in norm(q).split())
            and (cat=='すべて' or d['category']==cat)
            and (minp==0 or d['p'] is not None and d['p']>=minp)
            and (maxf==0 or d['f'] is not None and d['f']<=maxf)
            and (maxk==0 or d['kcal'] is not None and d['kcal']<=maxk)
            and (budget==0 or d['price'] is not None and d['price']<=budget)]

def validate(rows):
    if not isinstance(rows,list) or len(rows)>40000: raise ValueError('商品は40000件以内のリストにしてください。')
    seen=set()
    for d in rows:
        if not isinstance(d,dict): raise ValueError('商品形式が不正です。')
        for k in ('id','store','name','category','unit','url','checked','note'):
            if not isinstance(d.get(k),str) or len(d[k])>2000: raise ValueError('商品情報が不正です。')
        if d['id'] in seen: raise ValueError('商品IDが重複しています。')
        seen.add(d['id'])
        if d['store'] not in STORES or d['category'] not in CATEGORIES: raise ValueError('店舗・ジャンルが不正です。')
        if d['url'] and not safe_link(d['url']): raise ValueError('出典URLはhttpsにしてください。')
        for k in ('p','f','c','kcal','price'):
            v=d.get(k)
            if v is not None and (type(v) not in (float,int) or not math.isfinite(v) or v<0 or v>100000): raise ValueError('栄養値・価格が不正です。')
    return rows

def safe_link(url):
    try:
        p=urlparse(url)
        return p.scheme=='https' and bool(p.hostname) and not p.username and not p.password
    except ValueError: return False

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise ValueError('転送先のページは取得できません。公式の最終URLを指定してください。')

class PageText(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip and data.strip(): self.parts.append(data.strip())

@st.cache_data(ttl=3600,show_spinner=False)
def fetch_official(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in DOMAINS or p.port not in (None,443) or p.username or p.password:
        raise ValueError('対応する4社の公式商品URLを入力してください。')
    with build_opener(NoRedirect()).open(Request(url,headers={'User-Agent':'PFC-erabi/1.0'}),timeout=12) as response:
        raw=response.read(2000001)
        if len(raw)>2000000: raise ValueError('ページが大きすぎます。')
        parser=PageText(); parser.feed(raw.decode(response.headers.get_content_charset() or 'utf-8',errors='replace'))
    text=' '.join(parser.parts)
    # Extract only a nutrition section, never recommended products or reviews.
    m=re.search(r'栄養成分',text)
    section=text[m.end():m.end()+650] if m else ''
    vals={}
    for key,label in [('p','たんぱく質'),('f','脂質'),('c','炭水化物'),('kcal','(?:熱量|エネルギー)')]:
        n=re.search(label+r'[\s:：]*([0-9]+(?:\.[0-9]+)?)\s*(?:g|kcal)',section)
        vals[key]=float(n.group(1)) if n else None
    return section, vals

def fmt(v,suffix='g'): return '未確認' if v is None else f'{v:g}{suffix}'

def chart(d):
    r=ratios(d)
    if r is None: st.caption('PFC比率：栄養値不足のため計算できません。'); return
    colors=['#27806b','#cf8b37','#617dc5']
    html=''.join(f'<span style="width:{v}%;background:{col};height:12px;display:inline-block"></span>' for v,col in zip(r,colors))
    st.markdown('<div style="display:flex;border-radius:8px;overflow:hidden">'+html+'</div>',unsafe_allow_html=True)
    st.caption(' ／ '.join(f'{label} {v:.1f}%' for label,v in zip('PFC',r)))

# Public catalog collector: no Streamlit API is called from its worker thread.
# v4 collector principles:
# 1) public official pages only, robots.txt honored
# 2) discovery is autonomous: robots -> sitemap -> structured data -> HTML links
# 3) successful discovery routes are learned per retailer and reused on later runs
# 4) nutrition values are never invented; uncertain serving units are marked as such
import sqlite3, threading, time, hashlib, tempfile
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urljoin, urlunparse, parse_qsl, urlencode
from urllib.error import HTTPError, URLError
from urllib.robotparser import RobotFileParser

COLLECT_SOURCES = {
    STORES[0]: ['https://www.sej.co.jp/products/a/itemresult/?'+urlencode(dict(key=k,limit=100,p=1)) for k in ['たんぱく質','チキン','サラダ','おにぎり','魚','豆腐','ヨーグルト']],
    STORES[1]: ['https://www.lawson.co.jp/recommend/original/select/salad/index.html','https://www.lawson.co.jp/recommend/original/rice/'],
    STORES[2]: ['https://www.family.co.jp/goods/sidedishes.html','https://www.family.co.jp/goods.html'],
    STORES[3]: ['https://www.topvalu.net/items/list/100400600/','https://www.topvalu.net/items/list/100200500/','https://www.topvalu.net/items/'],
}
EXTRA_ROOTS = {'ナチュラルローソン': 'https://natural.lawson.co.jp/', 'ローソンストア100': 'https://store100.lawson.co.jp/', 'ミニストップ': 'https://www.ministop.co.jp/', 'デイリーヤマザキ': 'https://www.daily-yamazaki.jp/', 'NewDays': 'https://retail.jr-cross.co.jp/newdays/', 'セイコーマート': 'https://www.seicomart.co.jp/', 'ポプラ': 'https://www.poplar-cvs.co.jp/', 'オーケー（OKストア）': 'https://ok-corporation.jp/', 'イオンスタイル': 'https://www.aeonretail.jp/', 'まいばすけっと': 'https://www.mybasket.co.jp/', 'マックスバリュ': 'https://onlinestore.maxvalu.co.jp/', 'ダイエー': 'https://www.daiei.co.jp/', 'ピーコックストア': 'https://aeonmarket.co.jp/', '西友': 'https://www.seiyu.co.jp/', 'ライフ': 'https://www.lifecorp.jp/', 'サミット': 'https://www.summitstore.co.jp/', 'マルエツ': 'https://www.maruetsu.co.jp/', 'マルエツ プチ': 'https://www.maruetsu.co.jp/', 'イトーヨーカドー': 'https://www.itoyokado.co.jp/', 'ヨークフーズ': 'https://www.york-inc.com/', 'ヨークマート': 'https://www.york-inc.com/', 'ヨークベニマル': 'https://yorkbenimaru.com/', 'オオゼキ': 'https://www.ozeki-net.co.jp/', '東急ストア': 'https://www.tokyu-store.co.jp/', '東武ストア': 'https://www.tobustore.co.jp/', '京急ストア': 'https://www.keikyu-store.co.jp/', 'いなげや': 'https://www.inageya.co.jp/', 'コモディイイダ': 'https://www.comodi-iida.co.jp/', '文化堂': 'https://www.bunkado.com/', '三徳': 'https://santoku.co.jp/', '肉のハナマサ': 'https://www.hanamasa.co.jp/', '業務スーパー': 'https://www.gyomusuper.jp/', 'ベルク': 'https://www.belc.jp/', 'ベルクス': 'https://sunbelx.com/', 'ヤオコー': 'https://www.yaoko-net.com/', 'ロピア': 'https://lopia.jp/', 'コープ': 'https://goods.jccu.coop/', '成城石井': 'https://www.seijoishii.com/', '紀ノ国屋': 'https://www.e-kinokuniya.com/', 'クイーンズ伊勢丹': 'https://www.im-food.co.jp/', '明治屋': 'https://www.meidi-ya.co.jp/', 'ビオセボン': 'https://www.bio-c-bon.jp/', 'オーガニックスーパー ビオラル': 'https://www.lifecorp.jp/bio-ral/', '万代': 'https://www.mandai-net.co.jp/', '阪急オアシス': 'https://hankyu-oasis.kansai-foodmarket.co.jp/', '関西スーパー': 'https://www.kansaisuper.co.jp/', '平和堂': 'https://www.heiwado.jp/', 'バロー': 'https://valor.jp/', 'アピタ': 'https://www.uny.co.jp/', 'ピアゴ': 'https://www.uny.co.jp/', 'ゆめタウン': 'https://www.izumi.jp/', 'ゆめマート': 'https://www.izumi.jp/', 'サンリブ': 'https://www.sunlive.co.jp/', 'ハローズ': 'https://www.halows.com/', 'ラ・ムー': 'https://www.dkt-s.com/', 'ディオ': 'https://www.dkt-s.com/', 'トライアル': 'https://www.trial-net.co.jp/', 'コストコ': 'https://www.costco.co.jp/', 'ドン・キホーテ': 'https://www.donki.com/'}
for store,root in EXTRA_ROOTS.items():
    COLLECT_SOURCES[store]=[root]
COLLECT_SOURCES['その他スーパー']=[]
COLLECT_STORES=[s for s in STORES if s!='その他スーパー']
COLLECT_LIMIT=500
# Precision/coverage is preferred over raw speed. Different retailers can still overlap I/O,
# but each host is serialized and crawl-delay is honored.
COLLECT_WORKERS=8
COLLECT_DEFAULT_HOST_DELAY=0.45
COLLECT_CHECKPOINT_SECONDS=4.0
COLLECT_JOB_VERSION=10
COLLECT_UA='PFCProductCollector/2.0'
MAX_HTML_PAGES_PER_STORE=3600
MAX_SITEMAPS_PER_STORE=36
MAX_QUEUE_PER_STORE=7000
MAX_DEPTH=7
SITEMAP_EXPLORATION=180
LEARNED_SEED_LIMIT=20
COMMON_DISCOVERY_PATHS=('products/','product/','goods/','items/','item/','foods/','food/','lineup/','catalog/','shop/','search/')
STATIC_EXT_RE=re.compile(r'\.(?:jpg|jpeg|png|gif|webp|svg|css|js|woff2?|ttf|ico|mp4|mp3|zip|docx?|xlsx?|pptx?)$',re.I)
BAD_PATH_RE=re.compile(r'(?:/|^)(?:login|cart|checkout|contact|recruit|privacy|terms|company|corporate|ir|news|recipe|event|campaign)(?:/|$)',re.I)
PRODUCT_HINT_RE=re.compile(r'(?:product|products|goods|item|items|shohin|commodity|sku|detail|foods?|lineup|catalog)',re.I)
LIST_HINT_RE=re.compile(r'(?:category|categories|search|select|brand|lineup|catalog|products?|goods|items?)',re.I)
FOOD_LABEL_RE=re.compile(r'商品|食品|食料|一覧|ラインナップ|ブランド|惣菜|弁当|おにぎり|パン|麺|肉|魚|卵|豆腐|納豆|乳|ヨーグルト|サラダ|プロテイン|たんぱく',re.I)
NONFOOD_LABEL_RE=re.compile(r'ペット|ドッグ|キャット|洗剤|日用品|化粧|スキンケア|衣料|家電|酒|ビール|ワイン|求人|採用',re.I)

# Keep DOMAINS useful for manual web-search links in the UI, but collection authorization is
# store-aware and can follow official subdomains of the same organization.
for store,urls in COLLECT_SOURCES.items():
    for u in urls:
        h=urlparse(u).hostname
        if h: DOMAINS.setdefault(h,store)

def registrable_base(host):
    host=(host or '').lower().strip('.')
    parts=host.split('.')
    if len(parts)<=2: return host
    if '.'.join(parts[-2:]) in {'co.jp','ne.jp','or.jp','ac.jp','go.jp','gr.jp'} and len(parts)>=3:
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:])

STORE_HOSTS={s:set() for s in COLLECT_STORES}
STORE_BASES={s:set() for s in COLLECT_STORES}
for store in COLLECT_STORES:
    for u in COLLECT_SOURCES.get(store,[]):
        h=urlparse(u).hostname
        if h:
            STORE_HOSTS[store].add(h); STORE_BASES[store].add(registrable_base(h))
            if h.startswith('www.'): STORE_HOSTS[store].add(h[4:])
            elif h.count('.')>=1: STORE_HOSTS[store].add('www.'+h)

BASE_STORES={}
for s,bases in STORE_BASES.items():
    for b in bases: BASE_STORES.setdefault(b,set()).add(s)

def store_aliases(store):
    aliases={store}
    plain=re.sub(r'（.*?）','',store).strip()
    if plain: aliases.add(plain)
    m=re.search(r'（(.*?)）',store)
    if m:
        aliases.add(m.group(1)); aliases.add(m.group(1).replace('ストア',''))
    aliases.add(store.replace('・','').replace(' ','').replace('（','').replace('）',''))
    custom={
        'NewDays':{'NewDays','ニューデイズ'}, 'オーケー（OKストア）':{'オーケー','OKストア','OK'},
        'イオン・トップバリュ':{'トップバリュ','TOPVALU'}, 'マルエツ プチ':{'マルエツプチ','Maruetsu Petit'},
        'ヨークフーズ':{'ヨークフーズ','York Foods'}, 'ヨークマート':{'ヨークマート','York Mart'},
        'ラ・ムー':{'ラ・ムー','LAMU','LA MU'}, 'ディオ':{'ディオ','DIO'},
        'アピタ':{'アピタ','APITA'}, 'ピアゴ':{'ピアゴ','PIAGO'},
        'ゆめタウン':{'ゆめタウン','you me town'}, 'ゆめマート':{'ゆめマート','you me mart'},
    }
    aliases.update(custom.get(store,set()))
    return {a for a in aliases if len(a)>=2}

STORE_ALIASES={s:store_aliases(s) for s in COLLECT_STORES}

def allowed_host(store,host):
    host=(host or '').lower()
    if host in STORE_HOSTS.get(store,set()): return True
    base=registrable_base(host)
    return bool(base and base in STORE_BASES.get(store,set()))

def canonical(url,store=None):
    try:
        p=urlparse(url)
    except ValueError:
        return ''
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443): return ''
    if store is not None:
        if not allowed_host(store,p.hostname): return ''
    elif p.hostname not in DOMAINS:
        return ''
    query=urlencode(sorted((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith(('utm_','fbclid','gclid'))),doseq=True)
    path=re.sub(r'/+','/',p.path or '/')
    return urlunparse(('https',p.hostname.lower(),path,'',query,''))

def task_key(store,url): return store+'|'+url

def source_identity(row):
    return row.get('source_key') or canonical(row.get('url',''),row.get('store')) or row.get('url','')

def path_prefix(url):
    p=urlparse(url); seg=[x for x in p.path.split('/') if x]
    if not seg: return '/'
    # Strip a last segment that looks like a product id/detail slug; keep the reusable route.
    n=2 if len(seg)>=2 else 1
    return '/'+('/'.join(seg[:n]))+'/'

def page_priority(store,url,label='',profile=None):
    try: p=urlparse(url)
    except ValueError: return None
    path=p.path or '/'; low=(path+' '+label).casefold()
    if STATIC_EXT_RE.search(path) or BAD_PATH_RE.search(path) or NONFOOD_LABEL_RE.search(label): return None
    if path.lower().endswith(('.xml','.xml.gz')) or 'sitemap' in path.lower(): return -10
    profile=profile or {}
    for prefix,score in sorted(profile.get('prefix_scores',{}).items(),key=lambda x:-x[1]):
        if score>=2 and path.startswith(prefix): return 0
    if re.search(r'(?:product|goods|item|sku|detail)[/_-][^/]*(?:\d{3,}|[a-z0-9_-]{8,})',path,re.I): return 0
    if PRODUCT_HINT_RE.search(low): return 1
    if LIST_HINT_RE.search(low) or FOOD_LABEL_RE.search(label): return 2
    if path in ('','/'): return 3
    return 5

def guess_category(name):
    for pattern,cat in [('ヨーグルト|チーズ|牛乳',5),('サラダチキン|鶏|チキン|ささみ|豚|ハム|牛肉',0),('サラダ',3),('おにぎり|おむすび|ご飯|弁当|麺|パン|パスタ|そば|うどん',4),('豆腐|納豆|たまご|玉子|卵|大豆',2),('さば|鮭|魚|海老|えび|ツナ|いか|かに',1),('ドリンク|飲料|豆乳',6),('バー|ナッツ|菓子|チョコ',7)]:
        if re.search(pattern,name,re.I): return CATEGORIES[cat]
    return CATEGORIES[-1]

class ProductHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.texts=[]; self.links=[]; self.headings=[]; self.title=''; self.skip=0; self.capture=None; self.anchor=None; self.metas={}
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style','noscript'): self.skip+=1
        if self.skip: return
        if tag=='meta':
            key=a.get('property') or a.get('name')
            if key and a.get('content'): self.metas[key.casefold()]=unicodedata.normalize('NFKC',a['content']).strip()
            if a.get('property')=='og:title': self.title=a.get('content','')
        if tag in ('h1','h2','title'): self.capture=[tag,[],len(self.texts)]
        if tag=='a': self.anchor=[a.get('href',''),[]]
        if tag=='img' and self.anchor and a.get('alt'): self.anchor[1].append(a['alt'])
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'): self.skip=max(0,self.skip-1)
        if self.capture and tag==self.capture[0]:
            kind,parts,offset=self.capture; title=' '.join(parts).strip()
            if kind=='title' and not self.title: self.title=title
            if kind!='title' and title: self.headings.append((kind,title,offset))
            self.capture=None
        if tag=='a' and self.anchor:
            self.links.append((self.anchor[0],' '.join(self.anchor[1]))); self.anchor=None
    def handle_data(self,data):
        if self.skip or not data.strip(): return
        v=unicodedata.normalize('NFKC',data).strip(); self.texts.append(v)
        if self.capture: self.capture[1].append(v)
        if self.anchor: self.anchor[1].append(v)

def json_blobs(html):
    out=[]
    for m in re.finditer(r'<script\b([^>]*)>(.*?)</script\s*>',html,re.I|re.S):
        attrs=m.group(1); body=unescape(m.group(2)).strip()
        if not body or len(body)>5000000: continue
        typem=re.search(r'\btype\s*=\s*["\']([^"\']+)',attrs,re.I)
        idm=re.search(r'\bid\s*=\s*["\']([^"\']+)',attrs,re.I)
        typ=(typem.group(1) if typem else '').casefold(); sid=(idm.group(1) if idm else '').casefold()
        if 'json' not in typ and sid not in {'__next_data__','__nuxt_data__','__apollo_state__'} and not body.startswith(('{','[')): continue
        if body.startswith('<!--'): body=re.sub(r'^<!--|-->$','',body).strip()
        try: out.append(json.loads(body))
        except Exception: pass
    return out

def walk_json(obj,max_nodes=20000):
    stack=[obj]; n=0
    while stack and n<max_nodes:
        cur=stack.pop(); n+=1
        yield cur
        if isinstance(cur,dict): stack.extend(cur.values())
        elif isinstance(cur,list): stack.extend(cur)

def keynorm(k): return re.sub(r'[^a-z0-9ぁ-んァ-ヶ一-龠]','',norm(str(k)))

def get_any(d,names):
    wanted={keynorm(x) for x in names}
    for k,v in d.items():
        if keynorm(k) in wanted: return v
    return None

def number_from(v,unit=None):
    if isinstance(v,(int,float)) and not isinstance(v,bool): return float(v)
    if isinstance(v,dict):
        v=get_any(v,['value','amount','valueText','displayValue'])
    if not isinstance(v,str): return None
    s=unicodedata.normalize('NFKC',v).replace(',','')
    m=re.search(r'-?\d+(?:\.\d+)?',s)
    if not m: return None
    x=float(m.group())
    if x<0: return None
    if unit and unit.casefold() not in s.casefold() and re.search(r'[a-zA-Z]+',s):
        # Keep numeric values only when the string is not explicitly labeled with a conflicting unit.
        units=re.findall(r'[a-zA-Z]+',s)
        if units and unit.casefold() not in [u.casefold() for u in units]: return None
    return x

def nutrition_from_dict(d):
    if not isinstance(d,dict): return None
    nd=get_any(d,['nutrition','nutritionInformation','nutrients','nutritionFacts','nutritionalInformation'])
    candidates=[nd,d] if isinstance(nd,dict) else [d]
    for x in candidates:
        p=number_from(get_any(x,['proteinContent','protein','proteins','たんぱく質','タンパク質','たん白質']),'g')
        if p is None: continue
        f=number_from(get_any(x,['fatContent','fat','totalFat','脂質']),'g')
        c=number_from(get_any(x,['carbohydrateContent','carbohydrate','carbs','炭水化物']),'g')
        kcal=number_from(get_any(x,['calories','energy','energyKcal','kcal','熱量','エネルギー']),'kcal')
        serving=get_any(x,['servingSize','nutritionServingSize','serving','basis','栄養成分表示単位']) or get_any(d,['servingSize','nutritionServingSize'])
        serving=str(serving).strip() if serving is not None else ''
        return dict(p=p,f=f,c=c,kcal=kcal,unit=serving)
    return None

def product_name_from_dict(d):
    if not isinstance(d,dict): return ''
    typ=get_any(d,['@type','type'])
    typed='product' in norm(str(typ)) if typ is not None else False
    name=get_any(d,['name','productName','itemName','商品名','title'])
    if isinstance(name,dict): name=get_any(name,['value','text'])
    if not isinstance(name,str): return ''
    name=unicodedata.normalize('NFKC',re.sub(r'<[^>]+>',' ',name)).strip()
    return name if typed or nutrition_from_dict(d) else ''

def product_url_from_dict(store,d,base_url):
    for key in ['url','productUrl','productURL','detailUrl','detailURL','link','href','canonicalUrl']:
        v=get_any(d,[key])
        if isinstance(v,str):
            u=canonical(urljoin(base_url,v),store)
            if u: return u
    return ''

def price_from_dict(d):
    offers=get_any(d,['offers','offer','priceInfo','pricing']) if isinstance(d,dict) else None
    for x in ([offers,d] if isinstance(offers,dict) else [d]):
        if not isinstance(x,dict): continue
        v=get_any(x,['price','priceIncludingTax','taxIncludedPrice','salePrice','税込価格'])
        n=number_from(v)
        if n is not None and 0<n<1000000: return n
    return None

def unit_from_text(s):
    s=unicodedata.normalize('NFKC',s)
    patterns=[
        r'((?:100\s*(?:g|ml)|1\s*(?:包装|袋|個|本|食|カップ|パック|枚|粒|食分|製品))[^。:：]{0,55}?(?:当たり|あたり))',
        r'栄養成分(?:表示)?\s*[（(]?([^）)\n]{1,60}?(?:当たり|あたり))[）)]?',
        r'([^。\n]{0,35}(?:1食分|1個|1袋|1包装|100g|100ml)[^。\n]{0,35}(?:当たり|あたり))'
    ]
    for pat in patterns:
        m=re.search(pat,s,re.I)
        if m: return re.sub(r'\s+',' ',m.group(1)).strip()
    return ''

def nutrition_candidates_from_text(text):
    text=unicodedata.normalize('NFKC',text)
    out=[]
    for m in re.finditer(r'(?:たんぱく質|たん白質|タンパク質)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*g',text,re.I):
        left=max(0,m.start()-260); right=min(len(text),m.end()+520); section=text[left:right]
        p=float(m.group(1)); vals={'p':p,'f':None,'c':None,'kcal':None}
        specs=[('f','脂質','g'),('c','炭水化物','g'),('kcal','(?:熱量|エネルギー)','kcal')]
        for key,label,unit in specs:
            mm=re.search(label+r'\s*[:：]?\s*(\d+(?:\.\d+)?)\s*'+unit,section,re.I)
            vals[key]=float(mm.group(1)) if mm else None
        unit=unit_from_text(section)
        score=1+sum(vals[k] is not None for k in ('f','c','kcal'))+(2 if unit else 0)
        out.append((score,vals,unit,section))
    # Deduplicate identical nutrition blocks generated by repeated navigation/footer text.
    uniq={}
    for score,vals,unit,section in out:
        key=(vals['p'],vals['f'],vals['c'],vals['kcal'],norm(unit))
        if key not in uniq or score>uniq[key][0]: uniq[key]=(score,vals,unit,section)
    return sorted(uniq.values(),key=lambda x:-x[0])

def row_from_values(store,url,name,vals,unit,price=None,method='HTML',source_key=None):
    if not name or len(name)>220 or vals.get('p') is None: return None
    if any(v is not None and (v<0 or v>100000) for v in vals.values()): return None
    unit=(unit or '').strip() or '公式掲載単位（要確認）'
    # A package price must not be combined with nutrition expressed per 100g/ml or an unknown unit.
    # Keeping price=None is safer than producing a false protein-per-yen ranking.
    if price is not None and not re.search(r'1\s*(?:包装|袋|個|本|食|カップ|パック|枚|粒|製品)',unit):
        price=None
    note=f'公式サイトから自動取得（{method}）。数値は公開表示を転記し、推定していません。取扱い・販売地域・最新表示は店頭で確認してください。'
    if '要確認' in unit: note+=' 栄養表示の基準量を機械的に特定できていません。'
    src=source_key or url
    row=dict(id='auto_'+hashlib.sha256(task_key(store,src).encode()).hexdigest()[:20],store=store,name=name,category=guess_category(name),
             unit=unit,url=url,source_key=src,checked=str(date.today()),note=note,price=price,
             p=vals.get('p'),f=vals.get('f'),c=vals.get('c'),kcal=vals.get('kcal'),auto=True,source_method=method)
    try: validate([row])
    except Exception: return None
    return row

def rows_and_links_from_json(store,base_url,obj):
    rows=[]; links=[]; seen_rows=set()
    for node in walk_json(obj):
        if not isinstance(node,dict): continue
        name=product_name_from_dict(node)
        n=nutrition_from_dict(node)
        u=product_url_from_dict(store,node,base_url)
        if u: links.append(u)
        if not name or not n: continue
        vals={k:n.get(k) for k in ('p','f','c','kcal')}
        source=u or base_url+'#json:'+hashlib.sha256((name+str(get_any(node,['sku','id','productId','code']) or '')).encode()).hexdigest()[:16]
        row_url=u or base_url
        row=row_from_values(store,row_url,name,vals,n.get('unit',''),price_from_dict(node),'JSON/構造化データ',source)
        if row and source not in seen_rows:
            seen_rows.add(source); rows.append(row)
    return rows,links

def parse_html_products(store,url,html):
    parser=ProductHTML(); parser.feed(html)
    rows=[]; links=[]
    # Structured data / Next.js / Nuxt data is the highest-confidence generic route.
    for blob in json_blobs(html):
        rr,ll=rows_and_links_from_json(store,url,blob); rows.extend(rr); links.extend(ll)
    # HTML fallback. Require a plausible product name plus a real protein value from page text.
    h1=[h for h in parser.headings if h[0]=='h1' and h[1]]
    name=(h1[0][1] if len(h1)==1 else '') or parser.metas.get('og:title','') or parser.title
    name=re.split(r'[|｜]| - ',name)[0].strip()
    body=' '.join(parser.texts)
    nc=nutrition_candidates_from_text(body)
    generic_name=bool(re.fullmatch(r'.{0,8}(?:商品一覧|商品情報|商品検索|商品を探す|オンラインストア|食品一覧).{0,8}',name or ''))
    detail_priority=page_priority(store,url,name,{})
    plausible_detail=(detail_priority is not None and detail_priority<=1) or (len(h1)==1 and len(nc)==1 and not generic_name)
    if name and nc and not generic_name and plausible_detail:
        best=nc[0]
        # If two distinct nutrition blocks have equally strong evidence but different values, reject
        # the HTML fallback rather than risk mixing serving sizes. Structured rows above are retained.
        ambiguous=len(nc)>1 and nc[1][0]>=best[0] and (nc[1][1],nc[1][2])!=(best[1],best[2])
        if not ambiguous:
            score,vals,unit,section=best
            before=body[:max(0,body.find(section[:40]))] if section else body
            pm=re.search(r'(?:税込(?:価格)?\s*)?[¥￥]?\s*(\d[\d,]*(?:\.\d+)?)\s*円',before[-2000:])
            package_price=float(pm.group(1).replace(',','')) if pm else None
            price=package_price if unit and re.search(r'1\s*(?:包装|袋|個|本|食|カップ|パック|枚|粒|製品)',unit) else None
            row=row_from_values(store,url,name,vals,unit,price,'HTML栄養表示',url)
            if row: rows.append(row)
    # Deduplicate rows from multiple extraction methods; prefer structured data.
    bykey={}
    for r in rows:
        key=r.get('source_key') or r['url']
        if key not in bykey or r.get('source_method','').startswith('JSON'): bykey[key]=r
    return list(bykey.values()),links,parser

def parse_sitemap(store,url,text,profile):
    locs=[unescape(x.strip()) for x in re.findall(r'<loc\b[^>]*>(.*?)</loc\s*>',text,re.I|re.S)]
    if not locs: return []
    sitemap_index=bool(re.search(r'<sitemapindex\b',text,re.I))
    candidates=[]; unknown=[]
    for raw in locs[:60000]:
        u=canonical(urljoin(url,re.sub(r'<[^>]+>','',raw)),store)
        if not u: continue
        pr=page_priority(store,u,'',profile)
        if pr is None: continue
        if sitemap_index or pr==-10:
            candidates.append((-10,u,'sitemap'))
        elif pr<=2:
            candidates.append((pr,u,'html'))
        else:
            unknown.append((int(hashlib.sha1(u.encode()).hexdigest()[:8],16),u))
    if not sitemap_index:
        # Controlled exploration lets an unknown retailer teach us its product URL pattern without
        # crawling the whole corporate site.
        for _,u in sorted(unknown)[:SITEMAP_EXPLORATION]: candidates.append((5,u,'html'))
    else:
        # Sitemap indexes can contain hundreds of sections. Prefer product-ish maps, sample the rest.
        preferred=[x for x in candidates if PRODUCT_HINT_RE.search(urlparse(x[1]).path)]
        others=[x for x in candidates if x not in preferred]
        candidates=(preferred[:MAX_SITEMAPS_PER_STORE]+others[:12])
    return candidates

def shared_base_requires_evidence(store,host):
    # If this exact configured host belongs to only one retailer, the hostname itself is evidence.
    exact={s for s,hosts in STORE_HOSTS.items() if host in hosts}
    if len(exact)==1 and store in exact: return False
    return len(BASE_STORES.get(registrable_base(host),set()))>1

def chain_evidence_ok(store,url,parser):
    host=urlparse(url).hostname
    if not shared_base_requires_evidence(store,host): return True
    hay=norm(url+' '+' '.join(parser.texts[:500])+' '+parser.title)
    return any(norm(a) in hay for a in STORE_ALIASES.get(store,set()))

class CollectorRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class OfficialFetcher:
    def __init__(self):
        self.robots={}; self.robot_text={}; self.last={}; self.host_locks={}; self.meta_lock=threading.Lock()
    def host_lock(self,host):
        with self.meta_lock:
            lock=self.host_locks.get(host)
            if lock is None: lock=threading.Lock(); self.host_locks[host]=lock
            return lock
    def raw(self,store,url):
        for _ in range(5):
            c=canonical(url,store)
            if not c: raise ValueError('対応外の公式URL')
            try:
                req=Request(c,headers={'User-Agent':COLLECT_UA,'Accept':'text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.5','Accept-Encoding':'identity'})
                with build_opener(CollectorRedirect()).open(req,timeout=18) as response:
                    data=response.read(6000001)
                    if len(data)>6000000: raise ValueError('ページのサイズ上限を超えました')
                    if data[:2]==b'\x1f\x8b' or c.lower().endswith('.gz'):
                        data=gzip.decompress(data)
                        if len(data)>12000000: raise ValueError('展開後のサイズ上限を超えました')
                    charset=response.headers.get_content_charset() or 'utf-8'
                    return data.decode(charset,errors='replace')
            except HTTPError as e:
                if e.code in (301,302,303,307,308):
                    url=urljoin(c,e.headers.get('Location',''))
                    if not canonical(url,store): raise ValueError('対応外の転送先')
                    continue
                raise
        raise ValueError('転送回数の上限を超えました')
    def ensure_robots(self,store,host):
        key=(store,host)
        if key in self.robots: return
        robot=RobotFileParser(); txt=''
        try:
            txt=self.raw(store,'https://'+host+'/robots.txt'); robot.parse(txt.splitlines())
        except HTTPError as e:
            if e.code==404: robot.parse([])
            else: raise ValueError('収集可否を確認できません（robots.txt）')
        except URLError:
            raise ValueError('収集可否を確認できません（robots.txt）')
        self.robots[key]=robot; self.robot_text[key]=txt
    def sitemap_urls(self,store,host):
        self.ensure_robots(store,host)
        txt=self.robot_text.get((store,host),'')
        urls=[]
        for line in txt.splitlines():
            if line.lower().startswith('sitemap:'):
                u=canonical(line.split(':',1)[1].strip(),store)
                if u: urls.append(u)
        for name in ('sitemap.xml','sitemap_index.xml','sitemap-index.xml','wp-sitemap.xml'):
            u=canonical('https://'+host+'/'+name,store)
            if u and u not in urls: urls.append(u)
        return urls[:8]
    def get(self,store,url):
        host=urlparse(url).hostname
        with self.host_lock(host):
            self.ensure_robots(store,host)
            robot=self.robots[(store,host)]
            if not robot.can_fetch(COLLECT_UA,url): raise ValueError('サイトの収集制限により対象外')
            declared=robot.crawl_delay(COLLECT_UA) or robot.crawl_delay('*') or 0
            delay=max(COLLECT_DEFAULT_HOST_DELAY,float(declared))
            if delay>60: raise ValueError('サイト指定の収集間隔が長すぎるため対象外')
            wait_for=delay-(time.monotonic()-self.last.get(host,0))
            if wait_for>0: time.sleep(wait_for)
            text=self.raw(store,url); self.last[host]=time.monotonic(); return text

class CatalogCollector:
    def __init__(self,path):
        self.path=str(path); self.lock=threading.Lock(); self.thread=None
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS products (url TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS job (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS control (id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL, stop INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS profiles (store TEXT PRIMARY KEY, data TEXT NOT NULL)')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=15); db.execute('PRAGMA busy_timeout=15000')
        try:
            with db: yield db
        finally: db.close()
    def snapshot(self):
        with self.db() as db:
            row=db.execute('SELECT data FROM job WHERE id=1').fetchone()
        j=json.loads(row[0]) if row else {}
        if j.get('status')=='収集中' and time.time()-j.get('heartbeat',0)>240: j['status']='中断（自動再開待ち）'
        return j
    def products(self):
        with self.db() as db: return [json.loads(r[0]) for r in db.execute('SELECT data FROM products')]
    def load_profiles(self):
        with self.db() as db:
            return {s:json.loads(d) for s,d in db.execute('SELECT store,data FROM profiles')}
    def save_profiles(self,profiles):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for store,p in profiles.items():
                db.execute('INSERT OR REPLACE INTO profiles VALUES (?,?)',(store,json.dumps(p,ensure_ascii=False)))
    def save(self,j):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            ctl=db.execute('SELECT token,stop FROM control WHERE id=1').fetchone()
            if not ctl or ctl[0]!=j['token']: return False
            j['stop']=bool(ctl[1]); j['heartbeat']=time.time()
            db.execute('INSERT OR REPLACE INTO job VALUES (1,?)',(json.dumps(j,ensure_ascii=False),))
        return True
    def save_products(self,token,rows):
        if not rows: return True
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            ctl=db.execute('SELECT token FROM control WHERE id=1').fetchone()
            if not ctl or ctl[0]!=token: return False
            for row in rows:
                key=task_key(row['store'],source_identity(row))
                db.execute('INSERT OR REPLACE INTO products VALUES (?,?)',(key,json.dumps(row,ensure_ascii=False)))
        return True
    def control(self,token):
        with self.db() as db:
            r=db.execute('SELECT token,stop FROM control WHERE id=1').fetchone()
        return (r[0]==token,bool(r[1])) if r else (False,True)
    def initial_tasks(self,stores,profiles):
        pending=[]
        for store in stores:
            profile=profiles.get(store,{})
            seeds=[]
            # Learned productive list pages are first-class seeds on later runs.
            seeds.extend(profile.get('learned_seeds',[])[:LEARNED_SEED_LIMIT])
            seeds.extend(COLLECT_SOURCES.get(store,[]))
            # Root-derived common product paths improve first-run discovery without a search API.
            roots=COLLECT_SOURCES.get(store,[])
            if roots:
                root=roots[-1] if store in EXTRA_ROOTS else roots[0]
                rp=urlparse(root)
                origin='https://'+rp.hostname+'/'
                if origin not in seeds: seeds.append(origin)
                for part in COMMON_DISCOVERY_PATHS:
                    seeds.append(urljoin(origin,part))
            seen=set()
            for u in seeds:
                c=canonical(u,store)
                if c and c not in seen:
                    seen.add(c); pr=page_priority(store,c,'',profile)
                    if pr is None: pr=3
                    pending.append([store,c,0,pr,'seed'])
        return pending
    def start(self,stores,limit,resume=False,catalog_hint=None):
        with self.lock:
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                r=db.execute('SELECT data FROM job WHERE id=1').fetchone(); old=json.loads(r[0]) if r else {}
                same=old.get('job_version')==COLLECT_JOB_VERSION
                if same and old.get('status')=='収集中' and time.time()-old.get('heartbeat',0)<240: return False
                profiles={s:json.loads(d) for s,d in db.execute('SELECT store,data FROM profiles')}
                # Reconstruct useful route knowledge from the catalog as well. This means a restored
                # JSON backup can teach a fresh collector where successful product URLs lived.
                if catalog_hint:
                    for d in catalog_hint:
                        store=d.get('store'); u=canonical(d.get('url',''),store) if store in stores else ''
                        if not u: continue
                        prof=profiles.setdefault(store,{'learned_seeds':[],'prefix_scores':{},'methods':{}})
                        prefix=path_prefix(u); prof['prefix_scores'][prefix]=max(3,prof['prefix_scores'].get(prefix,0))
                        parent=urlunparse(('https',urlparse(u).hostname,prefix,'','',''))
                        if parent not in prof['learned_seeds']:
                            prof['learned_seeds']=(prof['learned_seeds']+[parent])[:LEARNED_SEED_LIMIT]
                    for ps,pv in profiles.items():
                        db.execute('INSERT OR REPLACE INTO profiles VALUES (?,?)',(ps,json.dumps(pv,ensure_ascii=False)))
                if resume and same and old.get('pending'):
                    j=old
                else:
                    pending=self.initial_tasks(stores,profiles)
                    j=dict(pending=pending,seen=[],counts={s:dict(pages=0,sitemaps=0,added=0,skipped=0,errors=0,discovered=0) for s in stores},
                           limit=COLLECT_LIMIT,errors=[],checked=0,added=0,skipped=0)
                j['limit']=COLLECT_LIMIT; j['job_version']=COLLECT_JOB_VERSION; j['active_stores']=[]; j['stores_done']=0; j['parallel_workers']=COLLECT_WORKERS
                j.update(token=uuid.uuid4().hex,status='収集中',stop=False,heartbeat=time.time())
                db.execute('INSERT OR REPLACE INTO control VALUES (1,?,0)',(j['token'],))
                db.execute('INSERT OR REPLACE INTO job VALUES (1,?)',(json.dumps(j,ensure_ascii=False),))
            self.thread=threading.Thread(target=self.run,args=(j,),daemon=True,name='pfc-autonomous-collector'); self.thread.start(); return True
    def stop(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE'); db.execute('UPDATE control SET stop=1 WHERE id=1')
            r=db.execute('SELECT data FROM job WHERE id=1').fetchone()
            if r:
                j=json.loads(r[0]); j['stop']=True; db.execute('UPDATE job SET data=? WHERE id=1',(json.dumps(j,ensure_ascii=False),))
    def process_task(self,fetcher,profiles,task):
        store,url,depth,priority,origin=task; result=dict(task=task,rows=[],candidates=[],error=None,productive=False)
        profile=profiles.get(store,{})
        try:
            text=fetcher.get(store,url)
            if page_priority(store,url,'',profile)==-10 or re.search(r'<(?:urlset|sitemapindex)\b',text,re.I):
                result['kind']='sitemap'; result['candidates']=parse_sitemap(store,url,text,profile); return result
            result['kind']='html'
            stripped=text.lstrip()
            if stripped.startswith(('{','[')):
                try:
                    blob=json.loads(stripped)
                    rows,json_links=rows_and_links_from_json(store,url,blob)
                    parser=ProductHTML()
                except Exception:
                    rows,json_links,parser=parse_html_products(store,url,text)
            else:
                rows,json_links,parser=parse_html_products(store,url,text)
            if rows and not chain_evidence_ok(store,url,parser): rows=[]
            result['rows']=rows
            candidates=[]
            # robots.txt sitemaps are discovered from every root host, once deduped by the queue.
            if depth==0:
                for su in fetcher.sitemap_urls(store,urlparse(url).hostname): candidates.append((-10,su,'sitemap'))
            for u in json_links:
                pr=page_priority(store,u,'',profile)
                if pr is not None: candidates.append((min(pr,1),u,'html'))
            for href,label in parser.links:
                u=canonical(urljoin(url,href),store)
                if not u: continue
                pr=page_priority(store,u,label,profile)
                if pr is None: continue
                # Deep generic navigation is restricted unless it looks product-related. Sitemap
                # exploration still covers unknown URL patterns independently.
                if depth>=2 and pr>=5: continue
                candidates.append((pr,u,'sitemap' if pr==-10 else 'html'))
            # Inline references to same-organization JSON/API endpoints (when present in page source).
            for m in re.finditer(r'["\']((?:https://[^"\']+|/[^"\']+?)(?:api|products?|goods|items?)[^"\']*?\.json(?:\?[^"\']*)?)["\']',text,re.I):
                u=canonical(urljoin(url,m.group(1)),store)
                if u: candidates.append((0,u,'html'))
            dedup={}
            for pr,u,k in candidates:
                if u!=url and (u not in dedup or pr<dedup[u][0]): dedup[u]=(pr,k)
            ordered=sorted((pr,u,k) for u,(pr,k) in dedup.items())[:900]
            result['candidates']=ordered
            productish=sum(1 for pr,_,_ in ordered if pr<=1)
            result['productive']=productish>=6 or bool(rows)
            return result
        except Exception as e:
            result['error']=e; result['kind']='html'; return result
    def run(self,j,fetcher=None):
        fetcher=fetcher or OfficialFetcher(); stores=list(j['counts']); profiles=self.load_profiles()
        for s in stores: profiles.setdefault(s,{'learned_seeds':[],'prefix_scores':{},'methods':{}})
        existing_rows=self.products()
        existing_keys={s:set() for s in stores}
        for r in existing_rows:
            if r.get('store') in existing_keys: existing_keys[r['store']].add(source_identity(r))
        seen=set(j.get('seen',[])); recent={task_key(r['store'],source_identity(r)) for r in existing_rows if r.get('checked')==str(date.today())}
        heaps={s:[] for s in stores}; seq=0; queued=set()
        for raw in j.get('pending',[]):
            if len(raw)<5: continue
            store,url,depth,pr,origin=raw; key=task_key(store,url)
            if store in heaps and url and key not in seen and key not in queued:
                heapq.heappush(heaps[store],(pr,seq,raw)); seq+=1; queued.add(key)
        active=set(); futures={}; stop_requested=False; last_checkpoint=0.0; completed=0; product_buffer=[]; profile_dirty=False

        def enqueue(store,url,depth,pr,origin):
            nonlocal seq
            key=task_key(store,url)
            if not url or key in seen or key in queued or len(heaps[store])>=MAX_QUEUE_PER_STORE: return
            task=[store,url,depth,int(pr),origin]; heapq.heappush(heaps[store],(int(pr),seq,task)); seq+=1; queued.add(key)

        def next_task(store):
            counts=j['counts'][store]
            while heaps[store]:
                _pr,_seq,task=heapq.heappop(heaps[store]); _,url,depth,pr,origin=task; key=task_key(store,url)
                if key in seen: continue
                # The catalog cap is per retailer in total, not 500 additional products on every run.
                if len(existing_keys[store])>=j['limit']: continue
                kind='sitemap' if pr==-10 or urlparse(url).path.lower().endswith(('.xml','.xml.gz')) or 'sitemap' in urlparse(url).path.lower() else 'html'
                if kind=='sitemap':
                    if counts['sitemaps']>=MAX_SITEMAPS_PER_STORE: continue
                    counts['sitemaps']+=1
                else:
                    if counts['pages']>=MAX_HTML_PAGES_PER_STORE: continue
                    # Re-fetching the exact same product source on the same day adds no value.
                    if key in recent and pr<=1: continue
                    counts['pages']+=1
                return task
            return None

        def checkpoint(force=False,status=None):
            nonlocal last_checkpoint,completed,profile_dirty
            now=time.monotonic()
            if not force and completed<25 and now-last_checkpoint<COLLECT_CHECKPOINT_SECONDS: return True
            if product_buffer:
                if not self.save_products(j['token'],product_buffer): return False
                product_buffer.clear()
            pending=[]
            for task in futures.values(): pending.append(task)
            for s in stores: pending.extend([x[2] for x in heaps[s]])
            j['pending']=pending; j['seen']=list(seen); j['active_stores']=list(active)
            j['stores_done']=sum(not heaps[s] and s not in active for s in stores)
            if status is not None: j['status']=status
            if not self.save(j): return False
            if profile_dirty:
                self.save_profiles(profiles); profile_dirty=False
            last_checkpoint=now; completed=0; return True

        try:
            with ThreadPoolExecutor(max_workers=COLLECT_WORKERS,thread_name_prefix='pfc-auto-store') as pool:
                while True:
                    same_token,stop_flag=self.control(j['token'])
                    if not same_token: return
                    if stop_flag: stop_requested=True
                    if not stop_requested:
                        for store in stores:
                            if len(futures)>=COLLECT_WORKERS: break
                            if store in active: continue
                            task=next_task(store)
                            if not task: continue
                            active.add(store); fut=pool.submit(self.process_task,fetcher,profiles,task); futures[fut]=task
                    if not futures: break
                    done,_=wait(list(futures),timeout=0.7,return_when=FIRST_COMPLETED)
                    if not done:
                        if not checkpoint(): return
                        continue
                    for fut in done:
                        task=futures.pop(fut); store,url,depth,pr,origin=task; active.discard(store); result=fut.result(); counts=j['counts'][store]
                        if result.get('error') is not None:
                            counts['errors']+=1; e=result['error']
                            reason=f'HTTP {e.code}' if isinstance(e,HTTPError) else ('通信タイムアウト' if isinstance(e,TimeoutError) else str(e)[:140])
                            j['errors'].append(dict(store=store,reason=reason,url=url))
                        else:
                            rows=result.get('rows',[])
                            # One list/JSON page may yield several product rows.
                            for row in rows:
                                src=source_identity(row); sk=task_key(store,src)
                                if sk in recent: continue
                                is_existing=src in existing_keys[store]
                                if not is_existing and len(existing_keys[store])>=j['limit']: break
                                if not is_existing: existing_keys[store].add(src)
                                counts['added']+=1; j['added']+=1; product_buffer.append(row); recent.add(sk)
                                prefix=path_prefix(row['url']); prof=profiles[store]; prof['prefix_scores'][prefix]=prof['prefix_scores'].get(prefix,0)+1
                                method=row.get('source_method','unknown'); prof['methods'][method]=prof['methods'].get(method,0)+1; profile_dirty=True
                            if not rows and result.get('kind')=='html': counts['skipped']+=1; j['skipped']+=1
                            if result.get('productive') and url not in profiles[store]['learned_seeds']:
                                profiles[store]['learned_seeds']=[url]+profiles[store]['learned_seeds'][:LEARNED_SEED_LIMIT-1]; profile_dirty=True
                            if depth<MAX_DEPTH and len(existing_keys[store])<j['limit']:
                                for cpr,u,kind in result.get('candidates',[]):
                                    ndepth=depth+(0 if kind=='sitemap' and result.get('kind')=='sitemap' else 1)
                                    if ndepth>MAX_DEPTH: continue
                                    # Learned successful prefixes are promoted automatically.
                                    for prefix,score in profiles[store].get('prefix_scores',{}).items():
                                        if score>=2 and urlparse(u).path.startswith(prefix): cpr=min(cpr,0); break
                                    enqueue(store,u,ndepth,cpr,url)
                                    counts['discovered']+=1
                        seen.add(task_key(store,url)); j['checked']+=1; completed+=1; j['errors']=j['errors'][-250:]
                    if not checkpoint(): return
                final='一時停止' if stop_requested else '完了'
                checkpoint(force=True,status=final)
        except Exception as e:
            j['status']='中断（自動再開待ち）'; j['errors'].append(dict(store='収集処理',reason=str(e)[:160],url=''))
            try: checkpoint(force=True,status=j['status'])
            except Exception: pass

@st.cache_resource
def collector(resource_version):
    # Version in cache key prevents a hot-reloaded Streamlit process from reusing old collector code.
    return CatalogCollector(Path(tempfile.gettempdir())/'pfc_public_catalog_v3.sqlite3')

def sync_public_catalog():
    incoming=collector(COLLECT_JOB_VERSION).products()
    bykey={}
    for i,d in enumerate(st.session_state.catalog):
        src=d.get('source_key') or (canonical(d.get('url',''),d.get('store')) if d.get('url') and d.get('store') else '')
        if src: bykey[task_key(d['store'],src)]=i
    for d in incoming:
        src=source_identity(d); key=task_key(d['store'],src); i=bykey.get(key)
        if i is None:
            bykey[key]=len(st.session_state.catalog); st.session_state.catalog.append(d)
        elif st.session_state.catalog[i].get('auto'):
            d=dict(d,id=st.session_state.catalog[i]['id']); st.session_state.catalog[i]=d

def collection_store_progress(j):
    stores=list(j.get('counts',{}))
    active=list(j.get('active_stores',[]))
    done=int(j.get('stores_done',0))
    if not done and stores:
        pending={task[0] for task in j.get('pending',[]) if task}
        done=sum(store not in pending and store not in active for store in stores)
    return stores,active,done

def protein_value(d):
    p,price=d.get('p'),d.get('price')
    if p is None or price is None or p<=0 or price<=0 or '要確認' in d.get('unit',''): return None
    return 100*p/price

@st.fragment(run_every=3)
def collection_status():
    try:
        c=collector(COLLECT_JOB_VERSION); j=c.snapshot()
        if not j or j.get('job_version')!=COLLECT_JOB_VERSION: return
        # A server sleep/restart should not require the user to discover and press a resume button.
        # Manual pause remains paused; only stale/interrupted autonomous jobs are resumed.
        if j.get('status')=='中断（自動再開待ち）' and j.get('pending'):
            try:
                c.start(COLLECT_STORES,COLLECT_LIMIT,resume=True,catalog_hint=st.session_state.catalog)
                j=c.snapshot()
            except Exception:
                pass
        sync_public_catalog()
        stores,active,done=collection_store_progress(j)
        if j.get('status')=='収集中':
            current=(sorted(active,key=lambda x:stores.index(x) if x in stores else 999)[0] if active else '準備中')
            more=(f'ほか{len(active)-1}店' if len(active)>1 else '')
            st.caption(f"収集中：{done}/{len(stores)}店舗完了｜現在：{current}{more}｜取得・更新 {j.get('added',0)}件")
        elif j.get('status')=='一時停止':
            st.caption(f"一時停止：{done}/{len(stores)}店舗完了｜取得・更新 {j.get('added',0)}件")
        elif j.get('pending'):
            st.caption(f"再開準備中：{done}/{len(stores)}店舗完了｜取得・更新 {j.get('added',0)}件")
        else:
            st.caption(f"収集完了：{len(stores)}/{len(stores)}店舗｜取得・更新 {j.get('added',0)}件")
    except Exception:
        st.warning('収集状況を読み込めません。画面を再読み込みしてください。')


def main():
    st.set_page_config(page_title='PFCえらび',page_icon='🥗',layout='centered')
    st.markdown('''<style>
    .stApp{background:#f5f7f4;color:#233831} .block-container{padding-top:3.5rem;padding-bottom:3rem;max-width:760px}
    h1,h2,h3,p,label{color:inherit} .hero{background:#e2eee7;padding:24px;border-radius:22px;margin-bottom:20px}
    .hero h1{font-size:1.9rem;margin:0;color:#205543}.hero p{margin:8px 0 0;color:#3c6556}
    div.stButton>button{border-radius:12px;min-height:46px} div.stButton>button[kind=primary]{background:#27755e;color:white;border:0}
    [data-testid=stVerticalBlockBorderWrapper]{border-radius:16px}
    @media(prefers-color-scheme:dark){.stApp{background:#15221e;color:#e5eee8}.hero{background:#233c31}.hero h1,.hero p{color:#e5eee8}}
    </style>''',unsafe_allow_html=True)
    for key,default in [('catalog',SEEDS),('cart',{}),('favorites',[]),('page','ホーム')]:
        if key not in st.session_state: st.session_state[key]=json.loads(json.dumps(default))
    try: sync_public_catalog()
    except Exception: st.warning('収集済みデータを読み込めません。登録データで検索できます。')
    st.markdown('<div class="hero"><h1>🥗 PFCえらび</h1><p>いつものお店で、たんぱく質をプラス。</p></div>',unsafe_allow_html=True)
    st.caption(f'v4.0｜{len(COLLECT_STORES)}店舗・各店最大{COLLECT_LIMIT}商品｜自律収集・精度優先')
    if st.session_state.page!='ホーム' and st.button('◀ トップページに戻る',use_container_width=True):
        st.session_state.page='ホーム'; st.rerun()
    collection_status()
    page=st.session_state.page
    if page=='ホーム':
        st.write('お店を選んで商品を比較。食べる組み合わせのPFCも確認できます。')
        collect_stores=COLLECT_STORES
        collect_limit=COLLECT_LIMIT
        try:
            state=collector(COLLECT_JOB_VERSION).snapshot()
            running=state.get('job_version')==COLLECT_JOB_VERSION and state.get('status')=='収集中'
        except Exception:
            state={}
            running=False

        start_clicked=st.button('📥 商品を収集する',type='primary',disabled=running,use_container_width=True)
        started=False
        startup_failed=False
        if start_clicked:
            if not collect_stores:
                st.warning('収集するお店を選択してください。')
            else:
                try:
                    started=collector(COLLECT_JOB_VERSION).start(collect_stores,collect_limit,catalog_hint=st.session_state.catalog)
                except Exception:
                    startup_failed=True
                    st.error('商品収集を開始できませんでした。ページを再読み込みして、もう一度お試しください。')
                if not started and not running and not startup_failed:
                    # A second click can race with the just-started worker; just reflect its current state.
                    latest=collector(COLLECT_JOB_VERSION).snapshot()
                    running=(latest.get('job_version')==COLLECT_JOB_VERSION and latest.get('status')=='収集中')
        # Important: st.rerun() must not be inside the try/except above. Streamlit uses a
        # control-flow exception for reruns, which can otherwise be mistaken for an app error.
        if started:
            st.rerun()
        for label in ['🔎 お店から探す','🍽 組み合わせを見る','♡ お気に入り','＋ 商品を追加・編集','💾 保存・復元']:
            if st.button(label,use_container_width=True): st.session_state.page=label; st.rerun()
        st.caption(f'登録商品 {len(st.session_state.catalog)}件｜初期データ確認日 2026/9/6')
        st.caption('公開された栄養情報を取得できた商品を登録します。全店での取得や在庫を保証するものではありません。')
        return
    if page=='💾 保存・復元':
        st.subheader('データを保存・復元')
        st.info('収集した公式商品はサーバーに保存しますが、休止・再デプロイ等で保存領域が消える場合があります。追加商品・お気に入りも含め、終了前に保存しておくと復元できます。')
        payload={k:st.session_state[k] for k in ('catalog','favorites','cart')}
        st.download_button('データを保存',json.dumps(payload,ensure_ascii=False,indent=2),'pfc_backup.json','application/json',use_container_width=True)
        f=st.file_uploader('保存ファイルを読み込む',type=['json'])
        if f and st.button('復元する'):
            try:
                if f.size>20000000: raise ValueError('ファイルは20MB以内にしてください。')
                data=json.load(f); rows=validate(data['catalog']); ids={d['id'] for d in rows}
                fav=data.get('favorites',[]); cart=data.get('cart',{})
                if not isinstance(fav,list) or any(x not in ids for x in fav): raise ValueError('お気に入りが不正です。')
                if not isinstance(cart,dict) or any(k not in ids or type(v) not in (int,float) or not math.isfinite(v) or not 0<v<=100 for k,v in cart.items()): raise ValueError('組み合わせが不正です。')
                st.session_state.catalog=rows; st.session_state.favorites=fav; st.session_state.cart=cart
                st.success('復元しました。')
            except (ValueError,KeyError,TypeError) as e: st.error(f'復元できません：{e}')
        return
    if page=='＋ 商品を追加・編集':
        st.subheader('商品を追加・編集')
        mode=st.radio('操作',['新しく追加','登録商品を編集'],horizontal=True)
        old=None
        if mode=='登録商品を編集':
            oldid=st.selectbox('商品', [d['id'] for d in st.session_state.catalog],format_func=lambda i:next(d['name'] for d in st.session_state.catalog if d['id']==i))
            old=next(d for d in st.session_state.catalog if d['id']==oldid)
        d=old or dict(name='',store=st.session_state.get('new_store',STORES[0]),category=CATEGORIES[0],unit='1包装',url='',note='',p=None,f=None,c=None,kcal=None,price=None)
        with st.expander('公式ページの栄養表示を確認'):
            url=st.text_input('公式商品ページURL',value=d['url'])
            if st.button('公式ページを読み込む'):
                try:
                    with st.spinner('公式の栄養表示を確認中…'): section,values=fetch_official(url)
                    if not section: st.warning('栄養表示を抽出できません。商品パッケージをご確認ください。')
                    else:
                        st.text(section); st.write({k:fmt(v,'kcal' if k=='kcal' else 'g') for k,v in values.items()})
                        st.info('抽出値は参考表示です。100g当たり／1包装当たりを確認して、下の欄に入力してください。')
                except Exception: st.warning('公式ページを取得できませんでした。公式サイトかパッケージで確認して入力できます。')
        with st.form('edit_'+(d.get('id') or 'new')):
            name=st.text_input('商品名',value=d['name'])
            store=st.selectbox('お店',STORES,index=STORES.index(d['store']))
            cat=st.selectbox('ジャンル',CATEGORIES,index=CATEGORIES.index(d['category']))
            unit=st.text_input('栄養値の単位（例：1包装110g、100g）',value=d['unit'])
            st.caption('未確認の数値は空欄にしてください。P・F・C・カロリーは同じ単位で入力。価格はその単位に対応する金額です。')
            values={}
            for key,label in [('p','P たんぱく質（g）'),('f','F 脂質（g）'),('c','C 炭水化物（g）'),('kcal','カロリー（kcal）'),('price','税込価格（円）')]:
                values[key]=st.text_input(label,value='' if d[key] is None else str(d[key]))
            source=st.text_input('出典URL（任意）',value=d['url'])
            note=st.text_input('メモ・スーパー名・販売地域',value=d['note'])
            ok=st.checkbox('商品表示と入力値・単位を確認しました')
            if st.form_submit_button('商品を保存',type='primary',use_container_width=True):
                try:
                    if not name.strip() or not unit.strip() or not ok: raise ValueError('商品名・単位を入力し、確認にチェックしてください。')
                    row=dict(id=d.get('id') or uuid.uuid4().hex,name=name.strip(),store=store,category=cat,unit=unit,url=source.strip(),note=note,checked=str(date.today()),**{k:float(v) if v.strip() else None for k,v in values.items()})
                    validate([row]); st.session_state.catalog=[x for x in st.session_state.catalog if x['id']!=row['id']]+[row]
                    st.success('保存しました。「保存・復元」からデータをダウンロードすると次回も使用できます。')
                except ValueError as e: st.error(str(e))
        return
    if page=='🍽 組み合わせを見る':
        st.subheader('食べる組み合わせ')
        rows=[d for d in st.session_state.catalog if d['id'] in st.session_state.cart]
        if not rows: st.info('「お店から探す」で商品を追加してください。'); return
        totals={k:0. for k in ('p','f','c','kcal','price')}; missing=set()
        for d in rows:
            with st.container(border=True):
                st.write(d['name']); st.caption(d['unit'])
                n=st.number_input('食べる量（表示単位の何倍か）',.25,100.,float(st.session_state.cart[d['id']]),.25,key='qty_'+d['id'])
                st.session_state.cart[d['id']]=n
                if st.button('外す',key='remove_'+d['id']): del st.session_state.cart[d['id']]; st.rerun()
                for k in totals:
                    if d[k] is None: missing.add(k)
                    else: totals[k]+=n*d[k]
        for k in missing: totals[k]=None
        st.write('**合計**'); st.write(f"P {fmt(totals['p'])} ／ F {fmt(totals['f'])} ／ C {fmt(totals['c'])}")
        st.write(f"{fmt(totals['kcal'],'kcal')} ・ {fmt(totals['price'],'円')}（食べる量相当）")
        chart(totals)
        if missing: st.caption('未確認値を含む項目は、合計も未確認として表示しています。')
        st.caption('PFC比率はP×4・F×9・C×4から算出。食品表示のカロリーとは一致しない場合があります。')
        return
    st.subheader('お気に入り' if page=='♡ お気に入り' else 'お店から探す')
    group=st.radio('お店の種類',['すべて','コンビニ','スーパー'],horizontal=True,key='store_group')
    choices=['すべてのお店']+(STORE_GROUPS['コンビニ']+STORE_GROUPS['スーパー'] if group=='すべて' else STORE_GROUPS[group])
    selected=st.selectbox('どのお店で探しますか？',choices,format_func=lambda name:name if name=='すべてのお店' else store_label(name),key='store_choice_'+group)
    stores=choices[1:] if selected=='すべてのお店' else [selected]
    st.caption('店名を選ぶと、そのお店の登録商品に切り替わります。商品数は登録データの件数で、在庫数ではありません。')
    with st.form('search'):
        with st.expander('商品名でさらに絞る（任意）'):
            q=st.text_input('商品名・キーワード',placeholder='入力しなくても検索できます')
        cat=st.selectbox('ジャンル',['すべて']+CATEGORIES)
        sort=st.selectbox('並び順',['たんぱく質のコスパ順（100円当たり）','たんぱく質が多い順','PFC目標比率に近い順','価格が安い順'])
        with st.expander('詳しい条件'):
            minp=st.number_input('たんぱく質の下限（g）',0.,100.,0.,5.)
            maxf=st.number_input('脂質の上限（g・0で指定なし）',0.,100.,0.,5.)
            maxk=st.number_input('カロリーの上限（kcal・0で指定なし）',0.,3000.,0.,100.)
            budget=st.number_input('価格の上限（円・0で指定なし）',0.,10000.,0.,100.)
            st.caption('PFC目標は比較用の初期設定です。ご自身の目標に変更できます。')
            tp=st.slider('目標P（%）',5,60,20,5); tf=st.slider('目標F（%）',5,60,25,5)
            st.caption(f'目標C：{100-tp-tf}% ｜ P+Fは100%未満にしてください。')
        submit=st.form_submit_button('この条件で検索',type='primary',use_container_width=True)
    if submit or 'filters' not in st.session_state or len(st.session_state.filters)!=9:
        if tp+tf>=100: st.error('P+Fが100%未満になるよう変更してください。'); return
        st.session_state.filters=(q,cat,minp,maxf,maxk,budget,sort,tp,tf)
    q,cat,minp,maxf,maxk,budget,sort,tp,tf=st.session_state.filters
    rows=filter_items(st.session_state.catalog,stores,q,cat,minp,maxf,maxk,budget)
    if page=='♡ お気に入り': rows=[d for d in rows if d['id'] in st.session_state.favorites]
    if sort=='PFC目標比率に近い順':
        rows=[d for d in rows if ratios(d) is not None]; rows.sort(key=lambda d:distance(d,[tp,tf,100-tp-tf]))
    elif sort=='価格が安い順': rows.sort(key=lambda d:d['price'] if d['price'] is not None else float('inf'))
    elif sort in ('たんぱく質のコスパ順（100円当たり）','100円当たりのたんぱく質が多い順'):
        rows=[d for d in rows if protein_value(d) is not None]; rows.sort(key=protein_value,reverse=True)
        st.caption('100円で摂れるたんぱく質が多い順です。価格・栄養値の対応単位が未確認の商品は除外します。')
    else: rows.sort(key=lambda d:d['p'] if d['p'] is not None else -1,reverse=True)
    st.caption(f'{len(rows)}件 ｜ 栄養値・価格は各カードの表示単位当たり。条件判定に必要な値が未確認の商品は除外します。')
    if not rows:
        registered=any(d['store'] in stores for d in st.session_state.catalog)
        if not registered:
            st.info('選んだお店の商品はまだ登録されていません。店名の選択には対応していますが、商品情報は未収録です。')
            if st.button('このお店の商品を追加する',use_container_width=True):
                if selected!='すべてのお店': st.session_state.new_store=selected
                st.session_state.page='＋ 商品を追加・編集'; st.rerun()
        else: st.info('この条件に該当する登録商品がありません。絞り込み条件をご確認ください。')
    page_count=max(1,math.ceil(len(rows)/20))
    result_page=st.selectbox('表示ページ',list(range(1,page_count+1)),key='results_page') if page_count>1 else 1
    for d in rows[(result_page-1)*20:result_page*20]:
        with st.container(border=True):
            st.caption(d['store']+' ・ '+d['category']); st.markdown('#### '+escape(d['name']))
            st.write(f"**P {fmt(d['p'])}** ／ F {fmt(d['f'])} ／ C {fmt(d['c'])}")
            st.write(f"{fmt(d['kcal'],'kcal')} ・ {fmt(d['price'],'円')}"); st.caption(d['unit']); chart(d)
            value=protein_value(d)
            if value is not None:
                st.write(f"**100円当たり たんぱく質 {value:.1f}g**")
                st.caption(f"たんぱく質1g当たり {d['price']/d['p']:.2f}円")
            else: st.caption('たんぱく質のコスパ：計算に必要な価格・栄養値・単位が未確認、またはたんぱく質0g')
            a,b=st.columns(2)
            if a.button('＋ 組み合わせ',key='add_'+d['id'],use_container_width=True):
                st.session_state.cart[d['id']]=min(100.,st.session_state.cart.get(d['id'],0)+1); st.toast('組み合わせに追加しました')
            favorite=d['id'] in st.session_state.favorites
            if b.button('♥ 登録済み' if favorite else '♡ お気に入り',key='fav_'+d['id'],use_container_width=True):
                if favorite: st.session_state.favorites.remove(d['id'])
                else: st.session_state.favorites.append(d['id'])
                st.rerun()
            with st.expander('出典・確認日'):
                st.caption('確認日：'+d['checked']); st.write(d['note'] or '取扱い・価格・成分は店舗の商品表示をご確認ください。')
                if safe_link(d['url']): st.link_button('商品情報を開く',d['url'])
    with st.expander('登録されていない商品をWebで探す'):
        st.caption('外部検索を開きます。見つかった商品は「商品を追加・編集」で登録できます。')
        for store in stores:
            domain=next((k for k,v in DOMAINS.items() if v==store),'')
            query=(f'site:{domain} ' if domain else store+' ')+(q or 'たんぱく質 栄養成分')
            st.link_button(store+'の商品を検索','https://www.google.com/search?q='+quote(query))
    st.caption('P＝たんぱく質、F＝脂質、C＝炭水化物。比率は4・9・4kcal/gで算出した目安です。商品単体の比率だけで食事全体の良し悪しは判断しません。')

if __name__=='__main__': main()

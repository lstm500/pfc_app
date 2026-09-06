"""PFCえらび / Streamlit. Run: streamlit run app.py"""
import streamlit as st
import json, math, re, uuid, unicodedata
from datetime import date
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

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
import sqlite3, threading, time, hashlib, tempfile
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urljoin, urlunparse, parse_qsl, urlencode
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser

COLLECT_SOURCES = {
    STORES[0]: ['https://www.sej.co.jp/products/a/itemresult/?'+urlencode(dict(key=k,limit=100,p=1)) for k in ['たんぱく質','チキン','サラダ','おにぎり','魚','豆腐','ヨーグルト']],
    STORES[1]: ['https://www.lawson.co.jp/recommend/original/select/salad/index.html','https://www.lawson.co.jp/recommend/original/rice/'],
    STORES[2]: ['https://www.family.co.jp/goods/sidedishes.html','https://www.family.co.jp/goods.html'],
    STORES[3]: ['https://www.topvalu.net/items/list/100400600/','https://www.topvalu.net/items/list/100200500/','https://www.topvalu.net/items/'],
}
# Every named chain is visited; "その他" is a manual-registration category, not a retailer.
EXTRA_ROOTS = {'ナチュラルローソン': 'https://natural.lawson.co.jp/', 'ローソンストア100': 'https://store100.lawson.co.jp/', 'ミニストップ': 'https://www.ministop.co.jp/', 'デイリーヤマザキ': 'https://www.daily-yamazaki.jp/', 'NewDays': 'https://retail.jr-cross.co.jp/newdays/', 'セイコーマート': 'https://www.seicomart.co.jp/', 'ポプラ': 'https://www.poplar-cvs.co.jp/', 'オーケー（OKストア）': 'https://ok-corporation.jp/', 'イオンスタイル': 'https://www.aeonretail.jp/', 'まいばすけっと': 'https://www.mybasket.co.jp/', 'マックスバリュ': 'https://onlinestore.maxvalu.co.jp/', 'ダイエー': 'https://www.daiei.co.jp/', 'ピーコックストア': 'https://aeonmarket.co.jp/', '西友': 'https://www.seiyu.co.jp/', 'ライフ': 'https://www.lifecorp.jp/', 'サミット': 'https://www.summitstore.co.jp/', 'マルエツ': 'https://www.maruetsu.co.jp/', 'マルエツ プチ': 'https://www.maruetsu.co.jp/', 'イトーヨーカドー': 'https://www.itoyokado.co.jp/', 'ヨークフーズ': 'https://www.york-inc.com/', 'ヨークマート': 'https://www.york-inc.com/', 'ヨークベニマル': 'https://yorkbenimaru.com/', 'オオゼキ': 'https://www.ozeki-net.co.jp/', '東急ストア': 'https://www.tokyu-store.co.jp/', '東武ストア': 'https://www.tobustore.co.jp/', '京急ストア': 'https://www.keikyu-store.co.jp/', 'いなげや': 'https://www.inageya.co.jp/', 'コモディイイダ': 'https://www.comodi-iida.co.jp/', '文化堂': 'https://www.bunkado.com/', '三徳': 'https://santoku.co.jp/', '肉のハナマサ': 'https://www.hanamasa.co.jp/', '業務スーパー': 'https://www.gyomusuper.jp/', 'ベルク': 'https://www.belc.jp/', 'ベルクス': 'https://sunbelx.com/', 'ヤオコー': 'https://www.yaoko-net.com/', 'ロピア': 'https://lopia.jp/', 'コープ': 'https://goods.jccu.coop/', '成城石井': 'https://www.seijoishii.com/', '紀ノ国屋': 'https://www.e-kinokuniya.com/', 'クイーンズ伊勢丹': 'https://www.im-food.co.jp/', '明治屋': 'https://www.meidi-ya.co.jp/', 'ビオセボン': 'https://www.bio-c-bon.jp/', 'オーガニックスーパー ビオラル': 'https://www.lifecorp.jp/bio-ral/', '万代': 'https://www.mandai-net.co.jp/', '阪急オアシス': 'https://hankyu-oasis.kansai-foodmarket.co.jp/', '関西スーパー': 'https://www.kansaisuper.co.jp/', '平和堂': 'https://www.heiwado.jp/', 'バロー': 'https://valor.jp/', 'アピタ': 'https://www.uny.co.jp/', 'ピアゴ': 'https://www.uny.co.jp/', 'ゆめタウン': 'https://www.izumi.jp/', 'ゆめマート': 'https://www.izumi.jp/', 'サンリブ': 'https://www.sunlive.co.jp/', 'ハローズ': 'https://www.halows.com/', 'ラ・ムー': 'https://www.dkt-s.com/', 'ディオ': 'https://www.dkt-s.com/', 'トライアル': 'https://www.trial-net.co.jp/', 'コストコ': 'https://www.costco.co.jp/', 'ドン・キホーテ': 'https://www.donki.com/'}
ORIGINAL_HOSTS=set(DOMAINS)
STORE_HOSTS={store:{urlparse(url).hostname for url in urls} for store,urls in COLLECT_SOURCES.items()}
for store,root in EXTRA_ROOTS.items():
    COLLECT_SOURCES[store]=[root]
    host=urlparse(root).hostname
    aliases={host}
    # Accept the conventional www redirect, without allowing arbitrary subdomains.
    if host.startswith('www.'): aliases.add(host[4:])
    elif host.count('.')==1 or host.endswith('.co.jp'): aliases.add('www.'+host)
    STORE_HOSTS[store]=aliases
    for alias in aliases: DOMAINS.setdefault(alias,store)
COLLECT_SOURCES['その他スーパー']=[]
# Collect every named retailer in the store list. 'その他スーパー' is a generic manual category.
COLLECT_STORES=[store for store in STORES if store!='その他スーパー']
COLLECT_LIMIT=500
COLLECT_JOB_VERSION=5

COLLECT_UA='PFCProductCollector/1.0'

class ProductHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.texts=[]; self.links=[]; self.headings=[]; self.stack=[]; self.title=''; self.skip=0; self.capture=None; self.anchor=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style','noscript'): self.skip+=1
        if self.skip: return
        if tag=='meta' and a.get('property')=='og:title': self.title=a.get('content','')
        if tag in ('h1','h2','title'): self.capture=[tag,[],len(self.texts)]
        if tag=='a': self.anchor=[a.get('href',''),[]]
        if tag=='img' and self.anchor and a.get('alt'): self.anchor[1].append(a['alt'])
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'): self.skip=max(0,self.skip-1)
        if self.capture and tag==self.capture[0]:
            kind,parts,offset=self.capture; title=' '.join(parts).strip()
            if kind=='title' and not self.title: self.title=title
            if kind!='title': self.headings.append((kind,title,offset))
            self.capture=None
        if tag=='a' and self.anchor:
            self.links.append((self.anchor[0],' '.join(self.anchor[1]))); self.anchor=None
    def handle_data(self,data):
        if self.skip or not data.strip(): return
        v=unicodedata.normalize('NFKC',data).strip(); self.texts.append(v)
        if self.capture: self.capture[1].append(v)
        if self.anchor: self.anchor[1].append(v)

def task_key(store,url): return store+'|'+url

def canonical(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in DOMAINS or p.username or p.password or p.port not in (None,443): return ''
    if p.hostname not in ORIGINAL_HOSTS:
        query=urlencode(sorted((k,v) for k,v in parse_qsl(p.query) if not k.startswith('utm_')))
        return urlunparse(('https',p.hostname,p.path or '/', '',query,''))
    path=p.path.replace('/sp/recommend/','/recommend/')
    # Normalize only identities of detail pages; keep list pagination parameters.
    host='www.lawson.co.jp' if p.hostname=='mldata.lawson.co.jp' else p.hostname
    query='' if re.search(r'/(?:item|detail)/',path) or re.search(r'/goods/[^/]+/\d+\.html',path) else urlencode(sorted(parse_qsl(p.query)))
    return urlunparse(('https',host,path.rstrip('/')+'/' if not path.endswith('.html') else path,'',query,''))

def page_kind(url):
    p=urlparse(url); path=p.path
    if p.hostname=='www.sej.co.jp':
        if re.fullmatch(r'/products/a/item/\d+/',path): return 'detail'
        if path.startswith('/products/a/') and ('itemresult' in path or '/cat/' in path): return 'list'
    if p.hostname=='www.lawson.co.jp' and path.startswith('/recommend/original/'):
        return 'detail' if re.fullmatch(r'/recommend/original/detail/\d+_\d+\.html',path) else 'list'
    if p.hostname=='www.family.co.jp':
        if re.fullmatch(r'/goods/[^/]+/\d+\.html',path): return 'detail'
        if re.fullmatch(r'/goods(?:/[a-z_]+)?\.html',path) and not re.search(r'(safety|daily|convenience|cosme|liquor)',path): return 'list'
    if p.hostname=='www.topvalu.net':
        if re.fullmatch(r'/items/detail/\d+/',path): return 'detail'
        if path=='/items/' or re.fullmatch(r'/items/list/\d+/',path): return 'list'
    if p.hostname in DOMAINS and p.hostname not in ORIGINAL_HOSTS:
        if re.search(r'\.(?:pdf|jpg|png|gif|zip|css|js|svg)$',path,re.I): return ''
        if re.search(r'login|cart|checkout|contact|recruit|privacy|recipe|news|ir/',path,re.I): return ''
        if re.search(r'(?:product|goods|item|shohin|commodity|brand|select|food|lineup)',path,re.I):
            return 'generic'
        return 'list'
    return ''

def guess_category(name):
    for pattern,cat in [('ヨーグルト|チーズ|牛乳',5),('サラダチキン|鶏|チキン|ささみ|豚|ハム|牛肉',0),('サラダ',3),('おにぎり|おむすび|ご飯|弁当|麺|パン|パスタ|そば|うどん',4),('豆腐|納豆|たまご|玉子|卵|大豆',2),('さば|鮭|魚|海老|えび|ツナ|いか|かに',1),('ドリンク|飲料|豆乳',6),('バー|ナッツ|菓子|チョコ',7)]:
        if re.search(pattern,name): return CATEGORIES[cat]
    return CATEGORIES[-1]

def parse_product(url,html):
    parser=ProductHTML(); parser.feed(html)
    expected=re.split(r'[|｜]| -イオン| - イオン',unicodedata.normalize('NFKC',parser.title))[0].strip()
    matches=[h for h in parser.headings if h[1] and (not expected or norm(h[1])==norm(expected))]
    if not matches and urlparse(url).hostname not in ORIGINAL_HOSTS:
        h1s=[h for h in parser.headings if h[0]=='h1']
        if len(h1s)==1: matches=h1s
    if not matches: return None,'商品見出しを特定できません'
    kind,name,offset=matches[0]
    if len(name)>180 or name in ('商品情報','商品一覧'): return None,'商品名を特定できません'
    body=' '.join(parser.texts[offset:])
    body=re.split(r'その他の商品|関連商品|商品のご案内へ戻る|の評判・口コミ|チルド惣菜一覧',body)[0]
    section=''
    for m in re.finditer('栄養成分',body):
        candidate=body[m.end():m.end()+700]
        candidate=re.split(r'賞味期限|アレルギー情報|原材料名|保存方法|お問い合わせ',candidate)[0]
        if re.search(r'(?:たんぱく質|たん白質|タンパク質)\s*[:：]?\s*[\d.]',candidate): section=candidate; break
    # Do not mix multiple tables (e.g. sauce separately, different serving sizes).
    if len(re.findall(r'(?:たんぱく質|たん白質|タンパク質)\s*[:：]?\s*[\d.]',section))>1:
        return None,'複数の栄養表示があり単位を特定できません'
    vals={}
    for key,label,unit in [('p','(?:たんぱく質|たん白質|タンパク質)','g'),('f','脂質','g'),('c','炭水化物','g'),('kcal','(?:熱量|エネルギー)','kcal')]:
        m=re.search(label+r'\s*[:：]?\s*(\d+(?:\.\d+)?)\s*'+unit,section,re.I)
        vals[key]=float(m.group(1)) if m else None
    unitmatch=re.search(r'((?:100\s*(?:g|ml)|1\s*(?:包装|袋|個|本|食|カップ|パック|枚|粒|食分))[^。:：]{0,45}?(?:当たり|あたり))',section)
    unit=unitmatch.group(1) if unitmatch else '公式掲載単位（要確認）'
    note='公式ページから自動取得。取扱い・販売地域・最新表示は店頭で確認してください。'
    if vals['p'] is None:
        m=re.search(r'たんぱく質\s*(\d+(?:\.\d+)?)\s*g',name)
        if m: vals['p']=float(m.group(1)); unit='1商品（商品名に記載）'; note+=' Pは商品名の表示値。'
    if vals['p'] is None: return None,'たんぱく質量の公開表示を取得できません'
    if any(v is not None and (v<0 or v>100000) for v in vals.values()): return None,'栄養値が範囲外です'
    # Price is not converted into a nutrition-unit price without an explicit matching unit.
    before_nutrition=body.split('栄養成分')[0]
    pm=re.search(r'税込(?:価格)?\s*(\d[\d,]*(?:\.\d+)?)\s*円',before_nutrition)
    if not pm: pm=re.search(r'(\d[\d,]*(?:\.\d+)?)\s*円\s*[（(]税込',before_nutrition)
    package_price=float(pm.group(1).replace(',','')) if pm else None
    price=package_price if unitmatch and re.match(r'1\s*(?:包装|袋|個|本|カップ|パック)',unit) else None
    if package_price is not None and price is None: note+=f' 商品税込価格 {package_price:g}円（栄養表示単位との対応未確認）。'
    if '100' in unit: note+=' 栄養値は100g/ml当たりです。1包装当たりではありません。'
    if re.search('現在この商品の情報を表示できません|販売を終了しました',body): note+=' 販売状況は要確認。'
    row=dict(id='auto_'+hashlib.sha256(url.encode()).hexdigest()[:20],store=DOMAINS[urlparse(url).hostname],name=name,category=guess_category(name),unit=unit,url=url,checked=str(date.today()),note=note,price=price,**vals,auto=True)
    validate([row]); return row,''

class CollectorRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class OfficialFetcher:
    def __init__(self): self.robots={}; self.last={}
    def raw(self,url):
        # Redirect destinations must pass the same host and scheme checks.
        for _ in range(4):
            p=urlparse(url)
            if p.scheme!='https' or p.hostname not in DOMAINS or p.port not in (None,443) or p.username or p.password: raise ValueError('対応外の転送先')
            try:
                with build_opener(CollectorRedirect()).open(Request(url,headers={'User-Agent':COLLECT_UA}),timeout=15) as response:
                    data=response.read(3000001)
                    if len(data)>3000000: raise ValueError('ページのサイズ上限を超えました')
                    return data.decode(response.headers.get_content_charset() or 'utf-8',errors='replace')
            except HTTPError as e:
                if e.code in (301,302,303,307,308): url=urljoin(url,e.headers.get('Location','')); continue
                raise
        raise ValueError('転送回数の上限を超えました')
    def get(self,url):
        host=urlparse(url).hostname
        if host not in self.robots:
            robot=RobotFileParser()
            try: robot.parse(self.raw('https://'+host+'/robots.txt').splitlines())
            except HTTPError as e:
                if e.code==404: robot.parse([])
                else: raise ValueError('収集可否を確認できません（robots.txt）')
            self.robots[host]=robot
        robot=self.robots[host]
        if not robot.can_fetch(COLLECT_UA,url): raise ValueError('サイトの収集制限により対象外')
        delay=max(1.,robot.crawl_delay(COLLECT_UA) or robot.crawl_delay('*') or 0)
        if delay>30: raise ValueError('サイトの収集間隔に対応できないため対象外')
        wait=delay-(time.monotonic()-self.last.get(host,0))
        if wait>0: time.sleep(wait)
        self.last[host]=time.monotonic()
        return self.raw(url)

class CatalogCollector:
    def __init__(self,path):
        self.path=str(path); self.lock=threading.Lock(); self.thread=None
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS products (url TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS job (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10); db.execute('PRAGMA busy_timeout=10000')
        try:
            with db: yield db
        finally: db.close()
    def snapshot(self):
        with self.db() as db:
            row=db.execute('SELECT data FROM job WHERE id=1').fetchone()
        j=json.loads(row[0]) if row else {}
        if j.get('status')=='収集中' and time.time()-j.get('heartbeat',0)>180: j['status']='中断（再開できます）'
        return j
    def products(self):
        with self.db() as db: return [json.loads(r[0]) for r in db.execute('SELECT data FROM products')]
    def save(self,j,row=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT data FROM job WHERE id=1').fetchone()
            if current and json.loads(current[0]).get('token')!=j['token']: return False
            old=json.loads(current[0]) if current else {}
            j['stop']=old.get('stop',False); j['heartbeat']=time.time()
            if row:
                legacy=db.execute('SELECT data FROM products WHERE url=?',(row['url'],)).fetchone()
                if legacy and json.loads(legacy[0]).get('store')==row['store']:
                    db.execute('DELETE FROM products WHERE url=?',(row['url'],))
                db.execute('INSERT OR REPLACE INTO products VALUES (?,?)',(task_key(row['store'],row['url']),json.dumps(row,ensure_ascii=False)))
            db.execute('INSERT OR REPLACE INTO job VALUES (1,?)',(json.dumps(j,ensure_ascii=False),))
        return True
    def start(self,stores,limit,resume=False):
        with self.lock:
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                r=db.execute('SELECT data FROM job WHERE id=1').fetchone(); old=json.loads(r[0]) if r else {}
                same_job=old.get('job_version')==COLLECT_JOB_VERSION
                if same_job and old.get('status')=='収集中' and time.time()-old.get('heartbeat',0)<180: return False
                if resume and same_job and old.get('pending'):
                    j=old
                    for store in COLLECT_STORES:
                        if store not in j['counts']:
                            j['counts'][store]=dict(detail=0,lists=0,added=0,skipped=0,errors=0)
                            j['pending'] += [[store,canonical(u),0] for u in COLLECT_SOURCES.get(store, [])]
                else:
                    pending=[]
                    for store in stores:
                        pending += [[store,canonical(u),0] for u in COLLECT_SOURCES.get(store, [])]
                    j=dict(pending=pending,seen=[],counts={s:dict(detail=0,lists=0,added=0,skipped=0,errors=0) for s in stores},limit=limit,errors=[],checked=0,added=0,skipped=0)
                j['limit']=COLLECT_LIMIT
                j['job_version']=COLLECT_JOB_VERSION
                j.update(token=uuid.uuid4().hex,status='収集中',stop=False,heartbeat=time.time())
                db.execute('INSERT OR REPLACE INTO job VALUES (1,?)',(json.dumps(j,ensure_ascii=False),))
            self.thread=threading.Thread(target=self.run,args=(j,),daemon=True,name='public-product-collector'); self.thread.start()
            return True
    def stop(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE'); r=db.execute('SELECT data FROM job WHERE id=1').fetchone()
            if r:
                j=json.loads(r[0]); j['stop']=True
                db.execute('UPDATE job SET data=? WHERE id=1',(json.dumps(j,ensure_ascii=False),))
    def run(self,j,fetcher=None):
        fetcher=fetcher or OfficialFetcher()
        seen=set(j['seen']); pending=j['pending']; queued={task_key(store,u) for store,u,_ in pending}
        recent={task_key(r['store'],r['url']) for r in self.products() if r['checked']==str(date.today())}
        try:
            while pending:
                state=self.snapshot()
                if state.get('token')!=j['token']: return
                if state.get('stop'): j['status']='一時停止'; break
                order=list(j['counts'])
                pending.sort(key=lambda task:order.index(task[0]))
                store,url,depth=pending[0]; counts=j['counts'][store]; kind=page_kind(url)
                if task_key(store,url) in seen or (task_key(store,url) in recent and kind in ('detail','generic')) or not kind or (kind in ('detail','generic') and (counts['added']>=j['limit'] or counts['detail']>=2500)) or (kind=='list' and counts['lists']>=40):
                    pending.pop(0); continue
                j['current_store']=store
                if not self.save(j): return
                row=None; counts['detail' if kind in ('detail','generic') else 'lists']+=1
                try:
                    html=fetcher.get(url); parser=ProductHTML(); parser.feed(html)
                    if kind in ('detail','generic'):
                        row,reason=parse_product(url,html)
                        if row:
                            # A shared corporate site must explicitly identify the target banner.
                            siblings=[name for name,hosts in STORE_HOSTS.items() if urlparse(url).hostname in hosts]
                            if len(siblings)>1 and store not in ' '.join(parser.texts):
                                row=None; reason='対象チェーンでの取扱いを確認できません'
                            else:
                                row['store']=store
                                row['id']='auto_'+hashlib.sha256(task_key(store,url).encode()).hexdigest()[:20]
                        if row: counts['added']+=1; j['added']+=1
                        else:
                            counts['skipped']+=1; j['skipped']+=1
                            j['errors'].append(dict(store=store,reason=reason,url=url))
                    if depth<4:
                        candidates=[]
                        for href,label in parser.links:
                            u=canonical(urljoin(url,href)); k=page_kind(u) if u else ''
                            if not k or urlparse(u).hostname not in STORE_HOSTS.get(store,set()) or task_key(store,u) in seen or task_key(store,u) in queued: continue
                            if re.search(r'ペット|ドッグ|キャット|洗剤|日用品|スキンケア|お酒|ビール|ワイン',label): continue
                            if urlparse(u).hostname not in ORIGINAL_HOSTS and k=='list' and not re.search('商品|食品|ブランド|一覧|次へ|たんぱく|チキン|ヨーグルト|豆腐|納豆|お肉|お魚|サラダ',label): continue
                            priority=0 if re.search('たんぱく|チキン|ヨーグルト|豆腐|納豆|魚|サラダ|おにぎり',label) else 1
                            candidates.append((priority,u,k))
                        for _,u,k in sorted(candidates):
                            if sum(task[0]==store for task in pending)>=2500: break
                            queued.add(task_key(store,u)); pending.append([store,u,depth+1])
                except Exception as e:
                    counts['errors']+=1
                    reason=f'HTTP {e.code}' if isinstance(e,HTTPError) else ('通信タイムアウト' if isinstance(e,TimeoutError) else str(e)[:120])
                    j['errors'].append(dict(store=store,reason=reason,url=url))
                pending.pop(0); seen.add(task_key(store,url)); j['seen']=list(seen); j['checked']+=1; j['errors']=j['errors'][-100:]
                if not self.save(j,row): return
            else: j['status']='完了' if j['added'] else '終了（取得0件・理由を確認）'
            self.save(j)
        except Exception as e:
            j['status']='中断（再開できます）'; j['errors'].append(dict(store='収集処理',reason=str(e)[:120],url=''))
            try: self.save(j)
            except Exception: pass

@st.cache_resource
def collector(resource_version):
    # resource_version is intentionally part of the cache key.
    # This prevents Streamlit hot-reload from reusing a collector instance
    # whose class methods still reference an older COLLECT_SOURCES mapping.
    return CatalogCollector(Path(tempfile.gettempdir())/'pfc_public_catalog_v3.sqlite3')

def sync_public_catalog():
    incoming=collector(COLLECT_JOB_VERSION).products()
    byurl={task_key(d['store'],canonical(d['url'])):i for i,d in enumerate(st.session_state.catalog) if d['url'] and canonical(d['url'])}
    for d in incoming:
        i=byurl.get(task_key(d['store'],d['url']))
        if i is None:
            byurl[task_key(d['store'],d['url'])]=len(st.session_state.catalog); st.session_state.catalog.append(d)
        elif st.session_state.catalog[i].get('auto'):
            d=dict(d,id=st.session_state.catalog[i]['id']); st.session_state.catalog[i]=d

def collection_store_progress(j):
    stores=list(j.get('counts',{})); pending=j.get('pending',[])
    active=j.get('current_store') or (pending[0][0] if pending else None)
    remaining={task[0] for task in pending}
    done=sum(store not in remaining for store in stores)
    return stores,active,(stores.index(active)+1 if active in stores else 0),done

def protein_value(d):
    p,price=d.get('p'),d.get('price')
    if p is None or price is None or p<=0 or price<=0 or '要確認' in d.get('unit',''): return None
    return 100*p/price

@st.fragment(run_every=3)
def collection_status():
    try:
        c=collector(COLLECT_JOB_VERSION); j=c.snapshot()
        # Ignore stale progress records created by older collection logic.
        if not j or j.get('job_version')!=COLLECT_JOB_VERSION: return
        sync_public_catalog()
        stores,active,position,done=collection_store_progress(j)
        current_added=j.get('counts',{}).get(active,{}).get('added',0) if active else 0
        if j['status']=='収集中':
            st.caption(f"収集中：{position}/{len(stores)}店舗｜現在：{active or '準備中'}｜{min(current_added,COLLECT_LIMIT)}/{COLLECT_LIMIT}商品")
        elif j.get('pending'):
            st.caption(f"一時停止：{position}/{len(stores)}店舗｜現在：{active or '準備中'}｜{min(current_added,COLLECT_LIMIT)}/{COLLECT_LIMIT}商品")
        else:
            st.caption(f"収集完了：{len(stores)}/{len(stores)}店舗")
    except Exception: st.warning('収集状況を読み込めません。画面を再読み込みしてください。')


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
    st.caption(f'v3.6｜{len(COLLECT_STORES)}店舗・各店最大{COLLECT_LIMIT}商品')
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
                    started=collector(COLLECT_JOB_VERSION).start(collect_stores,collect_limit)
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

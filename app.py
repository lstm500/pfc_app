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
    if not isinstance(rows,list) or len(rows)>2000: raise ValueError('商品は2000件以内のリストにしてください。')
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
    st.markdown('<div class="hero"><h1>🥗 PFCえらび</h1><p>いつものお店で、たんぱく質をプラス。</p></div>',unsafe_allow_html=True)
    if st.session_state.page!='ホーム' and st.button('◀ トップページに戻る',use_container_width=True):
        st.session_state.page='ホーム'; st.rerun()
    page=st.session_state.page
    if page=='ホーム':
        st.write('お店を選んで商品を比較。食べる組み合わせのPFCも確認できます。')
        for label in ['🔎 お店から探す','🍽 組み合わせを見る','♡ お気に入り','＋ 商品を追加・編集','💾 保存・復元']:
            if st.button(label,use_container_width=True): st.session_state.page=label; st.rerun()
        st.caption(f'登録商品 {len(st.session_state.catalog)}件｜初期データ確認日 2026/9/6')
        st.info('コンビニ・スーパーの店名一覧から選んで探せます。商品未登録のお店は追加登録後に検索できます。全商品の自動収集・在庫確認には未対応です。')
        return
    if page=='💾 保存・復元':
        st.subheader('データを保存・復元')
        st.info('追加商品・お気に入り・組み合わせは、この接続中に保持します。終了前に保存し、次回はファイルを読み込んでください。')
        payload={k:st.session_state[k] for k in ('catalog','favorites','cart')}
        st.download_button('データを保存',json.dumps(payload,ensure_ascii=False,indent=2),'pfc_backup.json','application/json',use_container_width=True)
        f=st.file_uploader('保存ファイルを読み込む',type=['json'])
        if f and st.button('復元する'):
            try:
                if f.size>5000000: raise ValueError('ファイルは5MB以内にしてください。')
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
        sort=st.selectbox('並び順',['たんぱく質が多い順','PFC目標比率に近い順','価格が安い順','100円当たりのたんぱく質が多い順'])
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
    elif sort=='100円当たりのたんぱく質が多い順':
        rows=[d for d in rows if d['p'] is not None and d['price'] is not None and d['price']>0]; rows.sort(key=lambda d:d['p']/d['price'],reverse=True)
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
    for d in rows:
        with st.container(border=True):
            st.caption(d['store']+' ・ '+d['category']); st.markdown('#### '+escape(d['name']))
            st.write(f"**P {fmt(d['p'])}** ／ F {fmt(d['f'])} ／ C {fmt(d['c'])}")
            st.write(f"{fmt(d['kcal'],'kcal')} ・ {fmt(d['price'],'円')}"); st.caption(d['unit']); chart(d)
            if sort=='100円当たりのたんぱく質が多い順': st.caption(f"100円当たり P {100*d['p']/d['price']:.1f}g")
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

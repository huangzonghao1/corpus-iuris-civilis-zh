from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, re, time

ROOT=Path(__file__).resolve().parent
SRC=ROOT/'source_original'
BASE='https://droitromain.univ-grenoble-alpes.fr/Corpus/Novellae.htm'
UA='Mozilla/5.0 (compatible; scholarly-legal-epub/1.0; personal research archive)'
class LinkParser(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]; self.href=None; self.text=[]
    def handle_starttag(self,t,a):
        if t.lower()=='a': self.href=dict(a).get('href'); self.text=[]
    def handle_data(self,d):
        if self.href is not None: self.text.append(d)
    def handle_endtag(self,t):
        if t.lower()=='a' and self.href is not None:
            self.links.append((''.join(self.text).strip(),self.href)); self.href=None

def fetch(url):
    time.sleep(0.15)
    req=Request(url,headers={'User-Agent':UA})
    with urlopen(req,timeout=45) as r: return r.status,r.geturl(),r.headers.get('Content-Type',''),r.read()
def detect(b,ct):
    m=re.search(r'charset\s*=\s*([^;\s]+)',ct,re.I)
    if m: return m.group(1).strip('"\'')
    h=b[:8192].decode('ascii',errors='ignore')
    m=re.search(r'<meta[^>]+charset\s*=\s*["\']?([^\s"\'>;]+)',h,re.I)
    if m: return m.group(1)
    m=re.search(r'content\s*=\s*["\'][^"\']*charset\s*=\s*([^;\s"\']+)',h,re.I)
    return m.group(1) if m else 'unspecified; inspect/heuristic needed'
def rec(url,path,status,ct,b,label=None):
    x={'source_url':url,'local_path':'source_original/'+path,'http_status':status,'content_type':ct,'detected_encoding':detect(b,ct),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    if label is not None: x['label']=label
    return x
index=SRC/'Novellae.htm'
if not index.exists():
    s,actual,ct,b=fetch(BASE); index.write_bytes(b)
else:
    b=index.read_bytes(); s=200; actual=BASE; ct='text/html; encoding determined from document'
p=LinkParser(); p.feed(b.decode(detect(b,ct),errors='replace'))
links=[]; seen=set(); external=[]
for label,href in p.links:
    u=urljoin(actual,href); z=urlsplit(u)
    if z.netloc.lower()=='droitromain.univ-grenoble-alpes.fr' and z.path.startswith('/Corpus/') and z.path.lower().endswith(('.htm','.html')):
        name=Path(z.path).name
        if name not in seen: links.append({'label':label,'url':u,'filename':name});seen.add(name)
    elif not href.startswith('#'): external.append({'label':label,'href':href,'reason':'external link; not part of corpus download'})

def one(item):
    path=SRC/item['filename']
    if path.exists():
        b=path.read_bytes(); return rec(item['url'],item['filename'],'retained-existing','',b,item['label']),None
    try:
        code,actual,ct,b=fetch(item['url'])
        if code!=200: return None,{'source_url':item['url'],'filename':item['filename'],'label':item['label'],'error':f'HTTP {code}'}
        path.write_bytes(b)
        return rec(actual,item['filename'],code,ct,b,item['label']),None
    except Exception as e:
        return None,{'source_url':item['url'],'filename':item['filename'],'label':item['label'],'error':repr(e)}

results=[]; failures=[]
missing=[i for i in links if not (SRC/i['filename']).exists()]
print(f'Indexed {len(links)} same-site corpus pages; {len(missing)} still need download; using 4 workers.',flush=True)
with ThreadPoolExecutor(max_workers=4) as pool:
    fs=[pool.submit(one,i) for i in links]
    for f in as_completed(fs):
        a,e=f.result()
        if a: results.append(a); print('saved/verified',a['local_path'],a['bytes'],flush=True)
        if e: failures.append(e); print('FAILED',e['filename'],e['error'],flush=True)
# Corrected index provenance.
ib=index.read_bytes(); records=[rec(BASE,'Novellae.htm',200,'text/html; charset=UTF-8',ib,'corpus_index')]
records+=sorted(results,key=lambda x:x['local_path'])
def nums(prefix):
    vals=[]
    for x in links:
        m=re.fullmatch(prefix+r'(\d+)\.htm',x['filename'],re.I)
        if m: vals.append(int(m.group(1)))
    return sorted(vals)
nov=nums('Nov'); ed=nums('Ed'); app=nums('App')
manifest={'manifest_created_utc':datetime.now(timezone.utc).isoformat(),'index_url':BASE,'index_http_status':200,'index_content_type':'text/html; charset=UTF-8','scope_inventory':{'Novellae_visible_expected':list(range(1,169)),'Novellae_downloaded_links':nov,'Novellae_missing_visible_numbers':sorted(set(range(1,169))-set(nov)),'Edicta_downloaded_links':ed,'Edicta_visible_unlinked_or_absent_from_sequence':[n for n in range(1,14) if n not in ed],'Appendix_downloaded_links':app,'Epitome_links':[x['filename'] for x in links if x['filename'].startswith('epitome_')]},'records':records,'failed_pages':failures,'external_links_not_fetched':external,'rights_note':'The site root metadata includes a copyright attribution to Alexandr Koptev. No robots.txt or explicit reuse license/terms were found during this check. These original pages are retained for the user-requested local research edition; no redistribution rights are asserted. Confirm applicable permissions before public distribution.'}
(ROOT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('COMPLETE: indexed',len(links),'downloaded/retained',len(records)-1,'failures',len(failures),'Novellae links',len(nov),'missing',manifest['scope_inventory']['Novellae_missing_visible_numbers'],'Edicta',ed,'Appendix',len(app),'Epitome',len(manifest['scope_inventory']['Epitome_links']),flush=True)

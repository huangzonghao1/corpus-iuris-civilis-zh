from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit
import hashlib,json,re,shutil
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'source_original'; WEB=ROOT/'web'; BASE='https://droitromain.univ-grenoble-alpes.fr/Corpus/Novellae.htm'
manifest=json.loads((ROOT/'source_manifest.json').read_text(encoding='utf-8'))
# The retry of App1.htm succeeded after one transient TLS timeout.
class LP(HTMLParser):
 def __init__(self): super().__init__(); self.links=[]; self.href=None; self.txt=[]
 def handle_starttag(self,t,a):
  if t=='a': self.href=dict(a).get('href'); self.txt=[]
 def handle_data(self,d):
  if self.href is not None: self.txt.append(d)
 def handle_endtag(self,t):
  if t=='a' and self.href is not None: self.links.append((''.join(self.txt).strip(),self.href)); self.href=None
idx=(SRC/'Novellae.htm').read_bytes(); lp=LP(); lp.feed(idx.decode('utf-8'))
url_by_name={Path(urlsplit(urljoin(BASE,h)).path).name:(urljoin(BASE,h),label) for label,h in lp.links if urlsplit(urljoin(BASE,h)).netloc=='droitromain.univ-grenoble-alpes.fr' and urlsplit(urljoin(BASE,h)).path.startswith('/Corpus/')}
records=[]
for f in sorted(SRC.glob('*')):
 if not f.is_file(): continue
 b=f.read_bytes(); high=any(x>=128 for x in b)
 try: b.decode('utf-8','strict'); utf8=True
 except UnicodeDecodeError: utf8=False
 head=b[:8192].decode('ascii','ignore')
 m=re.search(r'charset\s*=\s*["\']?([^\s"\'>;]+)',head,re.I)
 declared=m.group(1) if m else 'not declared'
 if high and utf8: enc='UTF-8 (verified from bytes; source meta declares '+declared+')'
 elif high: enc='non-UTF-8 high bytes; source declares '+declared
 elif f.name=='Novellae.htm': enc='ASCII-only bytes (HTTP response declared UTF-8; HTML meta declares '+declared+')'
 else: enc='ASCII-only bytes (source meta declares '+declared+')'
 if f.name=='Novellae.htm': url=BASE; label='corpus index'; status=200; ct='text/html; charset=UTF-8'
 else:
  url,label=url_by_name.get(f.name,('https://droitromain.univ-grenoble-alpes.fr/Corpus/'+f.name,f.stem)); status=200
  old=next((x for x in manifest.get('records',[]) if x.get('local_path')=='source_original/'+f.name),{})
  ct=old.get('content_type') or 'not retained; see source HTML declaration'
 records.append({'source_url':url,'local_path':'source_original/'+f.name,'http_status':status,'content_type':ct,'detected_encoding':enc,'declared_encoding':declared,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'label':label})
missing_file=[x['filename'] for x in []]
links=[]
for label,href in lp.links:
 u=urljoin(BASE,href); z=urlsplit(u)
 if z.netloc=='droitromain.univ-grenoble-alpes.fr' and z.path.startswith('/Corpus/') and z.path.lower().endswith(('.htm','.html')):
  name=Path(z.path).name
  if name not in [x['filename'] for x in links]: links.append({'label':label,'filename':name,'url':u})
missing=[x for x in links if not (SRC/x['filename']).exists()]
manifest.update({'records':records,'failed_pages':[{'source_url':x['url'],'filename':x['filename'],'error':'source file remains unavailable'} for x in missing], 'rights_note':'The site root metadata attributes copyright to Alexandr Koptev. No robots.txt or explicit reuse license was found in the checks performed. The old edition is preserved here for the user-requested local research copy; no redistribution permission is asserted. Confirm rights before public distribution.'})
manifest['scope_inventory']={'same_site_linked_pages':len(links),'Novellae_visible_expected':list(range(1,169)),'Novellae_downloaded_links':sorted(int(re.search(r'Nov(\d+)',x['filename']).group(1)) for x in links if re.match(r'Nov\d+\.htm',x['filename'])),'Novellae_unlinked_numbers':sorted(set(range(1,169))-set(sorted(int(re.search(r'Nov(\d+)',x['filename']).group(1)) for x in links if re.match(r'Nov\d+\.htm',x['filename']))) ),'Edicta_downloaded_links':sorted(int(re.search(r'Ed(\d+)',x['filename']).group(1)) for x in links if re.match(r'Ed\d+\.htm',x['filename'])),'Edicta_unlinked_numbers':sorted(set(range(1,14))-set(sorted(int(re.search(r'Ed(\d+)',x['filename']).group(1)) for x in links if re.match(r'Ed\d+\.htm',x['filename']))) ),'Appendix_downloaded_links':sorted(int(re.search(r'App(\d+)',x['filename']).group(1)) for x in links if re.match(r'App\d+\.htm',x['filename'])),'Epitome_links':[x['filename'] for x in links if x['filename'].startswith('epitome_')],'missing_linked_pages':[x['filename'] for x in missing]}
(ROOT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# Make an offline copy; source_original remains the untouched byte archive.
WEB.mkdir(parents=True,exist_ok=True)
for f in SRC.glob('*.htm'):
 shutil.copyfile(f,WEB/f.name)
groups=[('《查士丁尼新律》（Novellae）',r'^Nov(\d+)\.htm$',lambda n:f'Novella {n}'),('《查士丁尼十三篇敕令》（Iustiniani XIII Edicta）',r'^Ed(\d+)\.htm$',lambda n:f'Edictum {n}'),('散见宪令附录（Appendix constitutionum dispersarum）',r'^App(\d+)\.htm$',lambda n:f'Appendix {n}'),('《尤利安新律拉丁摘要》（Iuliani Epitome Latina Novellarum）',r'^epitome_julien_(\d+)\.htm$',lambda n:'Constitutiones 1–80' if n=='1' else 'Constitutiones 81–124')]
entry_groups=[]
for heading,pattern,label_fn in groups:
 group=[]
 for x in links:
  m=re.match(pattern,x['filename'])
  if m and (SRC/x['filename']).exists(): group.append(f'<li><a href="{x["filename"]}">{label_fn(m.group(1))}</a></li>')
 if group: entry_groups.append(f'<h2>{heading}</h2><ul>'+ '\n'.join(group) + '</ul>')
entries='\n'.join(entry_groups)
missing_html='、'.join(x['filename'] for x in missing) or '无'
landing=f'''<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8"><title>《查士丁尼新律》离线目录</title><style>body{{max-width:58em;margin:2em auto;padding:0 1em;font:1rem/1.65 sans-serif}}h1,h2{{line-height:1.3}}.note{{padding:1em;background:#f4f1e8}}ul{{columns:2;column-gap:2em}}li{{break-inside:avoid}}</style></head><body><h1>《查士丁尼新律》离线网页目录</h1><p>来源：<a href="{BASE}">{BASE}</a></p><p>据网站目录，本地保存可访问的《查士丁尼新律》、敕令、附录及尤利安摘要页面。原始页面副本以原始字节保存在 <code>../source_original/</code>，本目录中的同名页面供离线阅读。</p><p>版本署名：目录标示 Rudolfus Schoell 与 Guilelmus Kroll；具体页面的底本、录入者及版本说明请以页面原文为准。</p><div class="note"><strong>范围缺口：</strong>目录中未链接的新律编号为 136、137、163；未链接的敕令编号为 7、9、13。链接页下载情况详见旁附 <code>../source_manifest.json</code>。网站根页含 Alexandr Koptev 的版权归属信息；未发现明确的再利用许可，本地副本不表示获得公开传播许可。</div><p><a href="Novellae.htm">打开原始目录页</a></p><h2>网页链接清单</h2>{entries}</body></html>'''
(WEB/'index.html').write_text(landing,encoding='utf-8')
# Audit links within HTML snapshots for targets among the mirrored files and anchors.
class LinkAudit(HTMLParser):
 def __init__(self): super().__init__(); self.hrefs=[]
 def handle_starttag(self,t,a):
  d=dict(a)
  if t=='a' and d.get('href'): self.hrefs.append(d['href'])
files=list(WEB.glob('*.htm'))
known={f.name for f in files}|{'index.html'}
link_report=[]
for f in files:
 try: text=f.read_bytes().decode('utf-8','replace')
 except Exception: continue
 p=LinkAudit();p.feed(text)
 for href in p.hrefs:
  z=urlsplit(href)
  if z.scheme or z.netloc or not z.path: continue
  target=(f.parent/z.path).resolve()
  if target.exists(): continue
  link_report.append({'from':f.name,'href':href,'resolved_path':str(target.relative_to(WEB.resolve())) if str(target).startswith(str(WEB.resolve())) else z.path})
(WEB/'offline_link_audit.json').write_text(json.dumps({'checked_html_files':len(files),'unresolved_local_links':link_report},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('source_records',len(records),'linked_pages',len(links),'missing',missing_file,'failed',len(missing),'offline_html',len(files),'unresolved_local_links',len(link_report))
print('inventory',json.dumps(manifest['scope_inventory'],ensure_ascii=False))

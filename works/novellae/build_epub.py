from html.parser import HTMLParser
from html import escape, unescape
from urllib.parse import urlsplit
from pathlib import Path
from datetime import date,datetime,timezone
import json,re,hashlib,zipfile,uuid,xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
SRC=ROOT/'source_original'; TRANS=ROOT/'translations'; OUT=ROOT/'Novellae_Schoell_Kroll_Chinese_Bilingual.epub'
NAVY='Iustiniani Novellae ( Schoell & Kroll )'
BASE='https://droitromain.univ-grenoble-alpes.fr/Corpus/Novellae.htm'
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
SKIP={'head','style','script','noscript','title','meta','link'}
class N:
 def __init__(self,tag='root',attrs=None): self.tag=tag; self.attrs=dict(attrs or []); self.children=[]
class TreeParser(HTMLParser):
 def __init__(self): super().__init__(convert_charrefs=True); self.root=N(); self.stack=[self.root]; self.inbody=False; self.skip=[]
 def handle_starttag(self,t,a):
  t=t.lower()
  if t=='body': self.inbody=True; return
  if not self.inbody: return
  if t in SKIP: self.skip.append(t); return
  if self.skip: return
  node=N(t,a); self.stack[-1].children.append(node)
  if t not in VOID: self.stack.append(node)
 def handle_startendtag(self,t,a):
  if self.inbody and not self.skip: self.stack[-1].children.append(N(t.lower(),a))
 def handle_endtag(self,t):
  t=t.lower()
  if t=='body': self.inbody=False; return
  if self.skip:
   if t==self.skip[-1]: self.skip.pop()
   return
  for i in range(len(self.stack)-1,0,-1):
   if self.stack[i].tag==t:
    del self.stack[i:]; break
 def handle_data(self,d):
  if self.inbody and not self.skip and d: self.stack[-1].children.append(d)

def walk(node):
 for c in node.children:
  if isinstance(c,N):
   yield c
   yield from walk(c)
def all_text(node):
 return ''.join(c if isinstance(c,str) else all_text(c) for c in node.children)
def slug(x):
 x=re.sub(r'[^A-Za-z0-9_.:-]+','-',x).strip('-')
 if not x or not re.match(r'[A-Za-z_]',x): x='a-'+x
 return x

def clean_title(path):
 b=path.read_bytes(); enc='utf-8'
 try: b.decode('utf-8')
 except UnicodeDecodeError: enc='latin-1'
 txt=b.decode(enc,errors='replace')
 m=re.search(r'<title[^>]*>(.*?)</title\s*>',txt,re.I|re.S)
 if m: return re.sub(r'\s+',' ',unescape(m.group(1))).strip()
 return path.stem

def source_order(p):
 if p.name=='Novellae.htm': return (0,0)
 m=re.fullmatch(r'Nov(\d+)\.htm',p.name)
 if m: return (1,int(m.group(1)))
 m=re.fullmatch(r'Ed(\d+)\.htm',p.name)
 if m: return (2,int(m.group(1)))
 m=re.fullmatch(r'App(\d+)\.htm',p.name)
 if m: return (3,int(m.group(1)))
 m=re.fullmatch(r'epitome_julien_(\d+)\.htm',p.name)
 if m: return (4,int(m.group(1)))
 return (5,p.name.lower())
files=sorted(SRC.glob('*.htm'),key=source_order)
byname={p.name:p for p in files}
link_map={p.name:p.stem+'.xhtml' for p in files}
parsed={}; anchor_maps={}; titles={}
for p in files:
 b=p.read_bytes()
 try: raw=b.decode('utf-8','strict')
 except UnicodeDecodeError: raw=b.decode('latin-1')
 parser=TreeParser(); parser.feed(raw); parsed[p.name]=parser.root; titles[p.name]=clean_title(p)
 amap={}; counts={}
 for n in walk(parser.root):
  for key in ('id','name'):
   val=n.attrs.get(key)
   if val:
    counts[val]=counts.get(val,0)+1
    amap[val]=slug(val) if counts[val]==1 else slug(val)+'-'+str(counts[val])
 anchor_maps[p.name]=amap

# Convert source links to local XHTML links while maintaining external references.
def href_for(current,href):
 parts=urlsplit(href)
 if parts.scheme.lower()=='javascript': return None
 path=parts.path
 target_name=Path(path).name if path else ''
 # Same-site absolute links are mapped to their local page.
 if parts.scheme in ('http','https') and 'droitromain.univ-grenoble-alpes.fr' not in (parts.netloc or ''):
  return href
 if target_name in link_map:
  dest=link_map[target_name]
  if dest==link_map[current]: dest=''
  frag=parts.fragment
  if frag: frag=anchor_maps.get(target_name,{}).get(frag,slug(frag))
  return (dest or '')+('#'+frag if frag else '')
 if not path and parts.fragment:
  frag=anchor_maps.get(current,{}).get(parts.fragment,slug(parts.fragment))
  return '#'+frag
 if parts.scheme or parts.netloc: return href
 return href

BLOCK={'p','div','blockquote','pre','ul','ol','li','h1','h2','h3','h4','h5','h6'}
MAP={'table':('div','table-wrap'),'tbody':('div','table-body'),'thead':('div','table-head'),'tfoot':('div','table-foot'),'tr':('div','table-row'),'td':('div','table-cell'),'th':('div','table-cell'),'center':('div','center'),'font':('span',''),'section':('section',''),'article':('section','')}
INLINE={'a','span','b','strong','i','em','u','sup','sub','small','code','kbd','s','del','ins','cite','q','abbr'}
def serialize(node,current):
 out=[]
 for c in node.children:
  if isinstance(c,str): out.append(escape(c,quote=False)); continue
  tag=c.tag; attrs=c.attrs
  if tag in {'br','hr'}: out.append(f'<{tag}/>' ); continue
  if tag=='img':
   alt=attrs.get('alt','')
   if alt: out.append('[图片：'+escape(alt)+']')
   continue
  if tag=='a':
   name=attrs.get('id') or attrs.get('name')
   aid=anchor_maps.get(current,{}).get(name) if name else None
   href=attrs.get('href')
   if href:
    to=href_for(current,href)
    if to is not None: out.append('<a'+(f' id="{escape(aid,quote=True)}"' if aid else '')+f' href="{escape(to,quote=True)}">'+serialize(c,current)+'</a>')
    elif aid: out.append(f'<span id="{escape(aid,quote=True)}"></span>'+serialize(c,current))
    else: out.append(serialize(c,current))
   elif aid:
    out.append(f'<span id="{escape(aid,quote=True)}"></span>'+serialize(c,current))
   else: out.append(serialize(c,current))
   continue
  mapped=MAP.get(tag)
  if mapped: out.append(f'<{mapped[0]}'+(f' class="{mapped[1]}"' if mapped[1] else '')+'>'+serialize(c,current)+f'</{mapped[0]}>'); continue
  if tag in BLOCK or tag in INLINE or tag=='hr':
   out.append(f'<{tag}>'+serialize(c,current)+f'</{tag}>'); continue
  # Drop unknown presentational wrappers without dropping their text.
  out.append(serialize(c,current))
 return ''.join(out)

# E-book metadata pages.
css='''body { font-family: serif; line-height: 1.55; margin: 5%; text-align: justify; }
h1,h2,h3 { font-family: sans-serif; text-align: left; page-break-after: avoid; }
.source-page-title { margin-bottom: 1.5em; }
.source-note { border-left: .2em solid #777; padding-left: 1em; }
.translator-note { font-style: italic; }
.center { text-align: center; }
.table-row { display: block; }
.table-cell { display: block; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font-family: serif; }
blockquote { margin-left: 1.5em; margin-right: 1em; }
a { color: inherit; text-decoration: underline; }
'''
def xhtml(title,body,lang='und',style_href='../styles/book.css'):
 return ('<?xml version="1.0" encoding="utf-8"?>\n'
 '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="'+escape(lang,quote=True)+'" lang="'+escape(lang,quote=True)+'">'
 '<head><title>'+escape(title)+'</title><meta charset="utf-8"/><link rel="stylesheet" type="text/css" href="'+escape(style_href,quote=True)+'"/></head>'
 '<body>'+body+'</body></html>')

# Markdown to conservative XHTML for the working Chinese translations.
def inl(s):
 # Markdown source excerpts sometimes encode legal labels such as &lt;Praefatio&gt;.
 # Decode once before XHTML escaping so the reader sees the angle brackets, not entity text.
 s=unescape(s)
 code_spans=[]
 def save_code(match):
  token='ZXQCODE'+str(len(code_spans))+'QXZ'
  code_spans.append((token,escape(match.group(1),quote=False)))
  return token
 s=re.sub(r'`([^`]+)`',save_code,s)
 s=escape(s,quote=False)
 s=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',s)
 s=re.sub(r'\*(.+?)\*',r'<em>\1</em>',s)
 s=re.sub(r'(?<!\\)\[(.*?)\]\((https?://[^)]+)\)',r'<a href="\2">\1</a>',s)
 for token,code in code_spans: s=s.replace(token,'<code>'+code+'</code>')
 s=s.replace('\\*','*')
 return s
def md_convert(text):
 out=[]; lines=text.splitlines(); i=0; para=[]; quote=[]; list_items=[]; inlist=False; used_heading_ids={}; heading_index=0
 def flushp():
  nonlocal para
  if para: out.append('<p>'+inl(' '.join(para))+'</p>'); para=[]
 def flushq():
  nonlocal quote
  if quote: out.append('<blockquote><p>'+inl(' '.join(quote))+'</p></blockquote>'); quote=[]
 def flushlist():
  nonlocal list_items,inlist
  if inlist: out.append('<ul>'+''.join('<li>'+inl(x)+'</li>' for x in list_items)+'</ul>'); list_items=[]; inlist=False
 while i<len(lines):
  line=lines[i]
  if line.startswith('```'):
   flushp();flushq();flushlist(); lang=line[3:].strip(); i+=1; code=[]
   while i<len(lines) and not lines[i].startswith('```'): code.append(lines[i]); i+=1
   out.append('<pre><code>'+escape('\n'.join(code),quote=False)+'</code></pre>'); i+=1; continue
  if not line.strip(): flushp();flushq();flushlist();i+=1;continue
  if line.strip().startswith('|'):
   flushp();flushq();flushlist(); rows=[]
   while i<len(lines) and lines[i].strip().startswith('|'):
    cells=[c.strip() for c in lines[i].strip().strip('|').split('|')]
    if not all(re.fullmatch(r':?-{3,}:?',c or '-') for c in cells): rows.append(cells)
    i+=1
   if rows:
    heads=rows[0]; bodyrows=rows[1:]
    out.append('<table><thead><tr>'+''.join('<th>'+inl(c)+'</th>' for c in heads)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+inl(c)+'</td>' for c in row)+'</tr>' for row in bodyrows)+'</tbody></table>')
   continue
  m=re.match(r'^(#{1,6})\s+(.*)',line)
  if m:
   flushp();flushq();flushlist(); level=len(m.group(1)); heading=m.group(2)
   km=re.search(r'\bkp\.\s*(\d+)\b',heading,re.I)
   base='kp-'+km.group(1) if km else 'section-'+str(heading_index+1)
   count=used_heading_ids.get(base,0)+1; used_heading_ids[base]=count
   aid=base if count==1 else base+'-'+str(count)
   heading_index+=1
   out.append(f'<h{level} id="{escape(aid,quote=True)}">'+inl(heading)+f'</h{level}>');i+=1;continue
  m=re.match(r'^<!--\s*译文[:：](.*?)-->',line.strip())
  if m:
   flushp();flushq();flushlist();out.append('<p class="translator-note">【译文状态：'+inl(m.group(1).strip())+'】</p>');i+=1;continue
  if line.lstrip().startswith('>'):
   flushp();flushlist();quote.append(re.sub(r'^\s*>\s?','',line));i+=1;continue
  m=re.match(r'^\s*[-*+]\s+(.*)',line)
  if m:
   flushp();flushq();inlist=True;list_items.append(m.group(1));i+=1;continue
  flushq();flushlist();para.append(line.strip());i+=1
 flushp();flushq();flushlist()
 return ''.join(out)

translation_paths=sorted(tp for tp in TRANS.glob('*.md') if tp.name!='术语表_工作版.md')
translation_docs=[]; translation_meta=[]
for tp in translation_paths:
 txt=tp.read_text(encoding='utf-8')
 title=next((x.strip('# ').strip() for x in txt.splitlines() if x.startswith('# ')),tp.stem)
 doc='translation-'+tp.stem+'.xhtml'
 # Add corresponding source references at the top of each working translation file.
 refs=[]
 # Link each translation volume directly to its source pages inside this EPUB.
 # The underlying offline originals remain available separately in source_original/.
 page_numbers=re.search(r'_(\d+)-(\d+)_',tp.stem)
 if page_numbers:
  a,z=map(int,page_numbers.groups())
  page_numbers=range(a,z+1)
 else:
  single_number=re.search(r'_(\d+)_',tp.stem)
  page_numbers=[int(single_number.group(1))] if single_number else []
 if tp.stem.startswith('Novellae_'):
  refs=[f'<a href="../text/{link_map[f"Nov{n:02d}.htm"]}">Novella {n}</a>' for n in page_numbers if f'Nov{n:02d}.htm' in link_map and not (n==89 and tp.stem=='Novellae_057-112_Chinese')]
 elif tp.stem.startswith('Edicta_'):
  refs=[f'<a href="../text/{link_map[f"Ed{n}.htm"]}">Edictum {n}</a>' for n in page_numbers if f'Ed{n}.htm' in link_map and not (n==8 and tp.stem=='Edicta_001-012_Chinese')]
 elif tp.stem.startswith('Appendix_'):
  refs=[f'<a href="../text/{link_map[f"App{n}.htm"]}">Appendix {n}</a>' for n in page_numbers if f'App{n}.htm' in link_map]
 elif tp.stem.startswith('Epitome_Juliani_'):
  vol=2 if any(n>=81 for n in page_numbers) else 1
  source=f'epitome_julien_{vol}.htm'
  if source in link_map:
   kp_ids=[]
   for line in txt.splitlines():
    km=re.match(r'^#{2,6}\s+kp\.\s*(\d+)\b',line,re.I)
    if km and int(km.group(1)) not in kp_ids: kp_ids.append(int(km.group(1)))
   if kp_ids:
    refs=[]
    for number in (kp_ids[0],kp_ids[-1]):
     aid=anchor_maps[source].get(f'cap.{number}',slug(f'cap.{number}'))
     refs.append(f'<a href="../text/{link_map[source]}#{escape(aid,quote=True)}">kp.{number}</a>')
    if len(kp_ids)==1: refs=refs[:1]
   else: refs=[f'<a href="../text/{link_map[source]}">Epitome volume {vol}</a>']
 # Markdown itself is authoritative about actual translated coverage; don't infer completeness from file range.
 intro='<section class="source-note"><p>分卷状态以本译稿开头的“完成范围／尚未翻译”说明为准。原文与中文译文在下文逐段相邻排列；完整来源页见独立拉丁文版及项目目录中的 source_original/。译文为工作稿，尚待专业终审。</p></section>'
 translation_docs.append((doc,xhtml(title,intro+md_convert(txt),'zh-Hans')))
 translation_meta.append({'file':tp.name,'title':title,'doc':doc,'source_bytes':tp.stat().st_size})
glossary_path=TRANS/'术语表_工作版.md'
glossary_doc=None; glossary_content=None
if glossary_path.exists():
 glossary_doc='terminology.xhtml'
 glossary_content=xhtml('术语表（工作版）',md_convert(glossary_path.read_text(encoding='utf-8')),'zh-Hans','styles/book.css')

# Add reverse links from each source page to the relevant bilingual working volume.
translation_for_source={}
for meta in translation_meta:
 stem=Path(meta['file']).stem
 section=None; nums=[]
 if stem.startswith('Novellae_'):
  section='Nov'
 elif stem.startswith('Edicta_'):
  section='Ed'
 elif stem.startswith('Appendix_'):
  section='App'
 if section:
  m=re.search(r'_(\d+)-(\d+)_',stem)
  if m: nums=list(range(int(m.group(1)),int(m.group(2))+1))
  else:
   m=re.search(r'_(\d+)_',stem)
   if m: nums=[int(m.group(1))]
  for n in nums:
   # Novella 89 has a separate complete volume; the 57-112 file explicitly omits it.
   if section=='Nov' and n==89 and stem=='Novellae_057-112_Chinese': continue
   # Edictum VIII is published as its own bilingual file, not in the combined volume.
   if section=='Ed' and n==8 and stem=='Edicta_001-012_Chinese': continue
   fname=f'{section}{n:02d}.htm' if section=='Nov' else f'{section}{n}.htm'
   if fname in link_map: translation_for_source.setdefault(fname,[]).append(meta)
 elif stem.startswith('Epitome_Juliani_'):
  m=re.search(r'_(\d+)-(\d+)_',stem)
  if m: nums=list(range(int(m.group(1)),int(m.group(2))+1))
  else:
   m=re.search(r'_(\d+)_',stem)
   nums=[int(m.group(1))] if m else []
  vol=2 if any(n>=81 for n in nums) else 1
  fname=f'epitome_julien_{vol}.htm'
  if fname in link_map: translation_for_source.setdefault(fname,[]).append(meta)

# Source pages.
docs=[]
for p in files:
 body=serialize(parsed[p.name],p.name)
 title=titles[p.name]
 # Generated notice preserves a durable link to the exact downloaded byte source.
 source_name=p.name
 tmeta=translation_for_source.get(source_name,[])
 translated=('；中文对读：'+'、'.join(f'<a href="../translations/translation-{escape(Path(meta["file"]).stem+".xhtml",quote=True)}">{escape(meta["title"])}</a>' for meta in tmeta)) if tmeta else ''
 note=f'<aside class="source-note"><p>本页按来源网页整理为可重排文本；原始网页字节见 <code>source_original/{escape(source_name)}</code>。来源：<a href="{escape("https://droitromain.univ-grenoble-alpes.fr/Corpus/"+source_name,quote=True)}">原网页</a>{translated}。</p></aside>'
 doc=link_map[p.name]
 docs.append((doc,xhtml(title,'<h1 class="source-page-title">'+escape(title)+'</h1>'+note+body,'und')))

# Front matter and navigation.
coverage='''<p>本 EPUB 收录目录页及当前站点可访问的 186 个同站页面：新律 165 篇、敕令 10 篇、附录 9 篇、尤利安摘要 2 卷。目录未链接新律 136、137、163 及敕令 7、9、13；本书不补造这些正文。已链接的 Edicta I、V、VI 网页在正文位置标作 “Unknown text.”，页面虽已保存，但原站没有提供可整理的正文。</p>'''
translations_list=''.join('<li><a href="'+escape('translations/'+doc,quote=True)+'">'+escape(meta['title'])+'</a>（工作译稿，实际完成范围请看该卷开头）</li>' for doc,_ in translation_docs for meta in translation_meta if meta['doc']==doc)
front=f'''<h1>查士丁尼新律</h1><p><em>Iustiniani Novellae</em></p><p>据网页标示：Rudolfus Schoell 校订；Guilelmus Kroll 完成未竟工作，<em>Corpus Iuris Civilis</em>, vol. III。</p><p>中拉对照研究版：仅收逐段相邻排列的来源原文与中文译文，不另重复收录一整篇拉丁文原本。完整拉丁文原本见独立拉丁文版；各网页原始字节见项目目录中的 source_original/。原文网页显示的具体版本说明、录入者和来源引证以各篇译稿卷首及来源清单为准。</p><p>翻译责任说明：中文译文由 OpenAI Codex 及并行代理分批生成、整理，属于机器辅助工作译稿；目前尚未经古典法学专业译者终审，不能视为定本。</p><h2>导航目录</h2><p><a href="nav.xhtml">打开逐篇、逐章及段落导航目录</a></p><h2>收录范围</h2>{coverage}<p>网页呈现的正文以拉丁文为主。网页明确标注“Translated from the Greek”（由希腊文译出）的页面提供的是拉丁文本，并未同时提供相应希腊原文；Nov135、Nov142、Nov148、Nov153另有希腊字母片段。各页标记、罗马数字、编辑符号和来源缩写均按网页保留。网页未链接的编号不作补文。</p><h2>中文译稿状态</h2><p>网页实际提供正文的篇章均有逐段中文工作译稿，具体篇目与编号见各译稿卷首及项目目录。没有来源正文的 “Unknown text.” 页面不作补译；未链接的作品编号也不推造文本。译稿未经过专业古典法学审校，引用时应对照原文。</p><ul>{translations_list}</ul><h2>术语表</h2><p><a href="terminology.xhtml">打开术语表（工作版）</a></p><h2>来源、编码与权利说明</h2><p>来源网页：<a href="{BASE}">{BASE}</a>；下载日期 2026-09-27。原始 HTML、来源 URL、编码说明及 SHA-256 见随附项目目录的 <code>source_original/</code> 与 <code>source_manifest.json</code>。网站元数据标有 Alexandr Koptev 的版权归属；未发现明确再利用许可。本地研究归档不构成公开传播授权。</p><p>本电子版为 reflowable EPUB；不复制网页的装饰性背景图。底本和页面录入信息按原页分别记录。</p>'''
front_doc=xhtml('版本说明与收录范围',front,'zh-Hans','styles/book.css')

# Chinese navigation: include every Markdown heading, including paragraph-level headings.
def nav_link(name,label): return f'<li><a href="{escape(name,quote=True)}">{escape(label)}</a></li>'
def render_nav_item(item):
 nested='<ol>'+''.join(render_nav_item(child) for child in item['children'])+'</ol>' if item['children'] else ''
 return '<li><a href="'+escape(item['href'],quote=True)+'">'+escape(item['label'])+'</a>'+nested+'</li>'
def chinese_doc_title(filename,title):
 stem=Path(filename).stem
 ranges=re.search(r'_(\d+)-(\d+)_',stem)
 if stem.startswith('Novellae_'):
  if ranges:
   a,b=ranges.groups()
   suffix='（第89篇另收）' if (a,b)==('057','112') else ''
   return f'新律第{int(a)}—{int(b)}篇{suffix}'
  one=re.search(r'_(\d+)_',stem)
  return f'新律第{one.group(1)}篇' if one else title
 if stem.startswith('Edicta_'):
  if stem=='Edicta_008': return '敕令第八篇'
  return '十三篇敕令对读译稿（有正文部分）'
 if stem.startswith('Appendix_'): return '散见宪令附录 I—IX'
 if stem.startswith('Epitome_Juliani_'):
  if ranges: return f'尤利安摘要第{int(ranges.group(1))}—{int(ranges.group(2))}篇'
  one=re.search(r'_(\d+)_',stem)
  return f'尤利安摘要第{one.group(1)}篇' if one else title
 return title
def chinese_heading_label(filename,level,label):
 stem=Path(filename).stem
 s=' '.join(label.split())
 m=re.match(r'^Novella\s+([IVXLCDM]+|\d+)(?:\s*[—-]\s*(.*))?$',s,re.I)
 if m:
  num=m.group(1); tail=(m.group(2) or '').strip()
  in_paren=re.search(r'\（第\d+篇\）',tail)
  if in_paren: return tail
  return f'第{num}篇'+(f' {tail}' if tail else '')
 m=re.match(r'^Novella\s+([IVXLCDM]+)\s*\（第(\d+)篇\）$',s,re.I)
 if m: return f'第{m.group(2)}篇（{m.group(1)}）'
 m=re.match(r'^Iustiniani XIII Edicta\s+([IVXLCDM]+|\d+)$',s,re.I)
 if m: return f'敕令第{m.group(1)}篇'
 m=re.match(r'^Appendix constitutionum dispersarum\s+([IVXLCDM]+|\d+)$',s,re.I)
 if m: return f'附录第{m.group(1)}篇'
 m=re.match(r'^Constitutio\s+([IVXLCDM]+|\d+)(?:\s*[—-].*)?(?:\s*\((\d+)\))?$',s,re.I)
 if m: return f'摘要第{m.group(1)}篇'+(f'（{m.group(2)}）' if m.group(2) else '')
 m=re.match(r'^kp\.\s*(\d+)(?:\s*[—-].*)?$',s,re.I)
 if m:
  zh=re.search(r'（([^（）]*[\u3400-\u9fff][^（）]*)）',s)
  return f'kp.{m.group(1)}'+(f'（{zh.group(1)}）' if zh else '')
 if re.fullmatch(r'(?:Praefatio|序言(?:\s*\([^)]*\))?)',s,re.I): return '序言'
 if re.fullmatch(r'(?:Epilogus|结语(?:\s*\([^)]*\))?)',s,re.I): return '结语'
 m=re.match(r'^CAPUT\s+([IVXLCDM]+|\d+)(?:\b.*)?$',s,re.I)
 if m: return f'第{m.group(1)}章'
 m=re.match(r'^Caput\s+([IVXLCDM]+|\d+)(?:\s*—.*)?$',s,re.I)
 if m: return f'第{m.group(1)}章'
 m=re.fullmatch(r'([IVXLCDM]+)(?:\.(\d+))?',s)
 if m: return f'第{m.group(1)}章'+(f'第{m.group(2)}段' if m.group(2) else '')
 m=re.fullmatch(r'(?:paragraph|段落)\s*(\d+)',s,re.I)
 if m: return f'第{m.group(1)}段'
 m=re.match(r'^\d+\.(?:\s|$)',s)
 if m: return '第'+s.split('.',1)[0]+'段'
 return s
def translation_nav_entry(doc,meta,content):
 root=ET.fromstring(content); ns='{http://www.w3.org/1999/xhtml}'
 top={'href':'translations/'+doc,'label':chinese_doc_title(meta['file'],meta['title']),'children':[]}
 stack=[(1,top)]
 for node in root.iter():
  if not re.fullmatch(re.escape(ns)+r'h[2-6]',node.tag) or not node.attrib.get('id'): continue
  level=int(node.tag[-1]); label=' '.join(''.join(node.itertext()).split())
  item={'href':'translations/'+doc+'#'+node.attrib['id'],'label':chinese_heading_label(meta['file'],level,label),'children':[]}
  while stack and stack[-1][0]>=level: stack.pop()
  parent=stack[-1][1] if stack else top
  parent['children'].append(item); stack.append((level,item))
 return top
def roman_number(n):
 pairs=((1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),(90,'XC'),(50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I'))
 out=''
 for value,symbol in pairs:
  while n>=value: out+=symbol; n-=value
 return out
def latin_page_label(p):
 m=re.fullmatch(r'Nov(\d+)\.htm',p.name)
 if m: return 'Novella '+roman_number(int(m.group(1)))
 m=re.fullmatch(r'Ed(\d+)\.htm',p.name)
 if m: return 'Edictum '+roman_number(int(m.group(1)))
 m=re.fullmatch(r'App(\d+)\.htm',p.name)
 if m: return 'Appendix '+roman_number(int(m.group(1)))
 if p.name=='epitome_julien_1.htm': return 'Iuliani Epitome Latina — Constitutiones I—LXXX'
 if p.name=='epitome_julien_2.htm': return 'Iuliani Epitome Latina — Constitutiones LXXXI—CXXIV'
 return titles[p.name]
def latin_anchor_label(p,raw,visible):
 m=re.fullmatch(r'const\.(\d+)',raw,re.I)
 if m: return 'Constitutio '+m.group(1)
 m=re.fullmatch(r'const\.(\d+)\.(\d+)',raw,re.I)
 if m: return f'Constitutio {m.group(1)}, §{m.group(2)}'
 m=re.fullmatch(r'cap\.(\d+)',raw,re.I)
 if m: return 'cap.'+m.group(1)
 m=re.fullmatch(r'(\d+)\.praefatio(?:\.(pr\.|\d+))?',raw,re.I)
 if m:
  return 'Praefatio'+(', principium' if m.group(2)=='pr.' else (', §'+m.group(2) if m.group(2) else ''))
 m=re.fullmatch(r'(\d+)\.epilogus(?:\.(\d+))?',raw,re.I)
 if m: return 'Epilogus'+(', §'+m.group(2) if m.group(2) else '')
 m=re.fullmatch(r'(\d+)\.(Edictum|Scriptum|Notitia|Iusiurandum)(?:\.(pr\.|\d+))?',raw,re.I)
 if m:
  tail=', principium' if m.group(3)=='pr.' else (', §'+m.group(3) if m.group(3) else '')
  return m.group(2)+tail
 m=re.fullmatch(r'(\d+)\.(\d+)(?:\.(pr\.|\d+))?',raw,re.I)
 if m:
  caput=roman_number(int(m.group(2)))
  tail=', principium' if m.group(3)=='pr.' else (', §'+m.group(3) if m.group(3) else '')
  return 'Caput '+caput+tail
 if raw.isdigit(): return '§'+raw
 return visible or raw
def source_anchor_tree(p):
 entries=[]; lookup={}; current_const=None; seen=set()
 for node in walk(parsed[p.name]):
  if node.tag!='a': continue
  raw=node.attrs.get('id') or node.attrs.get('name')
  if not raw: continue
  target=anchor_maps[p.name].get(raw,slug(raw))
  if target in seen: continue
  seen.add(target)
  visible=re.sub(r'\s+',' ',all_text(node)).strip(' .\u00a0')
  item={'href':'text/'+link_map[p.name]+'#'+target,'label':latin_anchor_label(p,raw,visible),'children':[]}
  parent_raw=None
  if p.name.startswith('epitome_julien_'):
   m=re.fullmatch(r'const\.(\d+)',raw,re.I)
   if m: current_const=raw
   elif re.fullmatch(r'cap\.\d+',raw,re.I): parent_raw=current_const
   else:
    m=re.fullmatch(r'const\.(\d+)\.\d+',raw,re.I)
    if m: parent_raw='const.'+m.group(1)
  else:
   m=re.fullmatch(r'(\d+)\.(?:praefatio|Edictum|Scriptum|Notitia|Iusiurandum)',raw,re.I)
   if m and raw.count('.')==1: parent_raw=None
   else:
    m=re.fullmatch(r'(\d+)\.(praefatio|epilogus|Edictum|Scriptum|Notitia|Iusiurandum)\.(?:pr\.|\d+)',raw,re.I)
    if m: parent_raw=raw.rsplit('.',1)[0]
    else:
     m=re.fullmatch(r'(\d+)\.(\d+)\.(?:pr\.|\d+)',raw,re.I)
     if m: parent_raw=f'{m.group(1)}.{m.group(2)}'
  if parent_raw and parent_raw in lookup: lookup[parent_raw]['children'].append(item)
  else: entries.append(item)
  lookup[raw]=item
 return entries
def latin_source_page_entry(p):
 return {'href':'text/'+link_map[p.name],'label':latin_page_label(p),'children':source_anchor_tree(p)}
def group_items(items,label):
 return '<li><span>'+escape(label)+'</span><ol>'+''.join(render_nav_item(item) for item in items)+'</ol></li>'

translation_groups=[]
for prefix,label in [('Novellae_','查士丁尼新律中文对读译稿'),('Edicta_','查士丁尼十三篇敕令中文对读译稿'),('Appendix_','散见宪令附录中文对读译稿'),('Epitome_Juliani_','尤利安新律拉丁摘要中文对读译稿')]:
 items=[]
 for doc,body in translation_docs:
  meta=next(m for m in translation_meta if m['doc']==doc)
  if meta['file'].startswith(prefix): items.append(translation_nav_entry(doc,meta,body))
 if items: translation_groups.append(group_items(items,label))
zh_nav_items=nav_link('front.xhtml','版本与收录范围')+''.join(translation_groups)+(nav_link('terminology.xhtml','术语表（工作版）') if glossary_content else '')
nav_body='<nav epub:type="toc" id="toc-zh" xml:lang="zh-Hans" lang="zh-Hans"><h1>目录（中文）</h1><ol>'+zh_nav_items+'</ol></nav>'
nav=xhtml('目录（中文）',nav_body,'zh-Hans','styles/book.css')

# Latin index: list every named source anchor, including numbered paragraphs and kp./cap. locations.
latin_groups=[]
for regex,label in [(r'Nov\d+\.htm','Iustiniani Novellae'),(r'Ed\d+\.htm','Iustiniani XIII Edicta'),(r'App\d+\.htm','Appendix constitutionum dispersarum'),(r'epitome_julien_\d+\.htm','Iuliani Epitome Latina Novellarum Iustiniani')]:
 members=[latin_source_page_entry(p) for p in files if re.fullmatch(regex,p.name)]
 if members: latin_groups.append(group_items(members,label))
latin_body='<h1>Index Latinus</h1><p>Navigatio textuum Latinorum et titulorum atque paragraphorum fontis textus. Singula capita, principia, paragrapha et indicia kp./cap. ad ancoras in editione originali ducunt.</p><p><a href="nav.xhtml">Ad indicem Sinicum redi</a> · <a href="front.xhtml">Praefatio editionis</a></p><ol>'+''.join(latin_groups)+'</ol>'
latin_index=xhtml('Index Latinus',latin_body,'la','styles/book.css')

# Assemble package metadata and spine.
all_items=[('front.xhtml','front.xhtml','application/xhtml+xml',front_doc),('nav.xhtml','nav.xhtml','application/xhtml+xml',nav)]
all_items.append(('styles/book.css','styles/book.css','text/css',css))
for doc,body in translation_docs: all_items.append(('translations/'+doc,'translations/'+doc,'application/xhtml+xml',body))
if glossary_content: all_items.append((glossary_doc,glossary_doc,'application/xhtml+xml',glossary_content))
manifest_xml=[]; spine=[]
for i,(ident,href,media,content) in enumerate(all_items):
 manifest_xml.append(f'<item id="item{i}" href="{escape(href,quote=True)}" media-type="{media}"'+(' properties="nav"' if ident=='nav.xhtml' else '')+'/>')
 if media=='application/xhtml+xml':
  spine.append(f'<itemref idref="item{i}"'+(' linear="no"' if ident=='nav.xhtml' else '')+'/>')
opf=f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id" xml:lang="en">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="pub-id">urn:uuid:{uuid.uuid4()}</dc:identifier><dc:title>Novellae of Justinian: Original Text and Chinese Working Translation</dc:title><dc:creator>Rudolfus Schoell; Guilelmus Kroll (edition credits as reported by source)</dc:creator><dc:publisher>Local scholarly research edition</dc:publisher><dc:language>la</dc:language><dc:language>grc</dc:language><dc:language>zh-Hans</dc:language><dc:date>{date.today().isoformat()}</dc:date><dc:description>Source-preserving local compilation with incomplete Chinese working translation. See front matter for scope and rights status.</dc:description><meta property="dcterms:modified">{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}</meta></metadata>
<manifest>{''.join(manifest_xml)}</manifest><spine>{''.join(spine)}</spine></package>'''
container='<?xml version="1.0" encoding="utf-8"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
OUT.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(OUT,'w') as z:
 z.writestr('mimetype','application/epub+zip',compress_type=zipfile.ZIP_STORED)
 z.writestr('META-INF/container.xml',container,compress_type=zipfile.ZIP_DEFLATED)
 z.writestr('package.opf',opf,compress_type=zipfile.ZIP_DEFLATED)
 for ident,href,media,content in all_items:
  data=content.encode('utf-8') if isinstance(content,str) else content
  z.writestr(href,data,compress_type=zipfile.ZIP_DEFLATED)

# Structural validation and internal link/anchor audit.
with zipfile.ZipFile(OUT) as z:
 bad=z.testzip()
 names=z.namelist()
 assert names[0]=='mimetype' and z.getinfo('mimetype').compress_type==zipfile.ZIP_STORED
 assert bad is None, bad
 for name in names:
  if name.endswith(('.xhtml','.opf','.xml')):
   ET.fromstring(z.read(name))
 present=set(names); missing=[]; fragment_missing=[]; known_ids={}
 for name in names:
  if name.endswith('.xhtml'):
   root=ET.fromstring(z.read(name)); ns={'x':'http://www.w3.org/1999/xhtml'}
   known_ids[name]={e.attrib['id'] for e in root.iter() if 'id' in e.attrib}
 for name in names:
  if not name.endswith('.xhtml'): continue
  root=ET.fromstring(z.read(name))
  for e in root.iter():
   h=e.attrib.get('href')
   if not h: continue
   u=urlsplit(h)
   if u.scheme or u.netloc: continue
   if not u.path and not u.fragment: continue
   target=str((Path(name).parent/u.path).as_posix()) if u.path else name
   # Normalize relative path inside archive.
   parts=[]
   for part in target.split('/'):
    if part in ('','.'): continue
    if part=='..':
     if parts: parts.pop()
    else: parts.append(part)
   target='/'.join(parts)
   if target not in present: missing.append((name,h,target));continue
   if u.fragment and target in known_ids and u.fragment not in known_ids[target]: fragment_missing.append((name,h,target,u.fragment))
assert not missing, missing[:10]
assert not fragment_missing, fragment_missing[:10]
report={'epub':str(OUT),'zip_test':'passed','mimetype_first_uncompressed':True,'xhtml_xml_parse':'passed','internal_href_missing':missing,'missing_fragments':fragment_missing,'spine_documents':len(spine),'standalone_source_pages_embedded':0,'paired_translation_documents':len(translation_docs),'translation_files':translation_meta,'terminology_included':bool(glossary_content),'size_bytes':OUT.stat().st_size}
(ROOT/'epub_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

from pathlib import Path
from html.parser import HTMLParser
import zipfile,json,hashlib,re,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parent;M=json.loads((R/'source_manifest.json').read_text(encoding='utf-8'))
class Text(HTMLParser):
 def __init__(self): super().__init__(convert_charrefs=True); self.body=False; self.skip=[]; self.out=[]
 def handle_starttag(self,t,a):
  t=t.lower()
  if t=='body': self.body=True; return
  if self.body and t in {'script','style','noscript'}: self.skip.append(t)
 def handle_endtag(self,t):
  t=t.lower()
  if t=='body': self.body=False; return
  if self.skip and t in self.skip:
   i=len(self.skip)-1-self.skip[::-1].index(t); self.skip=self.skip[:i]
 def handle_data(self,d):
  if self.body and not self.skip: self.out.append(d)
def norm(s):return re.sub(r'\s+',' ',s).strip()
sha_errors=[];mirror_errors=[]
for rec in M['records']:
 p=R/rec['local_path']
 if not p.exists():sha_errors.append((rec['local_path'],'missing'));continue
 if hashlib.sha256(p.read_bytes()).hexdigest()!=rec['sha256']:sha_errors.append((rec['local_path'],'sha256 mismatch'))
 if p.name!='Novellae.htm' and not (R/'web'/p.name).exists():mirror_errors.append((p.name,'web missing'))
 elif p.name!='Novellae.htm' and (R/'web'/p.name).read_bytes()!=p.read_bytes():mirror_errors.append((p.name,'web bytes differ'))
source_pages=sorted((R/'source_original').glob('*.htm'))
edition_reports={};NS='{http://www.w3.org/1999/xhtml}'
def ettext(el):return (el.text or '')+''.join(ettext(c)+(c.tail or '') for c in list(el))
latin_epub=R/'Novellae_Schoell_Kroll_Latin.epub';text_mismatch=[]
with zipfile.ZipFile(latin_epub) as z:
 for p in source_pages:
  name='text/'+p.stem+'.xhtml'
  if name not in z.namelist():text_mismatch.append((p.name,'epub page absent'));continue
  src=p.read_bytes()
  try:s=src.decode('utf-8','strict')
  except UnicodeDecodeError:s=src.decode('latin-1')
  pa=Text();pa.feed(s)
  root=ET.fromstring(z.read(name));body=root.find(NS+'body');parts=[]
  for el in list(body):
   if el.attrib.get('class') in {'source-page-title','source-note'}:continue
   parts.append(ettext(el))
  got=norm(''.join(parts))
  # EPUB renders two French-translation image-button alt labels as accessible text.
  got=re.sub(r'\s*\[图片：Traduction française\]','',got)
  if norm(''.join(pa.out))!=got:text_mismatch.append((p.name,len(norm(''.join(pa.out))),len(got)))
edition_reports[latin_epub.name]={'mismatches':text_mismatch,'checked_pages':len(source_pages)}
bilingual=R/'Novellae_Schoell_Kroll_Chinese_Bilingual.epub'
with zipfile.ZipFile(bilingual) as z:
 names=z.namelist()
 paired_docs=[n for n in names if n.startswith('translations/translation-') and n.endswith('.xhtml')]
 standalone_sources=[n for n in names if n.startswith('text/') and n.endswith('.xhtml')]
edition_reports[bilingual.name]={'standalone_source_pages_embedded':len(standalone_sources),'paired_translation_documents':len(paired_docs),'layout':'Latin source paragraphs and Chinese translations are adjacent within each paired document'}
text_mismatch=edition_reports[latin_epub.name]['mismatches']
report={'manifest_rows':len(M['records']),'source_sha_mismatches':sha_errors,'offline_mirror_mismatches':mirror_errors,'epub_source_text_mismatches':text_mismatch,'epub_source_text_mismatches_by_edition':edition_reports,'checked_epub_pages':len(source_pages),'known_normalization':'The standalone Latin EPUB omits non-content Google Analytics script text present in some original HTML pages and renders two French-translation image-button alt labels as accessible text; exact original bytes remain archived.'}
(R/'source_integrity_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

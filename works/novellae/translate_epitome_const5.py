# -*- coding: utf-8 -*-
from html.parser import HTMLParser
from pathlib import Path
ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'source_original' / 'epitome_julien_1.htm'
OUTPUT = ROOT / 'translations' / 'Epitome_Juliani_005_Chinese.md'
class Paragraphs(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.depth=0; self.current=[]; self.items=[]
    def handle_starttag(self,tag,attrs):
        if tag=='p':
            if self.depth==0:self.current=[]
            self.depth+=1
        elif tag=='br' and self.depth:self.current.append(' ')
    def handle_endtag(self,tag):
        if tag=='p' and self.depth:
            self.depth-=1
            if self.depth==0:
                value=' '.join(''.join(self.current).split())
                if value:self.items.append(value)
    def handle_data(self,data):
        if self.depth:self.current.append(data)
raw=SOURCE.read_text(encoding='iso-8859-1')
a=raw.lower().find('<a name="const.5"');b=raw.lower().find('<a name="const.6"',a)
if a<0 or b<0:raise RuntimeError('Could not isolate Constitution V')
p=Paragraphs();p.feed(raw[a:b]); original=p.items
if len(original)!=3:raise RuntimeError(f'Expected 3 text blocks, got {len(original)}')
translations=[
'1. 本宪令在其有效期间保留现有神职人员人数。此后，规定君士坦丁堡城的神职人员人数如下：教会应有司铎六十人、执事一百人、女执事四十人、副执事九十人、读经员一百一十一人、歌咏者二十五人、司门员一百人。',
'第二十三章：不得借助他人庇护，使神职人员从较小教会转入较大教会；并关于神职人员的供养。',
'2. 在较小教会取得神职身份的人，不得随后借助他人的庇护转入较大的教会。若发生此类转任，应属无效，不产生任何效力。任何人也不得任命或设立神职人员却不给予他们生活供养；必须二者择一：要么不任命神职人员，要么在任命后提供其生活所需。'
]
parts=['# 《尤利安新律拉丁摘要》第一卷：Constitutio V 中译工作稿','',
'> 本篇拉丁文本据网页所列 Hänel, Leipzig 1873；网页说明这部摘要由尤利安将《查士丁尼新律》自希腊文译成拉丁文。以下保留网页转录的拼写（包括 u/v 用法）、章号和段号。',
'> 来源：`source_original/epitome_julien_1.htm`；页面题为 *Iuliani Epitome Latina Novellarum Iustiniani: Const. 1–80 (Hänel)*，网页来源见 [原页](https://droitromain.univ-grenoble-alpes.fr/Corpus/epitome_julien_1.htm)。','',
'## Constitutio V — De numero clericorum Constantinopolitanae ciuitatis','',
'**篇号原文：** `CONST. V`','','**逐段对读**']
labels=['Constitutio V, paragraph 1','Caput 23','Constitutio V, paragraph 2']
for label,src,zh in zip(labels,original,translations):
    parts += ['',f'### {label}','','**原文（拉丁文）**','',f'> {src}','','**中文译文**','',f'> {zh}']
parts += ['', '## 译者注', '', '1. *alimoniae* 在此指神职人员的生活供养；原文未规定供养的具体财源或数额。', '']
OUTPUT.write_text('\n'.join(parts),encoding='utf-8')
print(f'Wrote {OUTPUT} ({len(original)} source blocks and {len(translations)} translations).')

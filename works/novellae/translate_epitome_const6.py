# -*- coding: utf-8 -*-
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'source_original'/'epitome_julien_1.htm'
OUTPUT=ROOT/'translations'/'Epitome_Juliani_006_Chinese.md'
class Paragraphs(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.depth=0;self.current=[];self.items=[]
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
a=raw.lower().find('<a name="const.6"');b=raw.lower().find('<a name="const.7"',a)
if a<0 or b<0:raise RuntimeError('Could not isolate Constitution VI')
p=Paragraphs();p.feed(raw[a:b]);orig=p.items
if len(orig)!=15:raise RuntimeError(f'Expected 15 text blocks, got {len(orig)}')
zh=[
'''1. 本宪令第一章论述主教祝圣，程序应如下进行。首先必须审查候选主教的生活是否良好、是否可受指摘，以及是否有良好证言为其作证。若候选人具有官署人员或城邑议员身份，也不得成为主教；唯有自幼在修道院生活、因而免除上述身份者例外，但仍须依法向议员团缴纳其财产的四分之一。平信徒不得立即升任主教；仅仅假装曾取得神职身份也不够。候选主教不得有妻子、妾、子女或孙辈，无论这些后代为合法婚生还是法律不承认的身份。若有人违反上述规定，则被祝圣者和祝圣者本人均应被逐出主教职位。也不得以交付金钱的方式成为主教。候选人必须是修士或神职人员；但至少应已公开处于神职身份六个月。祝圣时，他还必须宣读神圣教规。祝圣者应询问他能否遵守神圣教规的一切规定；若他否认自己能够遵守，就不得为他祝圣。若他承诺将尽人所能遵守诸圣教规，祝圣者便应告诫并预先说明：若不遵守神圣教规，他就会与上帝疏离，也不会被列入虔敬主教之中。因为教父教规应具有法律的效力。若有人给付金钱并因此被任命为主教，则不仅他本人不得列入主教之中，祝圣他的人也不得列入主教之中；作为祝圣对价给付的金钱或财物应判归神圣教会，无论给付者是主教还是神职人员。收受者不仅丧失财物，也丧失其神职品级与荣誉。若收受金钱或财物的是平信徒，也应丧失所收财物，并被强令向圣教会支付等额罚金。若此人担任官职，则须停止任职，并被判处不可撤销的流放。若有人原为司铎或执事，却通过交付金钱升至主教高位，则他不仅应停止担任主教，还应丧失先前的司铎或执事品级。主教祝圣应在全体基督徒民众面前进行，使任何人如愿时都可提出异议。若在祝圣前有人提出异议，则在异议经过审理、并已充分查明候选人无辜以前，不得为其祝圣。若尚未审理异议就已祝圣，则被祝圣者和任命他的人均应丧失职位。若提出异议者被证明是诬告者，或放弃异议而不继续诉讼，则由祝圣该主教的人禁止其终身领受圣餐。''',
'第二十五章：同前。',
'2. 虔敬的主教不得离开自己的教会居住超过一年，除非是奉皇帝命令行事。宗主教应强令主教留在自己的教会，不得作长途旅行，除非奉君主命令。若主教未经君主命令，离开自己的教会超过一年，则该地区的宗主教应依合法公告召其返回，即遵守神圣教规所规定的程序。若被召者不服从而继续缺席，宗主教就应将他从主教名册中除名，并另行任命一人接替。若缺席者不是都主教，而是某一市镇的主教，则上述本应由宗主教采取的措施应由都主教采取。主教若为诉讼事务而旅行，不得准许。主教不应亲自诉讼，而应通过自己的神职人员办理，无论是使节代理人还是教会财务官；他们应向君主陈请，并将获准所求之事。',
'第二十六章：同前。',
'3. 主教不得前往君士坦丁堡，除非先从自己的都主教处取得一封致皇帝的信；神圣教规称此类信件为“推荐信”，其中应说明主教此次出行确有必要。若希望前往君士坦丁堡的是都主教本人，则应从其所在地区的宗主教处取得信件。前来者不得擅自直接晋见皇帝，而应先拜访宗主教或其所在地区的使节代理人，并向他们说明来访缘由。主教也可通过大教会的报告官，或宗主教的使节代理人，将情况报告皇帝，并由此请求得到答复。',
'第二十七章：关于神职人员。',
'4. 除非某人有良好声誉且通晓文字，否则不得成为神职人员；不识字者不能担任神职。司铎和执事应学习神圣祷文及教会教规；任命他们时不得存在可受指摘之处、正当异议或金钱给付，且应已免除官署人员或城邑议员身份，除非符合本宪令第一章所述的例外规则。',
'第二十八章：同前。',
'5. 有过两次婚姻者不得成为执事或司铎。若某人娶了一名与其丈夫分离、且由她本人离开丈夫的妇女，也不得成为执事或司铎。若其有妾，规则亦同；因为此类人应以贞洁生活。所谓贞洁，是指拥有或曾拥有一名贞洁的妻子，并且该妻子嫁给他时仍为处女。若某位司铎、执事或副执事娶妻或纳妾，无论秘密、公开或借其他名义进行，都应丧失神职荣誉，被褫夺身份而成为平信徒。',
'第二十九章：关于女执事。',
'6. 我们关于神职人员所说的规则，也适用于女执事。宪令规定，女执事须年满五十岁方可任命，但应为处女或仅有过一名丈夫。若某妇女因某种必要原因在未满五十岁时被任命为女执事，则她不得居住在别处，只能住在女修道者的修院中；该处不得有男子共同生活，她也不得随心所欲地生活。女执事不得带任何人同住并称其为兄弟、亲属，或人们所谓的“agapetoi”（即“爱侣”）。女执事应独自居住，或仅可接纳真正的兄弟同住。若有人怀疑她与一个假称兄弟的男子同住，则要么从一开始就不得为她祝圣，要么在她已受祝圣后剥夺其荣誉。她与引诱她的人应承受神圣宪令为惩治引诱者所规定的刑罚。祝圣女执事时，应告诫她：若她日后结婚或选择另一种生活，就应被惩以利剑，财产判归修道院或教会。引诱她的人也应受同样刑罚，但其财产应由国库追取。',
'第三十章：关于神职人员的同一规则。',
'7. 无论读经员、副执事、执事还是司铎，若轻蔑其神职荣誉而转入另一种生活，应受以下两种处置之一：或者连同其财产归入城邑议员身份；或者若该城市有较多议员，且此人身份较低，则将他编入官署人员身份，即税务吏一类。',
'第三十一章：同前，关于神职人员人数。',
'8. 主教不得随意大量任命神职人员；神职人员人数也应按教会收入加以调节。若建造神圣教会的人从一开始就确定了该教会应祝圣的神职人员人数，则应维持该人数。若未预先规定人数，则不得因私人交情或偏袒而加重神圣教会负担；应由宗主教、都主教及其他主教审慎调节人数。任何人，无论私人还是平信徒，只要发现有人违反我们所述规则，均可将此事报告皇帝。'
]
labels=['Constitutio VI, paragraph 1','Caput 25 — Idem','Constitutio VI, paragraph 2','Caput 26 — Idem','Constitutio VI, paragraph 3','Caput 27 — De clericis','Constitutio VI, paragraph 4','Caput 28 — Idem','Constitutio VI, paragraph 5','Caput 29 — De diaconissis','Constitutio VI, paragraph 6','Caput 30 — Idem de clericis','Constitutio VI, paragraph 7','Caput 31 — Idem de numero clericorum','Constitutio VI, paragraph 8']
parts=['# 《尤利安新律拉丁摘要》第一卷：Constitutio VI 中译工作稿','',
'> 本篇拉丁文本据网页所列 Hänel, Leipzig 1873；网页说明这部摘要由尤利安将《查士丁尼新律》自希腊文译成拉丁文。以下保留网页转录的拼写（包括 u/v 用法）、章号和段号。',
'> 来源：`source_original/epitome_julien_1.htm`；页面题为 *Iuliani Epitome Latina Novellarum Iustiniani: Const. 1–80 (Hänel)*，网页来源见 [原页](https://droitromain.univ-grenoble-alpes.fr/Corpus/epitome_julien_1.htm)。','',
'## Constitutio VI — De episcopis et clericis','', '**篇号原文：** `CONST. VI`','','**逐段对读**']
for label,src,cn in zip(labels,orig,zh):parts += ['',f'### {label}','','**原文（拉丁文）**','',f'> {src}','','**中文译文**','',f'> {cn}']
parts += ['', '## 译者注', '', '1. *officialis* 暂译“官署人员”，*curialis* 译“城邑议员”；两者身份及强制承担的职责不同，未合并处理。', '2. *apocrisiarius*、*referendarius*、*oikonomos* 分别暂译“使节代理人”“报告官”“教会财务官”；制度职掌仍应结合古典法术语表复核。', '3. *agapetoi* 为原文所录希腊语转写，译文保留音译并作概括释义。', '4. *taxeotica* 为网页拉丁文本保留的希腊语制度名称，暂释作税务官署身份，未据此推定具体职位。', '']
OUTPUT.write_text('\n'.join(parts),encoding='utf-8')
print(f'Wrote {OUTPUT} ({len(orig)} source blocks, {len(zh)} translations).')

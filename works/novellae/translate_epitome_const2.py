from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'source_original' / 'epitome_julien_1.htm'
OUTPUT = ROOT / 'translations' / 'Epitome_Juliani_002_Chinese.md'

class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.current = []
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag == 'p':
            if self.depth == 0:
                self.current = []
            self.depth += 1
        elif tag == 'br' and self.depth:
            self.current.append(' ')

    def handle_endtag(self, tag):
        if tag == 'p' and self.depth:
            self.depth -= 1
            if self.depth == 0:
                value = ' '.join(''.join(self.current).split())
                if value:
                    self.items.append(value)

    def handle_data(self, data):
        if self.depth:
            self.current.append(data)

raw = SOURCE.read_text(encoding='iso-8859-1')
start = raw.lower().find('<a name="const.2"')
end = raw.lower().find('<a name="const.3"', start)
if start < 0 or end < 0:
    raise RuntimeError('Could not isolate Constitution II in the archived source')
parser = Paragraphs()
parser.feed(raw[start:end])
originals = parser.items
if len(originals) != 10:
    raise RuntimeError(f'Expected 10 text paragraphs in Constitution II; found {len(originals)}')

translations = [
    '1. 任何再婚的妇女或男子，都不得在婚前赠与或嫁资中偏袒自己的某一子女；对于本人仅享有用益权而不享有所有权的财产，应使所有子女按均等份额取得所有权。',
    '第六章：同前。',
    '2. 再婚的丈夫或妻子若处分嫁资或婚前赠与的财物，该处分无论何时作出，既不视为有效，也不视为无效，而暂处于未定状态。若处分财物的父母先于其子女死亡，则该处分无论如何均应撤销。反之，若子女先于仍在世的父母死亡，则处分在该父母因子女死亡而取得的份额范围内有效；也就是说，处分只在该父母依嫁资或赠与文书约定、于子女出生后死亡时本可取得的份额内发生效力。对于其余份额，处分不发生效力，除非子女以遗嘱或无遗嘱继承方式将作出处分的父母指定为继承人。',
    '第七章：同前。',
    '3. 儿子无遗嘱死亡的，其从嫁资或婚前赠与中享有的份额，不归仍在世的父母；只有其兄弟姐妹得被召来取得该份额，但以死者没有子女为限，因为死者的子女优先于其兄弟姐妹和父母。至于死者留下的其他财产，父母应与兄弟姐妹一同受召继承，无论父母是否再婚。若儿子立遗嘱后死亡，则由遗嘱中指定的人受领，但以“违反义务遗嘱之诉”没有使该遗嘱失效为限。',
    '第八章：同前。',
    '4. 妻子在丈夫死亡后再婚的，她从先前婚姻的婚前赠与中取得的财物，应依下列方式管理。若财物为不动产，则由该妇女持有，并在子女尚存时为子女保存。若子女死亡，则她应无论如何保有因子女死亡而归她的财产份额，其余部分由子女的继承人取得。若婚前赠与包含动产，则财物由子女持有；子女应向母亲支付利息，按每月百分之一的三分之一计算，并由母亲提供适当担保，保证此后每一期间均如数支付该利息。若婚前赠与包含金、银和衣物，则母亲可以选择提供担保并管理这些财物，或向自己的子女收取上述利息。若婚前赠与同时包含动产和不动产，则不动产由母亲持有，以其收益维持生活；动产则依上述区分由子女持有。',
    '第九章。',
    '关于仅被记载而未实际交付或给付的嫁资。',
    '5. 若有人娶妻时，不仅记载了婚前赠与，而且已经实际交付该赠与；而妻子虽记载了嫁资，却在丈夫生前始终未实际交付任何嫁资，那么丈夫死亡后，妻子不得取得婚前赠与，因为她自己并未交付嫁资。若她完全没有交付嫁资，丈夫死后便不得从婚前赠与中取得任何利益；若她交付了部分嫁资，则丈夫死后，她仅按已交付的部分比例，从婚前赠与中取得利益。本宪令也适用于尚未解除的婚姻。还应知道，本宪令若干章的规定，已由关于婚姻的第三十六号宪令加以变更。'
]

parts = [
    '# 《尤利安新律拉丁摘要》第一卷：Constitutio II 中译工作稿',
    '',
    '> 本篇拉丁文本据网页所列 Hänel, Leipzig 1873；网页说明这部摘要由尤利安将《查士丁尼新律》自希腊文译成拉丁文。以下保留网页转录的拼写（包括 u/v 用法）、章号、段号和术语。',
    '> 来源：`source_original/epitome_julien_1.htm`；页面题为 *Iuliani Epitome Latina Novellarum Iustiniani: Const. 1–80 (Hänel)*，网页来源见 [原页](https://droitromain.univ-grenoble-alpes.fr/Corpus/epitome_julien_1.htm)。',
    '',
    '## Constitutio II — De his qui ad secundas nuptias migrauerunt',
    '',
    '**篇号原文：** `CONST. II`',
    '',
    '**逐段对读**',
]
labels = [
    ('Constitutio II, paragraph 1', originals[0], translations[0]),
    ('Caput 6 — Idem', originals[1], translations[1]),
    ('Constitutio II, paragraph 2', originals[2], translations[2]),
    ('Caput 7 — Idem', originals[3], translations[3]),
    ('Constitutio II, paragraph 3', originals[4], translations[4]),
    ('Caput 8 — Idem', originals[5], translations[5]),
    ('Constitutio II, paragraph 4', originals[6], translations[6]),
    ('Caput 9', originals[7], translations[7]),
    ('Caput title', originals[8], translations[8]),
    ('Constitutio II, paragraph 5', originals[9], translations[9]),
]
for label, original, translation in labels:
    parts += ['', f'### {label}', '', '**原文（拉丁文）**', '', f'> {original}', '', '**中文译文**', '', f'> {translation}']
parts += ['', '## 译者注', '', '1. *tertia centesimae* 暂按月利率为 centesima 的三分之一译作“每月百分之一的三分之一”。《查士丁尼法典》4.32.26 有相同的 *tertiam partem centesimae usurarum* 表述，参见[该条](https://droitromain.univ-grenoble-alpes.fr/Corpus/CJ4.htm)；本摘要此句未明示计息周期，故译法保留为工作解释。', '2. 第五段末明示部分规定已被第三十六号婚姻宪令变更；本译文保留该限定，不据此改写本篇规则。', '']
OUTPUT.write_text('\n'.join(parts), encoding='utf-8')
print(f'Wrote {OUTPUT} ({len(originals)} source paragraphs, {len(translations)} Chinese translations).')

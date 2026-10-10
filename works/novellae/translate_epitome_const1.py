from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'source_original' / 'epitome_julien_1.htm'
OUTPUT = ROOT / 'translations' / 'Epitome_Juliani_001_Chinese.md'

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
start = raw.lower().find('<a name="const.1"')
end = raw.lower().find('<a name="const.2"', start)
if start < 0 or end < 0:
    raise RuntimeError('Could not isolate Constitution I in the archived source')
parser = Paragraphs()
parser.feed(raw[start:end])
originals = parser.items
if len(originals) != 7:
    raise RuntimeError(f'Expected 7 text paragraphs in Constitution I; found {len(originals)}')

translations = [
'''1. 我们从《学说汇纂》和敕令中得知：父母、子女、兄弟姐妹以及保护人，对我们的财产享有某一确定份额；除非他们对我们显有忘恩行为，否则无论如何都必须为其保留该份额。至于其他不属于父母、子女、兄弟或保护人的人，无论是否忘恩，都只依我们的意思成为我们的继承人，或从我们的遗产中取得利益。既已如此区分，现来看本宪令所提出的规则。其效力如下：若有人指定其父母、子女、兄弟或保护人为继承人，并为他人留下法律所承认的遗赠或信托遗赠；如果书面指定的继承人履行死者的意思，不拖延给付遗赠，便稳固取得死者的遗产，并得享有遗嘱处分的效力，因为他没有任由该处分被推翻。反之，若他认为应当违背遗嘱人的意思，并拖延给付受遗赠人，以致受遗赠人诉至法官并取得催告判决，而继承人仍继续拖延，直至司法裁判作出后一年期限届满，则指定继承人只能取得依法应归自己的特留份，丧失其余部分。该部分若有替代继承人，首先归替代继承人；若无替代继承人，则归共同继承人；若也无共同继承人，则归概括信托遗赠受益人。若概括信托遗赠受益人有数人，该部分归在信托遗赠中受益份额较大者。若上述各类人均不存在，则该部分归受遗赠人；若也无受遗赠人，则归遗嘱人授予自由身份的人。上述任何人接受所归份额，都必须完整履行遗嘱人的意思。因此，他也必须提供担保，保证全面履行死者遗嘱所载事项，并遵循以下顺序：在受遗赠人和概括信托遗赠受益人之间，概括信托遗赠受益人优先于其他受遗赠人及信托遗赠受益人。若无概括信托遗赠受益人，则由获较大遗赠或信托遗赠者受领。若这些人无人能够或愿意接受该部分，则召集遗嘱人授予自由身份的人；不得任意召集，而须按遗嘱书写的顺序，首先受授自由身份者优先。若第一人不愿或不能接受该部分，则由第二位受授自由身份者受领。以上规定适用于父母、子女、兄弟姐妹或保护人之一被指定为继承人的情形。若指定继承人是外人，并在司法判决后起算的整整一年期间拖延受遗赠人，则该指定继承人不得取得任何份额或利益；遗嘱人给他的全部财产均应剥夺，并按上文同一顺序、同一规则移交；受召受领者也须以相同方式提供担保，保证履行死者遗嘱所载事项。若前述任何人均未出现，则死者的阿格纳特亲属（父系宗亲）或科格纳特亲属（血亲）也可受领，即使遗嘱中完全没有提到他们。若这类人也没有出现，则任何外人只要愿意接受遗产并担保履行遗嘱，也可受领。若也找不到愿按上述方式担保承受死者继承的人，则财产归国库追取，国库亦须履行遗嘱人的意思。另有一点确定无疑：若儿子在父亲遗嘱中被正当剥夺继承权，便不得借本宪令之机，无论依遗嘱还是无遗嘱继承，从中取得任何利益。凡依本法被召来请求取得财产的人，均享有继承人的一切权利，即接受继承以及以继承人身份处理事务的权利，并且可以起诉，也可以被诉。以上规则还适用于这样的情形：遗嘱人所命令的给付或行为，并非由继承人作出，而是由受遗赠人、信托遗赠受益人，或因死亡原因取得某物的人作出；此时，受召顺序从受遗赠人的替代人开始，终于国库。''',
'''Caput 2. 关于法尔基第法。''',
'''2. 若有人在遗嘱中被指定为继承人，而遗嘱中留下了遗赠或信托遗赠；他担心遗赠或信托遗赠可能耗尽死者的全部财产，使自己不能从所承受的遗产中取得任何利益，那么，若他希望完整保留法尔基第法的利益，就应在受遗赠人及信托遗赠受益人在场时，对遗嘱人遗留的财物制作清册；此处所指为居住在同一城市的受益人。但若他们因女性身份、地位、疾病、年龄、拘禁或其他必要原因而无法到场，则应由合法管理其事务的人代表他们参加清册编制。若受遗赠人或信托遗赠受益人全都无法到场，则应传唤三名诚信和声誉均经认可的证人。证人须来自编制清册的城市，清册应在他们亲眼见证、在场的情况下编成。在此事项上，我们不单独信任书吏。若受遗赠人日后返回，认为继承人窃取了某些财物、将其隐匿而未列入清册，他们可以通过拷问遗产中的奴隶查明真相，并揭露继承人的欺诈；同时，还应强令继承人宣誓，保证自己编制清册时绝无欺诈，证人也应被强令宣誓，证明他们不知道书面指定继承人有任何欺诈。上述规则适用于受遗赠人到场并亲自出席、由其代理人参加，或者受遗赠人缺席而有三名声誉良好的证人到场的情形。若受遗赠人虽在当地，却不愿亲自到场，也不愿派人参加清册编制，则继承人可自由邀请三名证人见证并编制清册；此后，即使受遗赠人希望通过拷问遗产奴隶、或令继承人及证人宣誓来查明真相，也不得据此提出阻碍。遵守以上全部事项的人，保有法尔基第法的利益。若他既不编制清册，也不遵守上述程序，则应知道自己必须向受遗赠人或信托遗赠受益人支付全部遗赠及信托遗赠；即使遗嘱人的财产不足，有时也会被迫以自己的财产给付遗赠或信托遗赠。全部这一争议，仅在遗嘱人不了解自己财产数额、因而留下过多遗赠或信托遗赠时适用。反之，若遗嘱人明知自己有多少财产，且特别表示不许继承人享用法尔基第法的利益，就必须遵从他的意思。若遗嘱人指定的继承人宁愿接受该遗产，就必须毫无扣减地支付全部遗赠和信托遗赠；他不应取得任何利益，只有因无偿遵从遗嘱人意思而体现的敬意。若他拒绝继承，则由替代继承人受领，其后依次为共同继承人、概括信托遗赠受益人、受遗赠人、被授予自由身份者、无遗嘱继承的阿格纳特亲属或科格纳特亲属；这些人均未出现时，由外人受领；外人之后则归国库。''',
'''Caput 3. 受遗赠人之间的平等。''',
'''3. 书面指定的继承人不得自行决定向某些受遗赠人足额给付、向另一些仅部分给付、而对其余人完全不给付；他必须按比例向所有受遗赠人给付，无论是足额还是按比例扣减，均应维护公平。因为，若他从一开始就知道财产数额，便不应扣减遗赠；若已向某些人足额给付，就必须向所有人履行遗赠，除非发生某种异常事件，导致遗嘱人的财产减少。''',
'''Caput 4. 遗赠应在一年内给付。''',
'''4. 遗赠无论如何都应在一年之内给付。该一年的起算点，应为被告因支付遗赠而经司法判决催告之时。若因继承人的过错而使一年届满，未支付遗赠的继承人就应丧失遗嘱人的遗产，遗产改由上文提及的人受领；但对未成年人、少年人而言，不得因这段一年期间造成任何不利，因为他们有双重救济：既可请求恢复原状，也可对其监护人或保佐人提起适当的诉讼。以上规定无论遗嘱或遗愿以书面还是非书面形式作出，均应适用；并且适用于所有人，无论其为私人、军人、宗教人士还是皇室人员。'''
]

sections = [
    ('Caput 1 — Si heres legata soluere noluerit', originals[0], translations[0]),
    ('Caput 2 — Ad legem Falcidiam', originals[1], translations[1]),
    ('Constitutio I, paragraph 2', originals[2], translations[2]),
    ('Caput 3 — De legatariorum exaequatione', originals[3], translations[3]),
    ('Constitutio I, paragraph 3', originals[4], translations[4]),
    ('Caput 4 — Vt legata intra annum praestentur', originals[5], translations[5]),
    ('Constitutio I, paragraph 4', originals[6], translations[6]),
]

parts = [
    '# 《尤利安新律拉丁摘要》第一卷：Constitutio I 中译工作稿',
    '',
    '> 本篇拉丁文本据网页所列 Hänel, Leipzig 1873；网页说明这部摘要由尤利安将《查士丁尼新律》自希腊文译成拉丁文。以下保留网页转录的拼写（包括 u/v 用法）、章号、段号和术语，不将其改写为希腊原文。',
    '> 来源：`source_original/epitome_julien_1.htm`；页面题为 *Iuliani Epitome Latina Novellarum Iustiniani: Const. 1–80 (Hänel)*，网页来源见 [原页](https://droitromain.univ-grenoble-alpes.fr/Corpus/epitome_julien_1.htm)。',
    '',
    '## Constitutio I — Si heres legata soluere noluerit',
    '',
    '**篇号原文：** `CONST. I`',
    '',
    '**逐段对读**',
]
for label, original, translation in sections:
    parts += ['', f'### {label}', '', '**原文（拉丁文）**', '', f'> {original}', '', '**中文译文**', '', f'> {translation}']
parts += ['', '## 译者注', '', '1. *legatum*、*fideicommissum* 分别译作“遗赠”“信托遗赠”；*fideicommissarius generalis* 暂译“概括信托遗赠受益人”，以区别特定受益人。', '2. *agnati* 与 *cognati* 在本篇并列，暂分别译作“阿格纳特亲属（父系宗亲）”与“科格纳特亲属（血亲）”；此为工作译法，需在全书术语表统一复核。', '3. *publicum* 按本段国库承受遗产的语境译作“国库”。', '']
OUTPUT.write_text('\n'.join(parts), encoding='utf-8')
print(f'Wrote {OUTPUT} ({len(originals)} source paragraphs, {len(translations)} Chinese translations).')

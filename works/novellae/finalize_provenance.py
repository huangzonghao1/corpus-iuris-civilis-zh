from pathlib import Path
from html import unescape
import json,re
R=Path(__file__).resolve().parent
p=R/'source_manifest.json'; m=json.loads(p.read_text(encoding='utf-8'))
records=m['records']; names={Path(x['local_path']).name for x in records}
greek_script_pages=[]; greek_translation_pages=[]; body_gaps=[]
for record in records:
    name=Path(record['local_path']).name
    raw=(R/record['local_path']).read_bytes()
    try: page=raw.decode('utf-8')
    except UnicodeDecodeError: page=raw.decode('latin-1')
    visible=unescape(re.sub(r'<[^>]*>',' ',page))
    if re.search(r'Unknown\s+text\s*\.',visible,re.I): body_gaps.append(name)
    has_greek=bool(re.search(r'[\u0370-\u03ff\u1f00-\u1fff]',visible))
    says_greek=bool(re.search(r'Translated\s+from\s+the\s+Greek',visible,re.I))
    if name=='Novellae.htm': language='多语目录页：英语编辑说明与拉丁文作品题名'
    elif has_greek:
        language=('拉丁文本；网页标注“Translated from the Greek”（由希腊文译出），并含希腊文片段，未提供希腊原文'
                  if says_greek else '以拉丁文为主，含希腊文片段')
        greek_script_pages.append(name)
    elif says_greek:
        language='拉丁文本；网页标注“Translated from the Greek”（由希腊文译出），未提供希腊原文'
        greek_translation_pages.append(name)
    elif name.startswith('epitome_'):
        language='拉丁文摘要正文'
    else: language='拉丁文正文'
    record['page_language_note']=language
    if says_greek and name not in greek_translation_pages: greek_translation_pages.append(name)
linked={Path(x['local_path']).name for x in records if Path(x['local_path']).name!='Novellae.htm'}
nov=sorted(int(re.fullmatch(r'Nov0*(\d+)\.htm',n).group(1)) for n in linked if re.fullmatch(r'Nov0*(\d+)\.htm',n))
ed=sorted(int(re.fullmatch(r'Ed0*(\d+)\.htm',n).group(1)) for n in linked if re.fullmatch(r'Ed0*(\d+)\.htm',n))
app=sorted(int(re.fullmatch(r'App0*(\d+)\.htm',n).group(1)) for n in linked if re.fullmatch(r'App0*(\d+)\.htm',n))
epi=sorted(n for n in linked if n.startswith('epitome_'))
m['scope_inventory']={'same_site_linked_pages':len(linked),'Novellae_expected_numbers':list(range(1,169)),'Novellae_downloaded_links':nov,'Novellae_unlinked_numbers':sorted(set(range(1,169))-set(nov)),'Edicta_downloaded_links':ed,'Edicta_unlinked_numbers':[n for n in range(1,14) if n not in ed],'Appendix_downloaded_links':app,'Epitome_links':epi,'missing_linked_pages':m.get('failed_pages',[])}
m['scope_inventory']['linked_pages_without_body_text']=body_gaps
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(R/'README.md').write_text('''# Iustiniani Novellae — 本地整理与双语 EPUB 工作目录

## 来源与版本

- 目录页：[Iustiniani Novellae](https://droitromain.univ-grenoble-alpes.fr/Corpus/Novellae.htm)，下载日期：2026-09-27（Asia/Shanghai）。
- 目录署名：Rudolfus Schoell；目录说明其身后由 Guilelmus Kroll 完成，列为 *Corpus Iuris Civilis*, vol. III。
- 单篇网页各自的底本说明和录入者可能不同，应以该页原文为准。例如第一篇说明依据 Schoell 与 Kroll 的拉丁文本，并注明网页文本由 Dr. Ingo Maier 提交；这两种贡献已分别记录。
- 网页目录包括新律、*Iustiniani XIII Edicta*、*Appendix constitutionum dispersarum*，以及以 Hänel 版本为依据的 *Iuliani Epitome Latina Novellarum Iustiniani*。摘要页面自称依据 HÄNEL 1873 年版。

## 本次下载范围

截至本地清点，已保存目录页和 186 个同站链接页，未发现网络层面失效的链接页。目录存在没有链接的编号：新律 136、137、163；敕令 7、9、13。另有已链接的 Edicta I、V、VI 页面在正文位置标作 “Unknown text.”；这些页面已保存，但没有可据以补译的正文。未据缺号或空缺补造原文，也未从其他版本拼接。细目见 `source_manifest.json`。

`source_original/` 保存下载所得页面原始字节；`web/` 提供离线页面副本和目录。原始站点使用了装饰性图片和站外来源链接，这些外部资源没有随正文抓取；网页正文与站内页面链接保存在本地。

## 正文语种与页面说明

正文页面实际提供的文本整体以拉丁文为主。网页明确标注“Translated from the Greek”（由希腊文译出）的页面为：新律 32、121、122、126、135、139、141、142、144、148、149、151—158、160—162、164—168；敕令 2—4、10—12；附录 4—5。此处指网页呈现的是拉丁文译本，并不表示本地保存了相应希腊原文。新律 135、142、148、153 另含希腊字母词句片段，已在 EPUB 中保留。逐页的语言说明见 `source_manifest.json`。

## 编码与来源校验

`source_manifest.json` 为每个本地网页记录来源 URL、状态、文件长度和 SHA-256。多数页面实际字节仅含 ASCII 字符，页面头部声明 ISO-8859-1；目录的 HTTP 响应声明 UTF-8；Nov135、Nov142、Nov148、Nov153 含有效 UTF-8 字节，且各自 meta 声明 UTF-8。EPUB 构建时应按字节与页面内容正确解码，不可机械沿用错误的旧 meta 声明。

## 使用与权利状态

站点根页的元数据将版权归属标为 Alexandr Koptev。本次检查未发现 `robots.txt`（请求返回 404）或明确的网页再利用许可。因此本目录作为用户要求的本地研究副本保存；不代表取得公开传播、再发布或商业使用许可。对外发布前应另行核实网站录入文本及相关版本的权利状态并遵守适用条件。

## 中文译稿状态

中文翻译须与原文逐段对照，并保留篇、章、段号、日期、编者说明、校勘标记和来源引证。鉴于网页收录文本总量约 25.5 万词，翻译分批推进。各译稿以篇号命名，文件首部明确已译篇目与未译范围。译文由 OpenAI Codex 及并行代理分批生成、整理，属于机器辅助工作译稿；尚未经具名古典法学译者终审，不能视为定本。只有实际完成并按卷首说明对照检查的篇章才会标为已译。

## 文件说明

- `source_original/`：来源网页原始字节。
- `source_manifest.json`：来源、编码、哈希及链接范围清单。
- `web/`：离线网页副本与本地导航。
- `translations/`：分批中文对照译稿。
- `complete_download_and_manifest.py`、`prepare_local_edition.py`、`finalize_provenance.py`、`build_epub.py`、`verify_sources.py`：下载清点、离线归档、EPUB 构建与完整性核验脚本。
''',encoding='utf-8')
print(json.dumps(m['scope_inventory'],ensure_ascii=False))
print('records',len(records),'missing links',len(m.get('failed_pages',[])))

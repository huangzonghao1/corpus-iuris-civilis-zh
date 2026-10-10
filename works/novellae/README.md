# Iustiniani Novellae — 来源归档、中文对读译稿与 EPUB

## 文献与版本

本地整理以 [目录页](https://droitromain.univ-grenoble-alpes.fr/Corpus/Novellae.htm) 实际链接和页面内容为准。目录将新律文本列在 *Corpus Iuris Civilis*, vol. III，署名 Rudolfus Schoell，并说明其身后由 Guilelmus Kroll 完成。各正文页的底本说明、版本信息、网页录入者及录入说明各有不同，须逐页分别读取；例如部分页面说明文本由 Dr. Ingo Maier 提交。网页录入者不等同于底本编者。

另外收录 *Iustiniani XIII Edicta*、*Appendix constitutionum dispersarum* 和 *Iuliani Epitome Latina Novellarum Iustiniani*。摘要页面自述依据 Hänel 1873 年版，并称尤利安将新律由希腊文译为拉丁文。具体署名和页面说明保留于来源 HTML、离线网页及 EPUB 原文页。

## 下载和实际收录范围

下载日期为 2026-09-27（Asia/Shanghai）。本地保存目录页及 186 个目录所链接页面，链接请求均成功；另有未链接编号和有链接但无正文的页面，清单见 `source_manifest.json`。

- **《查士丁尼新律》**：保存并翻译 165 个链接篇目：I–CXXXV、CXXXVIII–CLXII、CLXIV–CLXVIII。目录未链接 CXXXVI、CXXXVII、CLXIII，未按编号补写。
- **《查士丁尼十三篇敕令》**：保存目录所链接的 I–VI、VIII、X–XII。II–IV、VIII、X–XII 有正文并已译；I、V、VI 页面正文位置标作 “Unknown text.”，保留原页但无正文可译。VII、IX、XIII 未见目录链接。
- **《散见宪令附录》**：保存并翻译 I–IX。
- **《尤利安新律拉丁摘要》**：保存两页并翻译 constitutiones 1–124。第一卷可见 kp.1–306；第二卷可见 kp.307–530 及 kp.532–564。来源页没有 kp.531，不作补造。

正文页实际呈现以拉丁文为主。“Translated from the Greek”表示网页所收为由希腊文译出的拉丁文本，不表示该页同时提供希腊原文。新律 135、142、148、153 页含有希腊文片段，已予保留。更细的逐页语种、编码和来源信息见 manifest。

## 中文译稿原则与状态

`translations/` 中的 Markdown 是可编辑的中拉对读工作稿。对照版内原文和中文按段相邻排列，并尽量保留标题、序言、章段号、结语、日期、引证、交叉引用和编者标记；完整来源页另收于拉丁文版及项目目录，不在对照版重复编排。网页未载或缺失的内容不据篇号补造。法律术语见 `translations/术语表_工作版.md`。疑难处保留原文并以“译者注”说明。

本次已对照检查各卷的篇目范围、段落配对及显著结构信息。中文为机器辅助形成的工作译稿，尚未经古典法学译者逐词复核或专业终审；它不应被引用为权威定本。对外学术引用请回查原文页及底本版本。

## 文件

- `Novellae_Schoell_Kroll_Latin.epub`：拉丁文原本版，收录目录页及 186 个链接正文页；保留原站拉丁文本、希腊文片段、编辑标记和原页链接。含拉丁文 EPUB 导航目录，可定位作品、篇、章及来源页的命名锚点。
- `Novellae_Schoell_Kroll_Chinese.epub`：中文译本，按段保留译文、必要的原文标题／法律术语、篇章编号、来源说明和译者注；移除了逐段拉丁原文。含覆盖全部译稿标题层级的中文导航目录及术语表。
- `Novellae_Schoell_Kroll_Chinese_Bilingual.epub`：中拉对照版，只收逐段相邻排列的拉丁原文与中文译文，不再重复嵌入一整套独立拉丁文来源页。导航目录覆盖全部译稿标题层级；完整原文页和逐锚点拉丁目录见独立拉丁文版。
- `translations_chinese_only/`：由 `translations/` 对读稿按原文／译文标签分离生成的可编辑中文 Markdown；共移除 1,933 个拉丁原文块，全部与后续中文译文标签配对。
- `source_original/`：下载所得 HTML 原始字节；不以清洗后的页面覆盖。
- `source_manifest.json`：来源 URL、文件名、HTTP 状态、编码声明与检测、字节长度、SHA-256、范围及页面说明。
- `web/`：离线浏览版页面和内部导航；原始 HTML 的字节副本另保存在 `source_original/`。
- `translations/`：可编辑的中文译稿和术语表。
- `build_epub.py`、`build_three_editions.py`、`verify_sources.py`、`quality_check_epub.py`：三版 EPUB 构建、来源完整性核验及结构／导航／字符抽检脚本。
- `source_integrity_report.json`、`epub_validation.json`、`three_editions_validation.json`：原始来源、双语版及三版 EPUB 的检查结果。

## 编码、校验与权利

每份下载页保留原始字节，并在 `source_manifest.json` 登记 SHA-256。页面编码以实际字节、HTML 声明及目录响应头分别记录；不少页面仅含 ASCII 字节但声明 ISO-8859-1，含希腊字符的部分页面使用 UTF-8。EPUB 另行以 UTF-8 编码输出。

站点元数据将版权归于 Alexandr Koptev。本次未查到明确的再利用许可；保存与翻译为本地研究整理，不表示取得公开传播或商业使用许可。发布或分发前应核实网站录入文本及底本的权利条件，并遵守适用署名要求。

## 核验记录

`three_editions_validation.json` 分别记录三版 EPUB 的 ZIP 与 XML 检查、首项未压缩的 `mimetype`、内部链接、EPUB 导航语言、目录目标覆盖数和文件大小。拉丁目录覆盖 2,967 个来源锚点；中文目录和对照版目录均覆盖 2,320 个译稿标题。三版均通过 Calibre 7.22.0 转换为 AZW3；转换仅作导入与解析核验。`epub_validation.json` 记录对照版抽检页面、字符及中拉相邻段落情况，并确认其中未嵌入独立来源页。`source_integrity_report.json` 记录原始文件哈希、离线镜像和拉丁版原文文本对照结果。系统当前未提供 `epubcheck` 命令。

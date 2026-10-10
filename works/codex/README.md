# Codex Iustinianus — 学术 EPUB 工作目录

来源索引：<https://droitromain.univ-grenoble-alpes.fr/Corpus/codjust.htm>

## 来源与范围

索引页、三篇前置文本和 Libri I–XII 共 16 个核心页面已抓取；另存三篇由前言图标链接的法文辅助参照页及三项图片资源，仅用于离线网页导航，不纳入中文译本正文。`source_original/` 逐字节保留服务器响应；`source_manifest.json` 记录 URL、SHA-256、字符编码和页面标题。网页 HTTP 声明与 HTML 内部 `meta` 编码标签有冲突，原始文件未改，依据文件内 ISO-8859-1 声明解码，并在 manifest 中记录冲突。

`web/` 是可离线浏览副本。三处失效旧目录链接映射、图片与法译链接修复、遗留 Word 元数据处理及法文参照页统计脚本移除情况见 `source_link_audit.csv`；原始页面不作修订。

## 当前产物与翻译进度

当前提供四种阅读本：

- `Codex_Iustinianus_Krueger_Latin_source.epub`：原网页来源阅读本，保留网页英文索引与希腊文缺载提示。
- `Codex_Iustinianus_Krueger_Latin.epub`：拉丁文单语阅读本。为保持语言纯一，略去英文网页索引简介，并将网页英文希腊文缺载提示译为拉丁文；书首说明该提示属于后加的编辑性译文。原始网页文件仍保存在 `source_original/`。
- `Codex_Iustinianus_Krueger_Chinese.epub`：中文单语译本，删除连续拉丁法条原文，保留中文译文、卷题法条编号、必要拉丁术语及译者校记。缺文和原网页说明用中文呈现。
- `Codex_Iustinianus_Krueger_bilingual.epub`：拉丁文—中文逐条对照版。

四版均保留可导航的卷、题与法条层级。`translation_status.csv` 记录 4,683 个翻译单元的进度。

`build_corpus.py` 重建离线副本与台账；`build_latin_epub.py --latin-only --output Codex_Iustinianus_Krueger_Latin.epub` 重建拉丁文单语本；`build_bilingual_epub.py --chinese-only --output Codex_Iustinianus_Krueger_Chinese.epub` 重建中文单语本；不加单语选项时，`build_bilingual_epub.py` 仍生成双语版。

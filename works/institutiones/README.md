# Iustiniani Institutiones

此目录保存网页所载查士丁尼《法学阶梯》本地文本版、EPUB 3 电子书及原始网页文件。

## 文件

- `Justinian_Institutes_Krueger.epub`：EPUB 3 电子书。
- `web/index.html`：离线入口；其余 HTML 与 `styles.css` 构成完整离线网页本。
- `source_original/`：按网页原编码保存的首页、序文、四卷正文和标题索引。
- `source_manifest.json`：来源、编码、字节数和 SHA-256。

## 编排说明

收录 Prooemium、Liber I–IV 与 Index titulorum。保留罗马数字标题、原有段落号、希腊文、斜体／粗体及方括号内译文；标题索引及 EPUB 目录可跳转到各标题。原网页中未设段落锚点的正文、引文和译文均按原顺序保留。

网页标示正文据 Paulus Krueger 的《Corpus Iuris Civilis》第一卷文本，并注明 Dr. Philippe Paschel 校对。此为网页文本转制本，未对 Krueger 纸本逐页校勘；不含现代译文或新增评注。

## 来源

首页：https://droitromain.univ-grenoble-alpes.fr/Corpus/iust_institut.html

序文与四卷、索引链接列于 `source_manifest.json`。保存日期：2026-09-26。

## 发布版构建入口

`edition/` 为既有EPUB导出的可编辑编排源，包含正文XHTML、导航、CSS与包元数据。`build_epub.py` 从这些文件重新封装EPUB，不读取已完成的EPUB；原始网页字节与编排源分别保存。通过仓库根目录的 `scripts/build.py --work institutiones` 可在独立目录中重建并核对内容。

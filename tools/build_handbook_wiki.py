#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a static wiki for projects/docs-and-handbooks only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
import argparse
import json
import os
import re
import shutil
import ssl
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = ROOT / "projects/docs-and-handbooks"
SITE_DIR = ROOT / "docs-site"
CONTENT_DIR = SITE_DIR / "content"
ASSETS_DIR = SITE_DIR / "assets"
DATA_DIR = SITE_DIR / "data"

EXCLUDED_PARTS = {".git", ".github", ".idea", "__pycache__"}
SOURCE_ONLY_FILES = {
    Path("awesome_handbook.zip"),
    Path("learning_guide.zip"),
}

EXTERNAL_REPLACEMENTS = {
    "https://wiki.openwrt.org/zh-cn/doc/howto/buildroot.exigence": "https://openwrt.org/docs/guide-developer/toolchain/install-buildsystem",
    "https://wiki.openwrt.org/doc/howto/build": "https://openwrt.org/docs/guide-developer/toolchain/use-buildsystem",
    "http://catalog.mit.edu/degree-charts/computer-science-engineering-course-6-3/": "https://catalog.mit.edu/degree-charts/computer-science-engineering-course-6-3/",
    "http://csrankings.org/#/index?arch&comm&sec&mod&hpc&mobile&metrics&ops&plan&soft&da&bed&world": "https://csrankings.org/#/index?arch&comm&sec&mod&hpc&mobile&metrics&ops&plan&soft&da&bed&world",
    "https://mermain.js.org/": "https://mermaid.js.org/",
    "http://gitbook.hushuang.me/setup.html": "https://michaelcollins.xyz/gitbook-legacy-documentation/en/setup.html",
    "http://henrysbench.capnfatz.com/henrys-bench/arduino-sensors-and-input/arduino-hc-sr501-motion-sensor-tutorial/": "https://lastminuteengineers.com/pir-sensor-arduino-tutorial/",
    "http://www.arduino.cn/thread-2851-1-1.html": "https://lastminuteengineers.com/pir-sensor-arduino-tutorial/",
    "https://blog.csdn.net/qq_16714013/article/details/108638034": "https://code.visualstudio.com/docs/sourcecontrol/overview",
    "https://conanhujinming.github.io/post/tips_for_interview/": "https://github.com/conanhujinming/tips_for_interview/blob/master/README-zh_CN.md",
    "https://github.com/openwrt/openwrt/archive/v15.05.tar.gz": "https://archive.openwrt.org/chaos_calmer/15.05.1/",
    "https://github.com/openwrt/openwrt/archive/v15.05.zip": "https://archive.openwrt.org/chaos_calmer/15.05.1/",
    "https://phabricator.wikimedia.org/source/mediawiki/browse/master/includes/DefaultSettings.php": "https://www.mediawiki.org/wiki/Manual:DefaultSettings.php",
    "https://stellar.mit.edu/classlink/course6.html": "https://ocw.mit.edu/search/?d=Electrical%20Engineering%20and%20Computer%20Science",
    "https://ysyx.org/": "https://ysyx.oscc.cc/project/intro.html",
    "http://oqyjccf1n.bkt.clouddn.com/20180408-100752.png": "REMOVE:missing-image",
    "http://oqyjccf1n.bkt.clouddn.com/20180408-101436.png": "REMOVE:missing-image",
    "http://oqyjccf1n.bkt.clouddn.com/20180408-102205.png": "REMOVE:missing-image",
    "http://oqyjccf1n.bkt.clouddn.com/20180408-110132.png": "REMOVE:missing-image",
    "http://oqyjccf1n.bkt.clouddn.com/20180408-110156.png": "REMOVE:missing-image",
    "http://rolandorange.zone/": "REMOVE:unavailable-page",
    "https://blog.icyfeather.cf/2020/11/07/%e4%b9%b0%e4%ba%86%e4%b8%80%e5%8f%b0%e6%9c%8d%e5%8a%a1%e5%99%a8%e4%b9%8b%e5%90%8e%e7%9a%84%e5%9f%ba%e6%93%8d/": "REMOVE:unavailable-page",
    "https://github.com/IcyFeather233/FakeNewsGenerator": "REMOVE:unavailable-page",
    "https://www.zhihu.com/people/yuck-77/answers/by_votes": "REMOVE:restricted-profile",
}

INTERNAL_HOSTS = {
    "scumaker.org",
    "wiki.scumaker.org",
    "gogs.scumaker.org",
    "gitlab.scumaker.org",
    "pages.scumaker.org",
    "share.syaoran.scumaker.org",
}

VIRTUAL_ALIASES: dict[Path, dict[str, str]] = {}


@dataclass(frozen=True)
class Collection:
    root: Path
    section: str
    title: str
    order: int


@dataclass
class Page:
    path: Path
    title: str
    section: str
    collection: str
    source: Path | None
    excerpt: str
    headings: list[str]
    lines: int
    bytes: int
    order: tuple[int, int, int, str]
    generated: bool = False
    empty: bool = False


@dataclass
class Resource:
    source: Path
    path: Path
    title: str
    category: str
    ext: str
    size: int
    publish: bool
    note: str


def collections() -> list[Collection]:
    return [
        Collection(DOCS_ROOT / "awesome_handbook", "协会知识库", "协会介绍与技术教程", 10),
        Collection(DOCS_ROOT / "learning_guide", "协会知识库", "新人学习路线", 20),
        Collection(DOCS_ROOT / "books", "协会知识库", "图书资料", 30),
        Collection(DOCS_ROOT / "survive_scu_manual", "历史参考", "SCU 自学手册归档", 90),

    ]


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def strip_front_matter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index in range(1, min(len(lines), 80)):
        if lines[index].strip() == "---":
            return "\n".join(lines[index + 1:]).lstrip("\n")
    return text


def front_matter_title(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:80]:
        stripped = line.strip()
        if stripped == "---":
            break
        match = re.match(r"title:\s*[\"']?(.+?)[\"']?\s*$", stripped)
        if match:
            return clean_inline(match.group(1))
    return ""


def clean_inline(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[`*_>#|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def title_from_path(path: Path) -> str:
    if path.name.lower() == "readme.md":
        return path.parent.name.replace("_", " ").replace("-", " ")
    return path.stem.replace("_", " ").replace("-", " ")


def summarize_markdown(path: Path | None, text: str, fallback_title: str = "") -> tuple[str, str, list[str], int, bool]:
    body = strip_front_matter(text)
    lines = body.splitlines()
    title = fallback_title or front_matter_title(text)
    excerpt = ""
    headings: list[str] = []
    in_code = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code = not in_code
            continue
        if in_code:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            heading_text = clean_inline(heading.group(2))
            if heading_text:
                headings.append(heading_text)
                if not title:
                    title = heading_text
            continue
        if not excerpt and stripped and not stripped.startswith(("-", "*", "|", ">", "#")):
            cleaned = clean_inline(stripped)
            if cleaned:
                excerpt = cleaned

    if not title and path is not None:
        title = title_from_path(path)
    if not excerpt and headings:
        excerpt = " / ".join(headings[:3])
    if len(excerpt) > 180:
        excerpt = excerpt[:177] + "..."
    return title or "未命名页面", excerpt, headings[:12], len(lines), len(body.strip()) == 0


def load_summary_order(root: Path) -> tuple[dict[Path, int], dict[Path, str]]:
    summary = root / "SUMMARY.md"
    order: dict[Path, int] = {}
    titles: dict[Path, str] = {}
    if not summary.exists():
        return order, titles

    text = read_text(summary)
    for index, match in enumerate(re.finditer(r"\[([^\]]+)\]\(([^)]*)\)", text)):
        label = clean_inline(match.group(1))
        target = match.group(2).strip()
        if not target or is_external_url(target):
            continue
        target = unquote(target.split("#", 1)[0])
        if not target:
            continue
        resolved = (root / target).resolve()
        order[resolved] = index
        titles[resolved] = label
    return order, titles


def iter_markdown_files() -> list[Path]:
    files = []
    for path in DOCS_ROOT.rglob("*.md"):
        rel = path.relative_to(DOCS_ROOT)
        if is_excluded(rel):
            continue
        if path.name.lower() == "summary.md":
            continue
        files.append(path)
    return files


def natural_path_key(path: Path) -> str:
    """Return a stable path key where numbered chapters sort numerically."""
    return re.sub(r"\d+", lambda match: f"{int(match.group()):08d}", path.as_posix().casefold())


def collection_for(path: Path) -> Collection:
    for item in collections():
        try:
            path.relative_to(item.root)
            return item
        except ValueError:
            continue
    return Collection(DOCS_ROOT, "其他资料", "未分类", 999)


def collect_pages() -> tuple[list[Page], dict[Path, Path]]:
    summary_orders: dict[Path, dict[Path, int]] = {}
    summary_titles: dict[Path, dict[Path, str]] = {}
    for item in collections():
        order, titles = load_summary_order(item.root)
        summary_orders[item.root] = order
        summary_titles[item.root] = titles

    pages: list[Page] = []
    source_to_dest: dict[Path, Path] = {}
    for source in iter_markdown_files():
        rel = source.relative_to(DOCS_ROOT)
        item = collection_for(source)
        resolved = source.resolve()
        fallback = summary_titles.get(item.root, {}).get(resolved, "")
        text = read_text(source)
        title, excerpt, headings, lines, empty = summarize_markdown(source, text, fallback)
        order_index = summary_orders.get(item.root, {}).get(resolved, 9999)
        if empty:
            continue
        page = Page(
            path=rel,
            title=title,
            section=item.section,
            collection=item.title,
            source=source,
            excerpt=excerpt,
            headings=headings,
            lines=lines,
            bytes=source.stat().st_size,
            order=(item.order, order_index, len(rel.parts), natural_path_key(rel)),
            empty=empty,
        )
        pages.append(page)
        source_to_dest[source.resolve()] = rel

    for rel, spec in VIRTUAL_ALIASES.items():
        body = f"# {spec['title']}\n\n{spec['body']}"
        item = collection_for(DOCS_ROOT / rel)
        title, excerpt, headings, lines, empty = summarize_markdown(None, body, spec["title"])
        pages.append(
            Page(
                path=rel,
                title=title,
                section=item.section,
                collection=item.title,
                source=None,
                excerpt=excerpt,
                headings=headings,
                lines=lines,
                bytes=len(body.encode("utf-8")),
                order=(item.order, 9000, len(rel.parts), rel.as_posix()),
                generated=True,
                empty=empty,
            )
        )

    pages.sort(key=lambda page: page.order)
    return pages, source_to_dest


def classify_resource(rel: Path) -> tuple[str, str]:
    text = rel.as_posix()
    ext = rel.suffix.lower()
    if rel in SOURCE_ONLY_FILES:
        return "原始备份包", "已解包到同名目录，静态站不重复发布这个大压缩包。"
    if "tools_attatchment/1.devices" in text:
        return "设备与仪器手册", "设备说明书、用户手册或安装指南。"
    if "tools_attatchment/2.hardware_tools" in text:
        return "硬件工具资料", "焊接、万用表、逻辑分析仪、串口模块等工具资料。"
    if "tools_attatchment/4.software_tools" in text:
        return "软件工具包", "历史软件工具、安装包或使用说明。"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return "站内插图与图片素材", "Markdown 页面引用的图片或保留素材。"
    if ext in {".zip", ".rar", ".gz", ".dmg"}:
        return "压缩包与镜像", "压缩包、磁盘镜像或安装素材。"
    if ext in {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx"}:
        return "文档附件", "PDF、Office 文档或演示资料。"
    return "其他资源", "保留的非 Markdown 资源。"


def collect_resources() -> list[Resource]:
    resources: list[Resource] = []
    for source in DOCS_ROOT.rglob("*"):
        if not source.is_file():
            continue
        rel = source.relative_to(DOCS_ROOT)
        if is_excluded(rel) or rel.suffix.lower() == ".md":
            continue
        if rel.name in {".gitignore", ".nojekyll"}:
            continue
        category, note = classify_resource(rel)
        publish = rel not in SOURCE_ONLY_FILES
        resources.append(
            Resource(
                source=source,
                path=rel,
                title=resource_title(rel),
                category=category,
                ext=rel.suffix.lower() or "无扩展名",
                size=source.stat().st_size,
                publish=publish,
                note=note,
            )
        )
    resources.sort(key=lambda item: (item.category, item.path.as_posix()))
    return resources


def resource_title(path: Path) -> str:
    title = path.stem.replace("_", " ").replace("-", " ")
    title = re.sub(r"\s+", " ", title).strip()
    return title or path.name


def reset_output() -> None:
    SITE_DIR.mkdir(exist_ok=True)
    if CONTENT_DIR.exists():
        shutil.rmtree(CONTENT_DIR)
    if ASSETS_DIR.exists():
        shutil.rmtree(ASSETS_DIR)
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    CONTENT_DIR.mkdir(parents=True)
    ASSETS_DIR.mkdir(parents=True)
    DATA_DIR.mkdir(parents=True)


def is_external_url(target: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target)) or target.startswith("//")


def split_target(target: str) -> tuple[str, str]:
    if "#" in target:
        base, rest = target.split("#", 1)
        return base, "#" + rest
    return target, ""


def normalize_external_url(url: str) -> tuple[str, str | None]:
    url = url.strip()
    if url.startswith("extension://") and "file=" in url:
        parsed = urlparse(url)
        file_values = parse_qs(parsed.query).get("file")
        if file_values:
            return unquote(file_values[0]), "浏览器插件链接已替换为直接 PDF URL"
    if url in EXTERNAL_REPLACEMENTS:
        replacement = EXTERNAL_REPLACEMENTS[url]
        action = "移除失效链接" if replacement.startswith("REMOVE:") else "替换旧链接"
        return replacement, f"{action}：{url}"
    return url, None


def resolve_collection_root(source: Path) -> Path:
    return collection_for(source).root


def candidate_paths(source: Path, raw_target: str) -> list[Path]:
    base, _ = split_target(raw_target)
    target = unquote(base.strip())
    if not target:
        return []
    collection_root = resolve_collection_root(source)
    candidates = []
    if target.startswith("/"):
        stripped = target.lstrip("/")
        candidates.append(collection_root / stripped)
        candidates.append(DOCS_ROOT / stripped)
        if source.relative_to(DOCS_ROOT).parts[0] == "awesome_handbook":
            candidates.append(DOCS_ROOT / "awesome_handbook" / stripped)
    else:
        candidates.append(source.parent / target)
        candidates.append(collection_root / target)
        candidates.append(DOCS_ROOT / target)

    expanded: list[Path] = []
    for candidate in candidates:
        expanded.append(candidate)
        if candidate.suffix == "":
            expanded.append(candidate.with_suffix(".md"))
            expanded.append(candidate / "README.md")
    return expanded


def resolve_local_target(source: Path, target: str, source_to_dest: dict[Path, Path]) -> Path | None:
    for candidate in candidate_paths(source, target):
        resolved = candidate.resolve()
        if resolved in source_to_dest:
            return source_to_dest[resolved]
        try:
            rel = resolved.relative_to(DOCS_ROOT.resolve())
        except ValueError:
            continue
        if rel in VIRTUAL_ALIASES:
            return rel
        if candidate.exists() and candidate.is_file():
            return rel
    return None


def relative_link(from_path: Path, to_path: Path, suffix: str = "") -> str:
    relative = os.path.relpath(to_path.as_posix(), start=from_path.parent.as_posix()).replace("\\", "/")
    return relative.replace("(", "%28").replace(")", "%29") + suffix


def extract_external_urls(text: str) -> set[str]:
    urls: set[str] = set()
    for match in re.finditer(r"\]\(([^()\n]*(?:\([^()\n]*\)[^()\n]*)*)\)", text):
        target = match.group(1).strip()
        if is_external_url(target):
            normalized, _ = normalize_external_url(target)
            if normalized.startswith(("http://", "https://")):
                urls.add(normalized)
    for match in re.finditer(r"(?<![\]\(])https?://[^\s<>)`]+", text):
        raw = match.group(0).rstrip("，。；,.;'\"")
        if "[" in raw or "]" in raw:
            continue
        normalized, _ = normalize_external_url(raw)
        urls.add(normalized)
    return urls


def transform_links(
    source: Path,
    dest: Path,
    text: str,
    source_to_dest: dict[Path, Path],
    local_issues: list[dict[str, str]],
    replacements: list[dict[str, str]],
) -> str:
    link_pattern = re.compile(r"(!?\[[^\]]*\]\()([^()\n]*(?:\([^()\n]*\)[^()\n]*)*)(\))")

    def plain_label(prefix: str) -> str:
        match = re.match(r"!?\[([^\]]*)\]\(", prefix)
        return match.group(1) if match else ""

    def replace(match: re.Match[str]) -> str:
        prefix, target, closing = match.groups()
        target = target.strip()
        if not target:
            local_issues.append({"source": str(source.relative_to(ROOT)), "target": target, "reason": "空链接"})
            return plain_label(prefix)
        base, suffix = split_target(target)
        if not base and suffix:
            return match.group(0)

        if is_external_url(base):
            normalized, note = normalize_external_url(base)
            if note:
                replacements.append({"source": str(source.relative_to(ROOT)), "old": base, "new": normalized, "note": note})
            if normalized.startswith("REMOVE:"):
                return plain_label(prefix)
            return prefix + normalized + suffix + closing

        resolved = resolve_local_target(source, target, source_to_dest)
        if resolved is None:
            if base == "/url/to/file":
                return plain_label(prefix)
            local_issues.append({"source": str(source.relative_to(ROOT)), "target": target, "reason": "本地目标不存在"})
            return plain_label(prefix)

        return prefix + relative_link(dest, resolved, suffix) + closing

    transformed = link_pattern.sub(replace, text)
    for old, new in EXTERNAL_REPLACEMENTS.items():
        if new.startswith("REMOVE:"):
            continue
        transformed = transformed.replace(old, new)
    return transformed


def copy_resources(resources: list[Resource]) -> None:
    for resource in resources:
        if not resource.publish:
            continue
        target = CONTENT_DIR / resource.path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resource.source, target)


def write_source_pages(
    pages: list[Page],
    source_to_dest: dict[Path, Path],
) -> tuple[list[dict[str, str]], list[dict[str, str]], set[str]]:
    local_issues: list[dict[str, str]] = []
    replacements: list[dict[str, str]] = []
    external_urls: set[str] = set()

    for page in pages:
        output = CONTENT_DIR / page.path
        output.parent.mkdir(parents=True, exist_ok=True)
        if page.source is None:
            continue
        text = strip_front_matter(read_text(page.source))
        transformed = transform_links(page.source, page.path, text, source_to_dest, local_issues, replacements)
        external_urls.update(extract_external_urls(transformed))
        output.write_text(transformed, encoding="utf-8")

    return local_issues, replacements, external_urls


def size_text(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MiB"
    if size >= 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size} B"


def category_slug(category: str) -> str:
    mapping = {
        "设备与仪器手册": "device-manuals",
        "硬件工具资料": "hardware-tools",
        "软件工具包": "software-tools",
        "站内插图与图片素材": "images",
        "压缩包与镜像": "archives",
        "文档附件": "documents",
        "原始备份包": "source-archives",
        "其他资源": "others",
    }
    return mapping.get(category, "others")


def resource_category_order(category: str) -> tuple[int, str]:
    order = {
        "设备与仪器手册": 10,
        "硬件工具资料": 20,
        "软件工具包": 30,
        "文档附件": 40,
        "站内插图与图片素材": 50,
        "压缩包与镜像": 60,
        "原始备份包": 90,
        "其他资源": 99,
    }
    return order.get(category, 80), category


def resource_table(resources: list[Resource], current_page: Path) -> str:
    lines = ["| 资源 | 格式 | 大小 |", "| --- | --- | ---: |"]
    for item in resources:
        if item.publish:
            link = relative_link(current_page, item.path)
            name = f"[{item.title}]({link})"
        else:
            name = item.title
        lines.append(f"| {name} | `{item.ext}` | {size_text(item.size)} |")
    return "\n".join(lines)


def generate_resource_pages(resources: list[Resource]) -> dict[Path, str]:
    by_category: dict[str, list[Resource]] = {}
    for item in resources:
        by_category.setdefault(item.category, []).append(item)

    pages: dict[Path, str] = {}
    overview_lines = [
        "# 资源总库",
        "",
        "这里把 `projects/docs-and-handbooks` 中散落的 PDF、PPT、DOCX、安装包、配置模板和图片素材统一归类。Markdown 正文仍保留原有内容；资源总库负责补上“文件在哪里、怎么打开”的入口。",
        "",
        "| 分类 | 数量 | 说明 |",
        "| --- | ---: | --- |",
    ]
    for category, items in sorted(by_category.items(), key=lambda item: resource_category_order(item[0])):
        slug = category_slug(category)
        page = Path(f"00-wiki/resources/{slug}.md")
        overview_lines.append(f"| [{category}](resources/{slug}.md) | {len(items)} | {items[0].note} |")
        warning = "\n> 这些文件来自历史资料归档。运行安装包或可执行文件前，请自行核验来源和安全性。\n" if category == "软件工具包" else ""
        pages[page] = f"# {category}\n\n{items[0].note}\n{warning}\n{resource_table(items, page)}\n"

    pages[Path("00-wiki/resources.md")] = "\n".join(overview_lines) + "\n"
    return pages


def generate_home(pages: list[Page], resources: list[Resource], link_audit: list[dict[str, str]]) -> str:
    checked = len([item for item in link_audit if item.get("checked") == "yes"])
    broken = len([item for item in link_audit if item.get("status") == "broken"])
    source_pages = len([page for page in pages if page.source is not None and not page.empty])
    published_resources = len([item for item in resources if item.publish])

    return f"""# SCU Maker 文档资料 Wiki

这里整理 SCU Maker 协会的介绍、学习路线、技术教程、藏书和资料附件。当前收录 **{source_pages} 篇文档**、**{published_resources} 个资源**；`SCU 自学手册` 作为历史参考单独归档。

## 从这里开始

- [协会介绍](../awesome_handbook/协会整体介绍.md)
- [新人学习指南](../learning_guide/README.md)
- [自学与搜索方法](../learning_guide/introduction/README.md)
- [编程语言入门](../learning_guide/language/README.md)
- [Linux 与服务器入门](../learning_guide/server/README.md)

## 协会与技术

- [2020 协会招新公告](../awesome_handbook/2020协会招新公告.md)
- [树莓派 HC-SR501 红外探测教程](../awesome_handbook/software/树莓派的应用之HC-SR501模块.md)
- [OpenWrt 交叉编译教程](../awesome_handbook/software/openwrt交叉编译教程.md)
- [协会 Wiki 维护方法](../awesome_handbook/tools/wiki教程.md)

## 资料与归档

- [协会藏书清单](../books/README.md)
- [资源总库](resources.md)
- [SCU 自学手册归档](../survive_scu_manual/README.md)

## 站点维护

- [站点地图](wiki-map.md)
- [外部链接检测报告](external-links.md)
- [本地链接报告](missing-links.md)

> 链接记录 {len(link_audit)} 条，已联网检测 {checked} 条，确认不可用并取消跳转 {broken} 条。历史安装包和附件仅供资料留存，使用前请核验来源与安全性。
"""


def generate_wiki_map(pages: list[Page]) -> str:
    lines = ["# 站点地图", "", "按主题组织的 Wiki 入口。", ""]
    current_section = ""
    current_collection = ""
    for page in pages:
        if page.empty or page.path.as_posix().startswith("00-wiki/"):
            continue
        if page.section != current_section:
            current_section = page.section
            current_collection = ""
            lines.extend(["", f"## {current_section}", ""])
        if page.collection != current_collection:
            current_collection = page.collection
            lines.extend([f"### {current_collection}", ""])
        link = relative_link(Path("00-wiki/wiki-map.md"), page.path)
        lines.append(f"- [{page.title}]({link})")
    lines.append("")
    return "\n".join(lines)


def generate_missing_links(local_issues: list[dict[str, str]], replacements: list[dict[str, str]]) -> str:
    lines = [
        "# 本地链接报告",
        "",
        "构建时会重写可解析的本地 Markdown、图片和附件链接。下列问题需要人工判断或原资料缺失。",
        "",
        "## 已自动修正的链接",
        "",
    ]
    if replacements:
        lines.extend(["| 来源 | 原链接 | 新链接 | 说明 |", "| --- | --- | --- | --- |"])
        for item in replacements:
            new_link = item["new"]
            if new_link.startswith("REMOVE:"):
                new_link = "已取消跳转"
            else:
                new_link = f"`{new_link}`"
            lines.append(f"| `{item['source']}` | `{item['old']}` | {new_link} | {item['note']} |")
    else:
        lines.append("- 无")

    lines.extend(["", "## 未解析本地链接", ""])
    if local_issues:
        lines.extend(["| 来源 | 目标 | 原因 |", "| --- | --- | --- |"])
        for item in local_issues:
            lines.append(f"| `{item['source']}` | `{item['target']}` | {item['reason']} |")
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def is_internal_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if host in INTERNAL_HOSTS:
        return True
    if host in {"127.0.0.1", "localhost", "::1"}:
        return True
    if host.startswith("192.168.") or host.startswith("10.") or host.startswith("172.16."):
        return True
    return False


def check_external_urls(urls: set[str]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    context = ssl.create_default_context()
    headers = {"User-Agent": "SCUMakerWikiLinkCheck/1.0"}
    for url in sorted(urls):
        if is_internal_url(url):
            results.append({"url": url, "status": "internal", "code": "", "checked": "no", "note": "内部或历史协会服务地址，未按公网坏链处理"})
            continue
        status = "broken"
        code = ""
        note = ""
        final_url = url
        for method in ("HEAD", "GET"):
            try:
                req = urllib.request.Request(url, method=method, headers=headers)
                with urllib.request.urlopen(req, timeout=12, context=context) as response:
                    code = str(response.status)
                    final_url = response.geturl()
                    status = "ok" if response.status < 400 else "broken"
                    note = "redirected" if final_url != url else ""
                    break
            except urllib.error.HTTPError as exc:
                code = str(exc.code)
                if method == "HEAD" and exc.code in {403, 405, 429}:
                    continue
                status = "restricted" if exc.code in {403, 429} else ("broken" if exc.code >= 400 else "ok")
                note = exc.reason or ""
                break
            except Exception as exc:  # noqa: BLE001
                note = type(exc).__name__
                if method == "GET":
                    status = "unverified"
                    break
        results.append({"url": url, "status": status, "code": code, "checked": "yes", "note": note, "finalUrl": final_url})
    return results


def remove_broken_external_links(
    pages: list[Page],
    link_audit: list[dict[str, str]],
    replacements: list[dict[str, str]],
) -> None:
    """Turn confirmed broken external links into text in generated Markdown."""
    broken = {item["url"] for item in link_audit if item.get("status") == "broken"}
    if not broken:
        return
    link_pattern = re.compile(r"(!?\[[^\]]*\]\()([^()\n]*(?:\([^()\n]*\)[^()\n]*)*)(\))")
    recorded = {(item["source"], item["old"]) for item in replacements}

    for page in pages:
        if page.source is None:
            continue
        output = CONTENT_DIR / page.path
        text = read_text(output)

        def replace(match: re.Match[str]) -> str:
            prefix, target, _ = match.groups()
            base, _ = split_target(target.strip())
            normalized, _ = normalize_external_url(base)
            if normalized not in broken:
                return match.group(0)
            label_match = re.match(r"!?\[([^\]]*)\]\(", prefix)
            label = label_match.group(1) if label_match else ""
            key = (str(page.source.relative_to(ROOT)), normalized)
            if key not in recorded:
                replacements.append(
                    {
                        "source": key[0],
                        "old": normalized,
                        "new": "REMOVE:external-check",
                        "note": "联网检测确认目标不可用，已取消跳转",
                    }
                )
                recorded.add(key)
            return label

        cleaned = link_pattern.sub(replace, text)
        if cleaned != text:
            output.write_text(cleaned, encoding="utf-8")


def generate_external_report(link_audit: list[dict[str, str]]) -> str:
    lines = [
        "# 外部链接检测报告",
        "",
        "构建时会把明显过期或错误格式的外链替换为较新的入口；联网检测结果如下。内部协会域名和私有地址不会按公网坏链处理。",
        "",
        "| 状态 | HTTP | 链接 | 说明 |",
        "| --- | ---: | --- | --- |",
    ]
    for item in link_audit:
        status = item.get("status", "")
        code = item.get("code", "")
        url = item.get("url", "")
        note = item.get("note", "")
        final_url = item.get("finalUrl")
        if final_url and final_url != url:
            note = (note + " " if note else "") + f"→ {final_url}"
        display = f"[打开]({url})" if status == "ok" else f"`{url}`"
        lines.append(f"| {status} | {code} | {display} | {note} |")
    lines.append("")
    return "\n".join(lines)


def add_generated_pages(
    pages: list[Page],
    resources: list[Resource],
    local_issues: list[dict[str, str]],
    replacements: list[dict[str, str]],
    link_audit: list[dict[str, str]],
) -> list[Page]:
    generated: dict[Path, str] = {
        Path("00-wiki/README.md"): "",
        Path("00-wiki/wiki-map.md"): generate_wiki_map(pages),
        Path("00-wiki/missing-links.md"): generate_missing_links(local_issues, replacements),
        Path("00-wiki/external-links.md"): generate_external_report(link_audit),
    }
    generated.update(generate_resource_pages(resources))
    generated[Path("00-wiki/README.md")] = generate_home(pages, resources, link_audit)

    for rel, spec in VIRTUAL_ALIASES.items():
        generated[rel] = f"# {spec['title']}\n\n{spec['body']}"

    generated_pages: list[Page] = []
    for rel, text in generated.items():
        output = CONTENT_DIR / rel
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        title, excerpt, headings, lines, empty = summarize_markdown(None, text)
        section = "站点总览" if rel.as_posix().startswith("00-wiki/") else collection_for(DOCS_ROOT / rel).section
        collection = "生成索引" if rel.as_posix().startswith("00-wiki/") else collection_for(DOCS_ROOT / rel).title
        generated_pages.append(
            Page(
                path=rel,
                title=title,
                section=section,
                collection=collection,
                source=None,
                excerpt=excerpt,
                headings=headings,
                lines=lines,
                bytes=len(text.encode("utf-8")),
                order=(-1, 0, len(rel.parts), rel.as_posix()) if rel.as_posix().startswith("00-wiki/") else (collection_for(DOCS_ROOT / rel).order, 9000, len(rel.parts), rel.as_posix()),
                generated=True,
                empty=empty,
            )
        )

    merged = [page for page in pages if not (page.generated and page.path in generated)] + generated_pages
    merged.sort(key=lambda page: page.order)
    return merged


def navigation_for(page: Page) -> tuple[str, str]:
    path = page.path.as_posix()
    parts = page.path.parts
    if path == "00-wiki/README.md":
        return "开始使用", "首页"
    if path.startswith("learning_guide/"):
        return "开始使用", "新人学习路线"
    if path.startswith("awesome_handbook/"):
        if "/software/" in f"/{path}":
            return "协会资料", "技术教程"
        if "/tools/" in f"/{path}":
            return "协会资料", "维护方法"
        return "协会资料", "协会介绍"
    if path.startswith("books/"):
        return "资源库", "图书资料"
    if path == "00-wiki/resources.md" or path.startswith("00-wiki/resources/"):
        return "资源库", "分类资源"
    if path.startswith("survive_scu_manual/"):
        chapter = parts[1] if len(parts) > 2 else ""
        labels = {
            "00-introduction": "手册说明",
            "1-save-self": "自我提升",
            "2-survive": "校园生存",
            "3-future": "升学规划",
            "4-experience-sharing": "经验分享",
        }
        return "历史手册", labels.get(chapter, "归档首页")
    return "站点维护", "索引与检查"


def manifest(pages: list[Page], resources: list[Resource], link_audit: list[dict[str, str]]) -> dict[str, object]:
    return {
        "title": "SCU Maker 文档资料 Wiki",
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "sourceRoot": str(DOCS_ROOT.relative_to(ROOT)),
        "stats": {
            "pages": len(pages),
            "sourceMarkdown": len([page for page in pages if page.source is not None]),
            "generatedPages": len([page for page in pages if page.generated]),
            "resources": len(resources),
            "publishedResources": len([item for item in resources if item.publish]),
            "externalLinks": len(link_audit),
            "brokenExternalLinks": len([item for item in link_audit if item.get("status") == "broken"]),
        },
        "pages": [
            {
                "path": page.path.as_posix(),
                "title": page.title,
                "section": page.section,
                "collection": page.collection,
                "excerpt": page.excerpt,
                "headings": page.headings,
                "source": str(page.source.relative_to(ROOT)) if page.source else "generated",
                "lines": page.lines,
                "bytes": page.bytes,
                "empty": page.empty,
                "generated": page.generated,
                "navGroup": navigation_for(page)[0],
                "navSubgroup": navigation_for(page)[1],
            }
            for page in pages
        ],
        "resources": [
            {
                "path": item.path.as_posix(),
                "title": item.title,
                "category": item.category,
                "extension": item.ext,
                "size": item.size,
                "publish": item.publish,
                "source": str(item.source.relative_to(ROOT)),
            }
            for item in resources
        ],
    }


def validate_site(pages: list[Page], resources: list[Resource]) -> None:
    """Fail the build when a published page, resource, or local link is empty or missing."""
    problems: list[str] = []
    link_pattern = re.compile(r"!?\[[^\]]*\]\(([^()\n]*(?:\([^()\n]*\)[^()\n]*)*)\)")

    for page in pages:
        output = CONTENT_DIR / page.path
        if page.empty or not output.is_file() or output.stat().st_size == 0:
            problems.append(f"空页面：{page.path.as_posix()}")
            continue
        text = read_text(output)
        for match in link_pattern.finditer(text):
            target = match.group(1).strip()
            base, _ = split_target(target)
            if not base or is_external_url(base):
                continue
            decoded = unquote(base)
            if decoded.startswith("/"):
                relative = Path(decoded.lstrip("/"))
            else:
                relative = Path(os.path.normpath((page.path.parent / decoded).as_posix()))
            if relative.parts and relative.parts[0] == "..":
                problems.append(f"越界链接：{page.path.as_posix()} -> {target}")
                continue
            linked = CONTENT_DIR / relative
            if not linked.is_file() or linked.stat().st_size == 0:
                problems.append(f"无内容链接：{page.path.as_posix()} -> {target}")

    for resource in resources:
        if not resource.publish:
            continue
        output = CONTENT_DIR / resource.path
        if not output.is_file() or output.stat().st_size == 0:
            problems.append(f"空资源：{resource.path.as_posix()}")

    for shell_file in (SITE_DIR / "index.html", ASSETS_DIR / "wiki.css", ASSETS_DIR / "wiki.js", SITE_DIR / "manifest.json"):
        if not shell_file.is_file() or shell_file.stat().st_size == 0:
            problems.append(f"缺少站点文件：{shell_file.relative_to(ROOT)}")

    if problems:
        details = "\n".join(f"- {problem}" for problem in problems[:30])
        raise RuntimeError(f"站点完整性检查失败：\n{details}")


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SCU Maker 文档资料 Wiki</title>
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%23173f38'/%3E%3Ctext x='32' y='40' text-anchor='middle' font-size='21' font-family='Arial' font-weight='700' fill='%23fff7df'%3ESCU%3C/text%3E%3C/svg%3E" />
    <link rel="stylesheet" href="assets/wiki.css" />
  </head>
  <body>
    <div class="layout">
      <aside id="sidebar" class="sidebar" aria-label="站点导航">
        <div class="sidebar-head">
          <a class="brand" href="#/00-wiki/README.md" aria-label="返回 Wiki 首页">
          <div class="brand-mark">SCU</div>
            <div class="brand-copy">
            <div class="brand-title">Maker 文档资料 Wiki</div>
            <div class="brand-meta" id="site-stats">加载中</div>
            </div>
          </a>
          <button id="close-menu" class="close-menu" type="button" aria-label="关闭目录">×</button>
        </div>
        <label class="sr-only" for="search">搜索 Wiki</label>
        <input id="search" class="search" type="search" placeholder="搜索标题和内容摘要" autocomplete="off" />
        <nav id="nav" class="nav"></nav>
        <div class="sidebar-foot"><a href="#/00-wiki/wiki-map.md">查看完整站点地图</a></div>
      </aside>
      <button id="backdrop" class="backdrop" type="button" aria-label="关闭目录"></button>
      <main class="main">
        <header class="topbar">
          <button id="menu" class="menu" type="button" aria-label="打开目录" aria-controls="sidebar" aria-expanded="false">☰</button>
          <nav class="crumbs" aria-label="面包屑">
            <a href="#/00-wiki/README.md">首页</a><span aria-hidden="true">/</span>
            <span id="crumb-group"></span><span aria-hidden="true">/</span>
            <span id="crumb-title"></span>
          </nav>
          <a id="raw" class="raw" target="_blank" rel="noreferrer" hidden>查看 Markdown</a>
        </header>
        <div class="content-shell">
          <article id="content" class="markdown" tabindex="-1"></article>
          <aside id="toc" class="toc" aria-label="本页目录" hidden></aside>
        </div>
        <footer class="pager">
          <a id="prev" hidden></a>
          <a id="next" hidden></a>
        </footer>
      </main>
    </div>
    <script src="assets/wiki.js"></script>
  </body>
</html>
"""


WIKI_CSS = """
:root {
  --bg: #f5f7f4;
  --panel: #ffffff;
  --sidebar: #f9faf7;
  --ink: #1d2924;
  --muted: #65716b;
  --line: #dce4df;
  --accent: #0b766b;
  --accent-strong: #07574f;
  --accent-soft: #dcefeb;
  --warn: #976018;
  --code: #17231f;
  --code-text: #e6f0eb;
  --shadow: 0 16px 44px rgba(29, 41, 36, 0.12);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", sans-serif;
  overflow-x: hidden;
}
a { color: var(--accent); text-underline-offset: 3px; }
button, input { font: inherit; }
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}
.layout { display: grid; grid-template-columns: 300px minmax(0, 1fr); min-height: 100vh; }
.sidebar {
  position: sticky; top: 0; z-index: 10; height: 100vh; overflow: auto;
  border-right: 1px solid var(--line);
  background: var(--sidebar);
  padding: 20px 14px 16px;
}
.sidebar-head { display: flex; align-items: center; gap: 8px; margin-bottom: 18px; }
.brand {
  min-width: 0; display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 11px; align-items: center;
  color: var(--ink); text-decoration: none;
}
.brand-copy { min-width: 0; }
.brand-mark {
  width: 44px; height: 44px; border-radius: 11px; display: grid; place-items: center;
  background: #173f38; color: #fff7df; font-weight: 850; letter-spacing: .02em;
}
.brand-title { overflow: hidden; font-weight: 780; line-height: 1.22; text-overflow: ellipsis; white-space: nowrap; }
.brand-meta { color: var(--muted); font-size: 12px; margin-top: 3px; }
.close-menu { display: none; border: 0; background: transparent; color: var(--muted); font-size: 27px; line-height: 1; }
.search {
  width: 100%; height: 42px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel);
  padding: 0 12px; outline: none; margin-bottom: 16px; color: var(--ink);
}
.search:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12); }
.nav { display: grid; gap: 5px; }
.nav details > summary { list-style: none; cursor: pointer; }
.nav details > summary::-webkit-details-marker { display: none; }
.nav-section { border-bottom: 1px solid var(--line); padding: 2px 0 7px; }
.nav-section:last-child { border-bottom: 0; }
.section-title {
  display: flex; align-items: center; gap: 8px; min-height: 38px; padding: 0 8px;
  border-radius: 8px; color: #405049; font-size: 13px; font-weight: 800;
}
.section-title:hover { background: #edf2ee; }
.section-title::before { content: "›"; color: var(--muted); font-size: 18px; transition: transform 150ms ease; }
.nav-section[open] > .section-title::before { transform: rotate(90deg); }
.section-count { margin-left: auto; color: var(--muted); font-size: 11px; font-weight: 600; }
.nav-subgroup { margin: 1px 0 3px 13px; }
.collection-title {
  display: flex; align-items: center; min-height: 30px; padding: 0 8px;
  color: var(--muted); font-size: 11px; font-weight: 780;
}
.collection-title::before { content: "›"; margin-right: 6px; font-size: 15px; transition: transform 150ms ease; }
.nav-subgroup[open] > .collection-title::before { transform: rotate(90deg); }
.nav-links { display: grid; gap: 2px; margin: 2px 0 5px; }
.nav-link {
  display: block; border-radius: 8px; padding: 7px 9px 7px 22px; color: #2e3d36; text-decoration: none;
  font-size: 14px; line-height: 1.38; overflow-wrap: anywhere;
}
.nav-link:hover { background: #eaf1ed; color: var(--accent-strong); }
.nav-link.active { background: var(--accent-soft); color: var(--accent-strong); font-weight: 760; }
.nav-empty { padding: 22px 9px; color: var(--muted); font-size: 13px; text-align: center; }
.sidebar-foot { padding: 14px 8px 0; border-top: 1px solid var(--line); font-size: 12px; }
.sidebar-foot a { color: var(--muted); }
.main { min-width: 0; display: grid; grid-template-rows: auto 1fr auto; }
.topbar {
  position: sticky; top: 0; z-index: 5; min-width: 0; min-height: 58px; display: flex; align-items: center; gap: 12px;
  border-bottom: 1px solid var(--line); background: rgba(245, 247, 244, .94); backdrop-filter: blur(14px);
  padding: 0 28px;
}
.menu {
  display: none; flex: 0 0 auto; width: 38px; height: 38px; border: 1px solid var(--line); border-radius: 9px;
  background: var(--panel); color: var(--ink);
}
.crumbs { min-width: 0; display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: 13px; white-space: nowrap; overflow: hidden; }
.crumbs a { color: var(--muted); text-decoration: none; }
.crumbs span { overflow: hidden; text-overflow: ellipsis; }
#crumb-group { flex: 0 1 auto; }
#crumb-title { flex: 0 1 auto; color: #425149; }
.raw { flex: 0 0 auto; margin-left: auto; color: var(--muted); font-size: 13px; text-decoration: none; }
.raw:hover { color: var(--accent); }
.content-shell {
  width: min(100%, 1180px); margin: 0 auto; display: grid; grid-template-columns: minmax(0, 820px) 220px;
  align-items: start; gap: 54px; padding: 46px 36px 72px;
}
.markdown { min-width: 0; font-size: 16px; line-height: 1.78; }
.markdown:focus { outline: none; }
.markdown h1 { margin: 0 0 22px; font-size: clamp(30px, 3.1vw, 40px); line-height: 1.2; letter-spacing: -.02em; }
.markdown h2 { margin: 42px 0 14px; padding-top: 26px; border-top: 1px solid var(--line); font-size: 24px; line-height: 1.35; scroll-margin-top: 78px; }
.markdown h3 { margin: 30px 0 10px; font-size: 19px; scroll-margin-top: 78px; }
.markdown p { margin: 12px 0; }
.markdown ul, .markdown ol { padding-left: 1.5rem; }
.markdown li { margin: 5px 0; }
.markdown a { overflow-wrap: anywhere; }
.markdown blockquote { margin: 20px 0; border-left: 4px solid var(--warn); background: #fff7e8; padding: 11px 16px; color: #4b3f2f; }
.markdown blockquote p:first-child { margin-top: 0; }
.markdown blockquote p:last-child { margin-bottom: 0; }
.markdown code { border-radius: 5px; background: #e9efeb; padding: 2px 5px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .92em; }
.markdown pre { overflow: auto; border-radius: 8px; background: var(--code); color: var(--code-text); padding: 16px; box-shadow: var(--shadow); }
.markdown pre code { background: transparent; color: inherit; padding: 0; }
.markdown table { display: block; width: 100%; overflow: auto; border-collapse: collapse; margin: 20px 0; }
.markdown th, .markdown td { border: 1px solid var(--line); padding: 8px 10px; vertical-align: top; }
.markdown th { background: #eaf1ed; text-align: left; }
.markdown img { display: block; max-width: 100%; height: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); margin: 18px 0; }
.markdown hr { border: 0; border-top: 1px solid var(--line); margin: 28px 0; }
.empty-link { color: var(--muted); border-bottom: 1px dotted var(--muted); }
.home-page > p:first-of-type { color: #44544d; font-size: 18px; line-height: 1.75; }
.home-page h2 + ul { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; padding: 0; list-style: none; }
.home-page h2 + ul li { margin: 0; }
.home-page h2 + ul a {
  min-height: 54px; display: flex; align-items: center; border: 1px solid var(--line); border-radius: 10px;
  background: var(--panel); padding: 11px 14px; color: var(--ink); text-decoration: none;
}
.home-page h2 + ul a:hover { border-color: #9cc8bf; box-shadow: 0 8px 24px rgba(29, 41, 36, .07); color: var(--accent-strong); }
.resource-page table { display: table; width: 100%; table-layout: fixed; }
.resource-page th:first-child, .resource-page td:first-child { width: auto; }
.resource-page th:nth-child(2), .resource-page td:nth-child(2) { width: 100px; }
.resource-page th:nth-child(3), .resource-page td:nth-child(3) { width: 110px; }
.toc { position: sticky; top: 82px; max-height: calc(100vh - 110px); overflow: auto; padding-left: 18px; border-left: 1px solid var(--line); }
.toc-title { margin: 0 0 10px; color: #3c4b44; font-size: 12px; font-weight: 800; }
.toc-list { display: grid; gap: 3px; margin: 0; padding: 0; list-style: none; }
.toc a { display: block; padding: 5px 7px; border-radius: 6px; color: var(--muted); font-size: 12px; line-height: 1.4; text-decoration: none; }
.toc a:hover { background: #eaf1ed; color: var(--accent-strong); }
.toc .toc-h3 a { padding-left: 18px; }
.pager { width: min(100%, 1180px); display: flex; justify-content: space-between; gap: 14px; margin: 0 auto; padding: 0 36px 44px; }
.pager a { min-height: 46px; max-width: 48%; display: flex; align-items: center; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); color: var(--ink); padding: 8px 14px; text-decoration: none; }
.pager a:hover { border-color: #9cc8bf; color: var(--accent-strong); }
.backdrop { display: none; }
@media (max-width: 1120px) {
  .content-shell { max-width: 900px; grid-template-columns: minmax(0, 1fr); }
  .toc { display: none; }
}
@media (max-width: 820px) {
  .layout { display: block; }
  .sidebar { position: fixed; inset: 0 auto 0 0; z-index: 20; width: min(88vw, 330px); transform: translateX(-105%); transition: transform 180ms ease; box-shadow: var(--shadow); }
  body.sidebar-open .sidebar { transform: translateX(0); }
  body.sidebar-open { overflow: hidden; }
  .close-menu { display: block; margin-left: auto; }
  .backdrop { position: fixed; inset: 0; z-index: 15; width: 100%; border: 0; background: rgba(16, 28, 23, .38); opacity: 0; pointer-events: none; transition: opacity 180ms ease; }
  body.sidebar-open .backdrop { display: block; opacity: 1; pointer-events: auto; }
  .menu { display: block; }
  .topbar { padding: 0 16px; }
  #crumb-group, .crumbs span:nth-of-type(1) { display: none; }
  .content-shell { width: 100%; padding: 30px 18px 54px; }
  .markdown h1 { font-size: 30px; overflow-wrap: anywhere; }
  .markdown h2 { margin-top: 34px; }
  .pager { padding: 0 18px 32px; flex-direction: column; }
  .pager a { max-width: none; width: 100%; }
}
@media (max-width: 620px) {
  .raw { display: none; }
  .home-page > p:first-of-type { font-size: 16px; }
  .home-page h2 + ul { grid-template-columns: 1fr; }
  .resource-page table, .resource-page tbody, .resource-page tr, .resource-page td { display: block; width: 100%; }
  .resource-page thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
  .resource-page table { overflow: visible; }
  .resource-page tr { margin: 11px 0; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); padding: 11px 13px; }
  .resource-page td { width: 100% !important; border: 0; padding: 3px 0; overflow-wrap: anywhere; }
  .resource-page td:first-child { padding-bottom: 7px; font-weight: 700; }
  .resource-page td:nth-child(2), .resource-page td:nth-child(3) { display: inline; color: var(--muted); font-size: 13px; }
  .resource-page td:nth-child(2)::after { content: " · "; }
}
"""


WIKI_JS = r"""
const state = { manifest: null, pages: [], byPath: new Map(), currentPath: "" };
const externalPattern = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;
const groupOrder = ["开始使用", "协会资料", "资源库", "历史手册", "站点维护"];

function encodePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}
function dirname(path) {
  const index = path.lastIndexOf("/");
  return index === -1 ? "" : path.slice(0, index);
}
function normalizePath(path) {
  const parts = [];
  path.split("/").forEach((part) => {
    if (!part || part === ".") return;
    if (part === "..") parts.pop();
    else parts.push(part);
  });
  return parts.join("/");
}
function resolveRelative(base, target) {
  if (!target || target.startsWith("#") || externalPattern.test(target) || target.startsWith("//")) return target;
  const [pathPart, hashPart] = target.split("#");
  let decoded = pathPart;
  try { decoded = decodeURI(pathPart); } catch (_) { /* Keep the original path. */ }
  const normalized = normalizePath(`${dirname(base)}/${decoded}`);
  return hashPart === undefined ? normalized : `${normalized}#${hashPart}`;
}
function contentUrl(path) { return `content/${encodePath(path)}`; }
function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
function unescapeTarget(text) {
  return text.replaceAll("&amp;", "&").replaceAll("&quot;", '"').replaceAll("&#39;", "'");
}
function slugify(text) {
  return text.trim().toLowerCase().replace(/[^\p{Letter}\p{Number}]+/gu, "-").replace(/^-+|-+$/g, "");
}
function renderInline(text, basePath) {
  let rendered = escapeHtml(text);
  rendered = rendered.replace(/`([^`]+)`/g, "<code>$1</code>");
  rendered = rendered.replace(/!\[([^\]]*)\]\(([^()\n]*(?:\([^()\n]*\)[^()\n]*)*)\)/g, (_, alt, href) => {
    const cleanHref = unescapeTarget(href.trim());
    if (!cleanHref) return "";
    const finalHref = externalPattern.test(cleanHref) || cleanHref.startsWith("//") ? cleanHref : contentUrl(resolveRelative(basePath, cleanHref));
    return `<img src="${escapeHtml(finalHref)}" alt="${alt}" loading="lazy">`;
  });
  rendered = rendered.replace(/\[([^\]]+)\]\(([^()\n]*(?:\([^()\n]*\)[^()\n]*)*)\)/g, (_, label, href) => {
    const cleanHref = unescapeTarget(href.trim());
    if (!cleanHref) return label;
    if (externalPattern.test(cleanHref) || cleanHref.startsWith("//")) {
      return `<a href="${escapeHtml(cleanHref)}" target="_blank" rel="noreferrer">${label}</a>`;
    }
    if (cleanHref.startsWith("#")) {
      return `<a href="#/${escapeHtml(basePath)}${escapeHtml(cleanHref)}">${label}</a>`;
    }
    const resolved = resolveRelative(basePath, cleanHref);
    const pagePath = resolved.split("#")[0];
    if (state.byPath.has(pagePath)) return `<a href="#/${escapeHtml(resolved)}">${label}</a>`;
    return `<a href="${escapeHtml(contentUrl(resolved))}" target="_blank" rel="noreferrer">${label}</a>`;
  });
  rendered = rendered.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  rendered = rendered.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  return rendered;
}
function isTableDivider(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}
function splitTableRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}
function markdownToHtml(markdown, basePath) {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const html = [];
  let i = 0, inCode = false, codeLines = [], codeLang = "", listType = null;
  const headingIds = new Map();
  function closeList() { if (listType) { html.push(`</${listType}>`); listType = null; } }
  while (i < lines.length) {
    const line = lines[i], trimmed = line.trim();
    const fence = trimmed.match(/^(```|~~~)\s*(.*)$/);
    if (fence) {
      closeList();
      if (!inCode) { inCode = true; codeLang = fence[2] || ""; codeLines = []; }
      else { html.push(`<pre><code data-lang="${escapeHtml(codeLang)}">${escapeHtml(codeLines.join("\n"))}</code></pre>`); inCode = false; }
      i += 1; continue;
    }
    if (inCode) { codeLines.push(line); i += 1; continue; }
    if (!trimmed) { closeList(); i += 1; continue; }
    if (/^---+$/.test(trimmed) || /^\*\*\*+$/.test(trimmed)) { closeList(); html.push("<hr>"); i += 1; continue; }
    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = Math.min(6, heading[1].length), baseId = slugify(heading[2]) || `section-${i + 1}`;
      const count = (headingIds.get(baseId) || 0) + 1;
      headingIds.set(baseId, count);
      const id = count === 1 ? baseId : `${baseId}-${count}`;
      html.push(`<h${level} id="${id}">${renderInline(heading[2], basePath)}</h${level}>`);
      i += 1; continue;
    }
    if (i + 1 < lines.length && trimmed.includes("|") && isTableDivider(lines[i + 1])) {
      closeList();
      const headers = splitTableRow(trimmed); i += 2;
      const bodyRows = [];
      while (i < lines.length && lines[i].trim().includes("|")) { bodyRows.push(splitTableRow(lines[i])); i += 1; }
      html.push("<table><thead><tr>");
      headers.forEach((cell) => html.push(`<th>${renderInline(cell, basePath)}</th>`));
      html.push("</tr></thead><tbody>");
      bodyRows.forEach((row) => { html.push("<tr>"); row.forEach((cell) => html.push(`<td>${renderInline(cell, basePath)}</td>`)); html.push("</tr>"); });
      html.push("</tbody></table>");
      continue;
    }
    const unordered = line.match(/^\s*[-*+]\s+(.+)$/), ordered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (unordered || ordered) {
      const wanted = unordered ? "ul" : "ol";
      if (listType !== wanted) { closeList(); html.push(`<${wanted}>`); listType = wanted; }
      html.push(`<li>${renderInline((unordered || ordered)[1], basePath)}</li>`);
      i += 1; continue;
    }
    if (trimmed.startsWith(">")) {
      closeList();
      const quoteLines = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) { quoteLines.push(lines[i].trim().replace(/^>\s?/, "")); i += 1; }
      html.push(`<blockquote>${quoteLines.map((item) => `<p>${renderInline(item, basePath)}</p>`).join("")}</blockquote>`);
      continue;
    }
    closeList();
    const paragraph = [trimmed]; i += 1;
    while (i < lines.length && lines[i].trim() && !/^(#{1,6})\s+/.test(lines[i].trim()) && !/^\s*[-*+]\s+/.test(lines[i]) && !/^\s*\d+\.\s+/.test(lines[i]) && !/^(```|~~~)/.test(lines[i].trim()) && !lines[i].trim().startsWith(">")) {
      paragraph.push(lines[i].trim()); i += 1;
    }
    html.push(`<p>${renderInline(paragraph.join(" "), basePath)}</p>`);
  }
  closeList();
  if (inCode) html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  return html.join("\n");
}
function renderSidebar(filter = "") {
  const nav = document.getElementById("nav");
  const query = filter.trim().toLowerCase();
  const pages = query
    ? state.pages.filter((page) => [page.title, page.navGroup, page.navSubgroup, page.source, page.excerpt, ...(page.headings || [])].join(" ").toLowerCase().includes(query))
    : state.pages;
  const groups = new Map();
  pages.forEach((page) => {
    if (!groups.has(page.navGroup)) groups.set(page.navGroup, new Map());
    const subgroups = groups.get(page.navGroup);
    if (!subgroups.has(page.navSubgroup)) subgroups.set(page.navSubgroup, []);
    subgroups.get(page.navSubgroup).push(page);
  });
  if (!pages.length) {
    nav.innerHTML = '<div class="nav-empty">没有匹配的页面</div>';
    return;
  }
  const current = state.byPath.get(state.currentPath);
  const fragments = [];
  [...groups.entries()]
    .sort(([a], [b]) => groupOrder.indexOf(a) - groupOrder.indexOf(b))
    .forEach(([group, subgroups]) => {
      const count = [...subgroups.values()].reduce((total, items) => total + items.length, 0);
      const groupOpen = Boolean(query) || current?.navGroup === group;
      fragments.push(`<details class="nav-section"${groupOpen ? " open" : ""}><summary class="section-title">${escapeHtml(group)}<span class="section-count">${count}</span></summary>`);
      subgroups.forEach((items, subgroup) => {
        const subgroupOpen = Boolean(query) || items.some((page) => page.path === state.currentPath);
        fragments.push(`<details class="nav-subgroup"${subgroupOpen ? " open" : ""}><summary class="collection-title">${escapeHtml(subgroup)}</summary><div class="nav-links">`);
      items.forEach((page) => {
        const active = page.path === state.currentPath ? " active" : "";
          fragments.push(`<a class="nav-link${active}" href="#/${escapeHtml(page.path)}">${escapeHtml(page.title)}</a>`);
      });
        fragments.push("</div></details>");
    });
      fragments.push("</details>");
  });
  nav.innerHTML = fragments.join("");
}
function pageFromHash() {
  let raw = location.hash.replace(/^#\/?/, "");
  try { raw = decodeURI(raw); } catch (_) { raw = ""; }
  const path = raw.split("#")[0];
  if (path && state.byPath.has(path)) return raw;
  return "00-wiki/README.md";
}
function renderToc(page) {
  const toc = document.getElementById("toc");
  const headings = [...document.querySelectorAll("#content h2, #content h3")];
  if (!headings.length) {
    toc.hidden = true;
    toc.innerHTML = "";
    return;
  }
  const links = headings.map((heading) => {
    const level = heading.tagName === "H3" ? "toc-h3" : "toc-h2";
    return `<li class="${level}"><a href="#/${escapeHtml(page.path)}#${escapeHtml(heading.id)}">${escapeHtml(heading.textContent)}</a></li>`;
  });
  toc.innerHTML = `<div class="toc-title">本页目录</div><ol class="toc-list">${links.join("")}</ol>`;
  toc.hidden = false;
}
function setPagerLink(element, page, direction) {
  if (!page) {
    element.hidden = true;
    element.removeAttribute("href");
    element.textContent = "";
    return;
  }
  element.hidden = false;
  element.href = `#/${page.path}`;
  element.textContent = direction === "prev" ? `← ${page.title}` : `${page.title} →`;
}
function setSidebar(open) {
  document.body.classList.toggle("sidebar-open", open);
  document.getElementById("menu").setAttribute("aria-expanded", String(open));
}
async function loadPage(pathWithHash) {
  const [path, anchor] = pathWithHash.split("#");
  const page = state.byPath.get(path) || state.byPath.get("00-wiki/README.md");
  state.currentPath = page.path;
  renderSidebar(document.getElementById("search").value);
  const response = await fetch(contentUrl(page.path));
  if (!response.ok) throw new Error(`无法读取页面：${page.path}`);
  const markdown = await response.text();
  const content = document.getElementById("content");
  content.className = "markdown";
  if (page.path === "00-wiki/README.md") content.classList.add("home-page");
  if (page.path === "00-wiki/resources.md" || page.path.startsWith("00-wiki/resources/")) content.classList.add("resource-page");
  content.innerHTML = markdownToHtml(markdown, page.path);
  renderToc(page);
  document.title = `${page.title} · SCU Maker 文档资料 Wiki`;
  document.getElementById("crumb-group").textContent = page.navGroup;
  document.getElementById("crumb-title").textContent = page.title;
  const raw = document.getElementById("raw");
  if (page.source === "generated") {
    raw.hidden = true;
    raw.removeAttribute("href");
  } else {
    raw.hidden = false;
    raw.href = contentUrl(page.path);
    raw.title = page.source;
  }
  const siblings = state.pages.filter((item) => item.navGroup === page.navGroup);
  const index = siblings.findIndex((item) => item.path === page.path);
  setPagerLink(document.getElementById("prev"), siblings[index - 1], "prev");
  setPagerLink(document.getElementById("next"), siblings[index + 1], "next");
  setSidebar(false);
  if (anchor) {
    requestAnimationFrame(() => document.getElementById(anchor)?.scrollIntoView());
  } else {
    window.scrollTo({ top: 0 });
  }
}
async function init() {
  const response = await fetch("manifest.json");
  if (!response.ok) throw new Error("无法读取站点清单");
  state.manifest = await response.json();
  state.pages = state.manifest.pages.filter((page) => !page.empty);
  state.pages.forEach((page) => state.byPath.set(page.path, page));
  document.getElementById("site-stats").textContent = `${state.manifest.stats.pages} 页 · ${state.manifest.stats.publishedResources} 个资源`;
  document.getElementById("search").addEventListener("input", (event) => renderSidebar(event.target.value));
  document.getElementById("menu").addEventListener("click", () => setSidebar(true));
  document.getElementById("close-menu").addEventListener("click", () => setSidebar(false));
  document.getElementById("backdrop").addEventListener("click", () => setSidebar(false));
  document.getElementById("nav").addEventListener("click", (event) => {
    if (event.target.closest("a")) setSidebar(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setSidebar(false);
  });
  window.addEventListener("hashchange", () => loadPage(pageFromHash()));
  renderSidebar();
  await loadPage(pageFromHash());
}
init().catch((error) => {
  document.getElementById("content").innerHTML = `<h1>页面加载失败</h1><p>${escapeHtml(error.message)}</p>`;
});
"""


SITE_README = """# SCU Maker 文档资料 Wiki

这个目录由 `tools/build_handbook_wiki.py` 生成，只发布 `projects/docs-and-handbooks` 中的文档资料。

## 本地预览

```bash
python3 -m http.server 4173 -d docs-site
```

访问 `http://127.0.0.1:4173/`。

## 重新生成

```bash
python3 tools/build_handbook_wiki.py --check-external
```

如果不需要联网检测外链，可去掉 `--check-external`。

构建会校验所有发布页面、附件和本地链接；发现空内容或缺失目标时会直接失败。

"""


def write_static_shell(site_manifest: dict[str, object], link_audit: list[dict[str, str]]) -> None:
    (SITE_DIR / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (ASSETS_DIR / "wiki.css").write_text(WIKI_CSS.strip() + "\n", encoding="utf-8")
    (ASSETS_DIR / "wiki.js").write_text(WIKI_JS.strip() + "\n", encoding="utf-8")
    (SITE_DIR / "README.md").write_text(SITE_README, encoding="utf-8")
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (SITE_DIR / "manifest.json").write_text(json.dumps(site_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA_DIR / "external-links.json").write_text(json.dumps(link_audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-external", action="store_true", help="Check public external links over the network")
    args = parser.parse_args()

    reset_output()
    pages, source_to_dest = collect_pages()
    resources = collect_resources()
    copy_resources(resources)
    local_issues, replacements, external_urls = write_source_pages(pages, source_to_dest)
    link_audit = check_external_urls(external_urls) if args.check_external else [
        {"url": url, "status": "unchecked", "code": "", "checked": "no", "note": "本次构建未启用 --check-external"}
        for url in sorted(external_urls)
    ]
    remove_broken_external_links(pages, link_audit, replacements)
    pages = add_generated_pages(pages, resources, local_issues, replacements, link_audit)
    site_manifest = manifest(pages, resources, link_audit)
    write_static_shell(site_manifest, link_audit)
    validate_site(pages, resources)

    print(f"Generated {site_manifest['stats']['pages']} wiki pages in {SITE_DIR.relative_to(ROOT)}")
    print(f"Published {site_manifest['stats']['publishedResources']} resources from {DOCS_ROOT.relative_to(ROOT)}")
    print(f"External links: {site_manifest['stats']['externalLinks']}, broken: {site_manifest['stats']['brokenExternalLinks']}")
    print("Validated all published pages, resources, and local links")


if __name__ == "__main__":
    main()

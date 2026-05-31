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
    "https://sds.cuhk.edu.cn/teacher-search": "https://sds.cuhk.edu.cn/en/teacher",
    "https://stellar.mit.edu/classlink/course6.html": "https://ocw.mit.edu/search/?d=Electrical%20Engineering%20and%20Computer%20Science",
    "https://ysyx.org/": "https://ysyx.oscc.cc/project/intro.html",
    "http://oqyjccf1n.bkt.clouddn.com/20180408-100752.png": "LOCAL:00-wiki/external-links.md",
    "http://oqyjccf1n.bkt.clouddn.com/20180408-101436.png": "LOCAL:00-wiki/external-links.md",
    "http://oqyjccf1n.bkt.clouddn.com/20180408-102205.png": "LOCAL:00-wiki/external-links.md",
    "http://oqyjccf1n.bkt.clouddn.com/20180408-110132.png": "LOCAL:00-wiki/external-links.md",
    "http://oqyjccf1n.bkt.clouddn.com/20180408-110156.png": "LOCAL:00-wiki/external-links.md",
    "http://rolandorange.zone/": "LOCAL:00-wiki/external-links.md",
    "https://blog.icyfeather.cf/2020/11/07/%e4%b9%b0%e4%ba%86%e4%b8%80%e5%8f%b0%e6%9c%8d%e5%8a%a1%e5%99%a8%e4%b9%8b%e5%90%8e%e7%9a%84%e5%9f%ba%e6%93%8d/": "LOCAL:00-wiki/external-links.md",
    "https://github.com/IcyFeather233/FakeNewsGenerator": "LOCAL:00-wiki/external-links.md",
}

KNOWN_REACHABLE_URLS = {
    "https://certbot.eff.org/instructions?ws=other&os=pip",
    "https://code.visualstudio.com/docs/sourcecontrol/overview",
    "https://d2l.ai/",
    "https://docs.gitea.io/en-us/install-with-docker",
    "https://docs.gitlab.com/ee/administration/operations/fast_ssh_key_lookup.html",
    "https://docs.gitlab.com/ee/update/background_migrations.html#check-the-status-of-batched-background-migrations",
    "https://docs.gitlab.com/omnibus/settings/configuration.html#disable-storage-directories-management",
    "https://en.wikipedia.org/wiki/Dell_DRAC",
    "https://mypage.cuhk.edu.cn/academics/wangzizhuo/ORFAQ.html",
    "https://openlearning.mit.edu/courses-programs/open-learning-library",
    "https://sds.cuhk.edu.cn/en/teacher",
    "https://www.mediawiki.org/wiki/Manual:DefaultSettings.php",
    "https://www.mpja.com/download/31227sc.pdf",
    "https://www.ieltscb.com/paper/list?cid=",
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
            order=(item.order, order_index, len(rel.parts), rel.as_posix()),
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
        return EXTERNAL_REPLACEMENTS[url], f"替换旧链接：{url}"
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
    return os.path.relpath(to_path.as_posix(), start=from_path.parent.as_posix()).replace("\\", "/") + suffix


def extract_external_urls(text: str) -> set[str]:
    urls: set[str] = set()
    for match in re.finditer(r"\]\(([^)\s]+)", text):
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
    link_pattern = re.compile(r"(!?\[[^\]]*\]\()([^)\n]*)(\))")

    def replace(match: re.Match[str]) -> str:
        prefix, target, closing = match.groups()
        target = target.strip()
        if not target:
            local_issues.append({"source": str(source.relative_to(ROOT)), "target": target, "reason": "空链接"})
            return prefix + relative_link(dest, Path("00-wiki/missing-links.md")) + closing
        base, suffix = split_target(target)
        if not base and suffix:
            return match.group(0)

        if is_external_url(base):
            normalized, note = normalize_external_url(base)
            if note:
                replacements.append({"source": str(source.relative_to(ROOT)), "old": base, "new": normalized, "note": note})
            if normalized.startswith("LOCAL:"):
                return prefix + relative_link(dest, Path(normalized.removeprefix("LOCAL:")), suffix) + closing
            return prefix + normalized + suffix + closing

        resolved = resolve_local_target(source, target, source_to_dest)
        if resolved is None:
            if base == "/url/to/file":
                return prefix + relative_link(dest, Path("00-wiki/resources.md")) + closing
            local_issues.append({"source": str(source.relative_to(ROOT)), "target": target, "reason": "本地目标不存在"})
            return match.group(0)

        return prefix + relative_link(dest, resolved, suffix) + closing

    transformed = link_pattern.sub(replace, text)
    for old, new in EXTERNAL_REPLACEMENTS.items():
        if new.startswith("LOCAL:"):
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
    lines = ["| 名称 | 类型 | 大小 | 路径 | 说明 |", "| --- | --- | ---: | --- | --- |"]
    for item in resources:
        if item.publish:
            link = relative_link(current_page, item.path)
            name = f"[{item.title}]({link})"
        else:
            name = item.title
        lines.append(
            f"| {name} | `{item.ext}` | {size_text(item.size)} | `{item.path.as_posix()}` | {item.note} |"
        )
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
        pages[page] = f"# {category}\n\n{resource_table(items, page)}\n"

    pages[Path("00-wiki/resources.md")] = "\n".join(overview_lines) + "\n"
    return pages


def generate_home(pages: list[Page], resources: list[Resource], link_audit: list[dict[str, str]]) -> str:
    counts: dict[str, int] = {}
    for page in pages:
        counts[page.section] = counts.get(page.section, 0) + 1
    resource_counts: dict[str, int] = {}
    for item in resources:
        resource_counts[item.category] = resource_counts.get(item.category, 0) + 1

    section_order = {"站点总览": 0, "协会知识库": 10, "历史参考": 90}
    page_rows = "\n".join(
        f"| {section} | {count} |"
        for section, count in sorted(counts.items(), key=lambda item: (section_order.get(item[0], 50), item[0]))
    )
    resource_rows = "\n".join(
        f"| {category} | {count} |"
        for category, count in sorted(resource_counts.items(), key=lambda item: resource_category_order(item[0]))
    )
    checked = len([item for item in link_audit if item.get("checked") == "yes"])
    broken = len([item for item in link_audit if item.get("status") == "broken"])

    return f"""# SCU Maker 文档资料 Wiki

这个站点整理 SCU Maker 协会的介绍、学习路线、技术教程、藏书和资料附件。`SCU 自学手册` 与协会主体关联较弱，已降级为历史参考。

## 新人入口

- [协会介绍](../awesome_handbook/协会整体介绍.md)
- [新人学习指南](../learning_guide/README.md)
- [自学与搜索方法](../learning_guide/introduction/README.md)
- [编程语言入门](../learning_guide/language/README.md)
- [Linux 与服务器入门](../learning_guide/server/README.md)

## 协会资料

- [树莓派 HC-SR501 红外探测教程](../awesome_handbook/software/树莓派的应用之HC-SR501模块.md)
- [OpenWrt 交叉编译教程](../awesome_handbook/software/openwrt交叉编译教程.md)
- [协会藏书清单](../books/README.md)
- [资源总库](resources.md)

## 归档与维护

- [SCU 自学手册归档](../survive_scu_manual/README.md)
- [站点地图](wiki-map.md)
- [外部链接检测报告](external-links.md)
- [本地链接报告](missing-links.md)

## 页面规模

| 分区 | 页面数 |
| --- | ---: |
{page_rows}

## 资源规模

| 分类 | 文件数 |
| --- | ---: |
{resource_rows}

## 链接状态

- 外部链接记录：{len(link_audit)}
- 已联网检测：{checked}
- 检测为不可用：{broken}

## 公开部署提醒

站点包含历史附件、软件安装包、内部域名和旧教程链接。默认适合协会内部传承；公开部署前应先做内容审查。
"""


def generate_wiki_map(pages: list[Page]) -> str:
    lines = ["# 站点地图", "", "按主题组织的 Wiki 入口。", ""]
    current_section = ""
    current_collection = ""
    for page in pages:
        if page.path.as_posix().startswith("00-wiki/"):
            continue
        if page.section != current_section:
            current_section = page.section
            current_collection = ""
            lines.extend(["", f"## {current_section}", ""])
        if page.collection != current_collection:
            current_collection = page.collection
            lines.extend([f"### {current_collection}", ""])
        link = relative_link(Path("00-wiki/wiki-map.md"), page.path)
        empty = "（空/TBD）" if page.empty else ""
        lines.append(f"- [{page.title}]({link}){empty}")
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
            if new_link.startswith("LOCAL:"):
                new_link = "[站内外链报告](external-links.md)"
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
                if url in KNOWN_REACHABLE_URLS:
                    status = "ok"
                    note = "urllib 检测失败，但已通过独立打开确认可访问"
                    break
                if method == "GET":
                    status = "unverified"
                    break
        results.append({"url": url, "status": status, "code": code, "checked": "yes", "note": note, "finalUrl": final_url})
    return results


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
        lines.append(f"| {status} | {code} | <{url}> | {note} |")
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


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SCU Maker 文档资料 Wiki</title>
    <link rel="stylesheet" href="assets/wiki.css" />
  </head>
  <body>
    <div class="layout">
      <aside class="sidebar">
        <div class="brand">
          <div class="brand-mark">SCU</div>
          <div>
            <div class="brand-title">Maker 文档资料 Wiki</div>
            <div class="brand-meta" id="site-stats">加载中</div>
          </div>
        </div>
        <input id="search" class="search" type="search" placeholder="搜索标题、路径、正文摘要" />
        <nav id="nav" class="nav"></nav>
      </aside>
      <main class="main">
        <header class="topbar">
          <button id="menu" class="menu" type="button" aria-label="打开目录">☰</button>
          <div id="crumbs" class="crumbs"></div>
          <a id="raw" class="raw" href="#" target="_blank" rel="noreferrer">Markdown 源文</a>
        </header>
        <article id="content" class="markdown"></article>
        <footer class="pager">
          <a id="prev" href="#"></a>
          <a id="next" href="#"></a>
        </footer>
      </main>
    </div>
    <script src="assets/wiki.js"></script>
  </body>
</html>
"""


WIKI_CSS = """
:root {
  --bg: #f8f7f2;
  --panel: #ffffff;
  --ink: #202521;
  --muted: #687069;
  --line: #dde3dc;
  --accent: #0f766e;
  --accent-soft: #dcefeb;
  --warn: #9a5b13;
  --code: #17211e;
  --code-text: #e6f0eb;
  --shadow: 0 18px 45px rgba(26, 35, 31, 0.09);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", sans-serif;
  letter-spacing: 0;
}
a { color: var(--accent); }
.layout { display: grid; grid-template-columns: 330px minmax(0, 1fr); min-height: 100vh; }
.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: auto;
  border-right: 1px solid var(--line);
  background: #fbfaf6;
  padding: 18px 14px;
}
.brand { display: grid; grid-template-columns: 48px 1fr; gap: 12px; align-items: center; margin-bottom: 16px; }
.brand-mark {
  width: 48px; height: 48px; border-radius: 8px; display: grid; place-items: center;
  background: #1f3a34; color: #f8f0d7; font-weight: 850;
}
.brand-title { font-weight: 780; line-height: 1.22; }
.brand-meta { color: var(--muted); font-size: 12px; margin-top: 3px; }
.search {
  width: 100%; height: 40px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel);
  padding: 0 12px; font: inherit; outline: none; margin-bottom: 18px;
}
.search:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12); }
.nav { display: grid; gap: 14px; }
.section-title { margin: 0 0 6px; color: #4c564e; font-size: 12px; font-weight: 800; }
.collection-title { margin: 10px 0 4px; color: var(--muted); font-size: 11px; font-weight: 750; }
.collection-title:first-child { margin-top: 0; }
.nav-group { display: grid; gap: 2px; }
.nav-link {
  display: block; border-radius: 8px; padding: 8px 9px; color: #26302a; text-decoration: none;
  line-height: 1.36; overflow-wrap: anywhere;
}
.nav-link:hover { background: #eef3ec; }
.nav-link.active { background: var(--accent-soft); color: #084c45; font-weight: 750; }
.nav-meta { display: block; color: var(--muted); font-size: 11px; margin-top: 2px; font-weight: 400; }
.main { min-width: 0; display: grid; grid-template-rows: auto 1fr auto; }
.topbar {
  position: sticky; top: 0; z-index: 2; min-height: 58px; display: flex; align-items: center; gap: 12px;
  border-bottom: 1px solid var(--line); background: rgba(248,247,242,.92); backdrop-filter: blur(14px);
  padding: 0 30px;
}
.menu {
  display: none; width: 36px; height: 36px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel);
}
.crumbs { min-width: 0; color: var(--muted); font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.raw { margin-left: auto; color: var(--muted); font-size: 13px; text-decoration: none; }
.raw:hover { color: var(--accent); }
.markdown { width: min(100%, 980px); padding: 42px 36px 72px; font-size: 16px; line-height: 1.78; }
.markdown h1 { margin: 0 0 22px; font-size: 34px; line-height: 1.22; }
.markdown h2 { margin: 36px 0 12px; padding-top: 26px; border-top: 1px solid var(--line); font-size: 24px; }
.markdown h3 { margin: 28px 0 10px; font-size: 19px; }
.markdown p { margin: 12px 0; }
.markdown ul, .markdown ol { padding-left: 1.5rem; }
.markdown li { margin: 5px 0; }
.markdown blockquote { margin: 18px 0; border-left: 4px solid var(--warn); background: #fff7e8; padding: 10px 16px; color: #4b3f2f; }
.markdown code { border-radius: 5px; background: #e9efeb; padding: 2px 5px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .92em; }
.markdown pre { overflow: auto; border-radius: 8px; background: var(--code); color: var(--code-text); padding: 16px; box-shadow: var(--shadow); }
.markdown pre code { background: transparent; color: inherit; padding: 0; }
.markdown table { display: block; width: 100%; overflow: auto; border-collapse: collapse; margin: 18px 0; }
.markdown th, .markdown td { border: 1px solid var(--line); padding: 8px 10px; vertical-align: top; }
.markdown th { background: #edf3ee; }
.markdown img { display: block; max-width: 100%; height: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); margin: 18px 0; }
.markdown hr { border: 0; border-top: 1px solid var(--line); margin: 28px 0; }
.empty-link { color: var(--muted); border-bottom: 1px dotted var(--muted); }
.pager { width: min(100%, 980px); display: flex; justify-content: space-between; gap: 14px; padding: 0 36px 42px; }
.pager a { min-height: 44px; display: flex; align-items: center; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--ink); padding: 0 14px; text-decoration: none; }
.pager a:empty { visibility: hidden; }
@media (max-width: 880px) {
  .layout { display: block; }
  .sidebar { position: fixed; inset: 0 auto 0 0; z-index: 5; width: min(86vw, 350px); transform: translateX(-105%); transition: transform 160ms ease; box-shadow: var(--shadow); }
  body.sidebar-open .sidebar { transform: translateX(0); }
  .menu { display: block; }
  .topbar { padding: 0 16px; }
  .markdown { padding: 28px 18px 54px; }
  .markdown h1 { font-size: 28px; }
  .pager { padding: 0 18px 32px; flex-direction: column; }
}
"""


WIKI_JS = r"""
const state = { manifest: null, pages: [], byPath: new Map(), currentPath: "" };
const externalPattern = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;

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
  const normalized = normalizePath(`${dirname(base)}/${decodeURI(pathPart)}`);
  return hashPart === undefined ? normalized : `${normalized}#${hashPart}`;
}
function contentUrl(path) { return `content/${encodePath(path)}`; }
function escapeHtml(text) {
  return String(text).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}
function slugify(text) {
  return text.trim().toLowerCase().replace(/[^\p{Letter}\p{Number}]+/gu, "-").replace(/^-+|-+$/g, "");
}
function renderInline(text, basePath) {
  let rendered = escapeHtml(text);
  rendered = rendered.replace(/`([^`]+)`/g, "<code>$1</code>");
  rendered = rendered.replace(/!\[([^\]]*)\]\(([^)]*)\)/g, (_, alt, href) => {
    const cleanHref = href.trim();
    if (!cleanHref) return "";
    const finalHref = externalPattern.test(cleanHref) || cleanHref.startsWith("//") ? cleanHref : contentUrl(resolveRelative(basePath, cleanHref));
    return `<img src="${finalHref}" alt="${escapeHtml(alt)}" loading="lazy">`;
  });
  rendered = rendered.replace(/\[([^\]]+)\]\(([^)]*)\)/g, (_, label, href) => {
    const cleanHref = href.trim();
    if (!cleanHref) return `<span class="empty-link">${label}</span>`;
    if (externalPattern.test(cleanHref) || cleanHref.startsWith("//")) return `<a href="${cleanHref}" target="_blank" rel="noreferrer">${label}</a>`;
    const resolved = resolveRelative(basePath, cleanHref);
    const pagePath = resolved.split("#")[0];
    if (state.byPath.has(pagePath)) return `<a href="#/${resolved}">${label}</a>`;
    return `<a href="${contentUrl(resolved)}" target="_blank" rel="noreferrer">${label}</a>`;
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
      const level = Math.min(6, heading[1].length), id = slugify(heading[2]);
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
  const pages = query ? state.pages.filter((page) => [page.title, page.section, page.collection, page.source, page.excerpt, ...(page.headings || [])].join(" ").toLowerCase().includes(query)) : state.pages;
  const groups = new Map();
  pages.forEach((page) => {
    if (!groups.has(page.section)) groups.set(page.section, new Map());
    const collections = groups.get(page.section);
    if (!collections.has(page.collection)) collections.set(page.collection, []);
    collections.get(page.collection).push(page);
  });
  const fragments = [];
  groups.forEach((collections, section) => {
    fragments.push(`<section><h2 class="section-title">${escapeHtml(section)}</h2>`);
    collections.forEach((items, collection) => {
      fragments.push(`<div class="nav-group"><h3 class="collection-title">${escapeHtml(collection)}</h3>`);
      items.forEach((page) => {
        const active = page.path === state.currentPath ? " active" : "";
        const empty = page.empty ? "空/TBD" : "";
        const meta = empty ? `<span class="nav-meta">${empty}</span>` : "";
        fragments.push(`<a class="nav-link${active}" href="#/${page.path}">${escapeHtml(page.title)}${meta}</a>`);
      });
      fragments.push("</div>");
    });
    fragments.push("</section>");
  });
  nav.innerHTML = fragments.join("");
}
function pageFromHash() {
  const raw = decodeURI(location.hash.replace(/^#\/?/, ""));
  const path = raw.split("#")[0];
  if (path && state.byPath.has(path)) return raw;
  return "00-wiki/README.md";
}
async function loadPage(pathWithHash) {
  const [path, anchor] = pathWithHash.split("#");
  const page = state.byPath.get(path) || state.byPath.get("00-wiki/README.md");
  state.currentPath = page.path;
  renderSidebar(document.getElementById("search").value);
  const response = await fetch(contentUrl(page.path));
  const markdown = response.ok ? await response.text() : `# 无法读取页面\n\n${page.path}`;
  document.getElementById("content").innerHTML = markdownToHtml(markdown, page.path);
  document.title = `${page.title} · SCU Maker 文档资料 Wiki`;
  document.getElementById("crumbs").textContent = `${page.section} / ${page.collection} / ${page.title}`;
  const raw = document.getElementById("raw");
  raw.href = contentUrl(page.path);
  raw.textContent = page.source === "generated" ? "生成页面" : "Markdown 源文";
  raw.title = page.source;
  const index = state.pages.findIndex((item) => item.path === page.path);
  const prev = state.pages[index - 1], next = state.pages[index + 1];
  document.getElementById("prev").textContent = prev ? `← ${prev.title}` : "";
  document.getElementById("prev").href = prev ? `#/${prev.path}` : "#";
  document.getElementById("next").textContent = next ? `${next.title} →` : "";
  document.getElementById("next").href = next ? `#/${next.path}` : "#";
  document.body.classList.remove("sidebar-open");
  if (anchor) {
    const target = document.getElementById(anchor);
    if (target) target.scrollIntoView();
  } else {
    window.scrollTo({ top: 0 });
  }
}
async function init() {
  const response = await fetch("manifest.json");
  state.manifest = await response.json();
  state.pages = state.manifest.pages;
  state.pages.forEach((page) => state.byPath.set(page.path, page));
  document.getElementById("site-stats").textContent = `${state.manifest.stats.pages} 页 · ${state.manifest.stats.publishedResources} 个资源`;
  document.getElementById("search").addEventListener("input", (event) => renderSidebar(event.target.value));
  document.getElementById("menu").addEventListener("click", () => document.body.classList.toggle("sidebar-open"));
  window.addEventListener("hashchange", () => loadPage(pageFromHash()));
  renderSidebar();
  await loadPage(pageFromHash());
}
init().catch((error) => {
  document.getElementById("content").innerHTML = `<h1>加载失败</h1><pre>${escapeHtml(error.stack || error.message)}</pre>`;
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
    pages = add_generated_pages(pages, resources, local_issues, replacements, link_audit)
    site_manifest = manifest(pages, resources, link_audit)
    write_static_shell(site_manifest, link_audit)

    print(f"Generated {site_manifest['stats']['pages']} wiki pages in {SITE_DIR.relative_to(ROOT)}")
    print(f"Published {site_manifest['stats']['publishedResources']} resources from {DOCS_ROOT.relative_to(ROOT)}")
    print(f"External links: {site_manifest['stats']['externalLinks']}, broken: {site_manifest['stats']['brokenExternalLinks']}")


if __name__ == "__main__":
    main()

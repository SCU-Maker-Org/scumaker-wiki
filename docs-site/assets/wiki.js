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

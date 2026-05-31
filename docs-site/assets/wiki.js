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

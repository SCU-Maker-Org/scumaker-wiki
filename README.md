# SCU Maker Wiki

这是 SCU Maker 协会 Wiki 的独立维护仓库。

## 目录结构

- `projects/docs-and-handbooks/`：Wiki 源 Markdown、图片和附件。
- `tools/build_handbook_wiki.py`：静态站点生成脚本。
- `tools/build_docs_site.py`：兼容入口，等价于运行主生成脚本。
- `docs-site/`：生成后的静态站点，可直接部署到 GitHub Pages。

## 本地预览

```bash
python3 -m http.server 4173 -d docs-site
```

访问 `http://127.0.0.1:4173/`。

## 重新生成

```bash
python3 tools/build_handbook_wiki.py
```

如果需要联网检查外链：

```bash
python3 tools/build_handbook_wiki.py --check-external
```

## 维护原则

- 优先维护 `projects/docs-and-handbooks/` 下的源文档，不要只改 `docs-site/`。
- 新页面需要有明确标题和实质内容，空页面直接删除。
- `SCU 自学手册` 已作为历史参考保留，不放在协会 Wiki 主入口。
- 公开部署前检查历史附件、软件安装包、内部域名和旧链接。
 非常感谢SCU 自学指南的'https://github.com/SCU-CS-Runner'
## GitHub Pages

仓库自带 `.github/workflows/deploy-pages.yml`。推送到 `main` 或 `master` 后，GitHub Actions 会重新生成 `docs-site/` 并发布到 Pages。

如果不使用 Actions，也可以直接把 `docs-site/` 作为 Pages 发布目录。

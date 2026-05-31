# SCU Maker 文档资料 Wiki

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



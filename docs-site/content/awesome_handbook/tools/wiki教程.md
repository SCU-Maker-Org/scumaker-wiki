# 如何维护协会 Wiki

这篇文档替代旧 GitBook/Gogs 流程，用来说明现在这个静态 Wiki 应该怎么维护。

## 内容来源

当前站点只整理 `projects/docs-and-handbooks` 下的协会文档：

- `awesome_handbook/`：协会介绍、历史招新、技术教程和 Wiki 维护说明。
- `learning_guide/`：新人学习路线。
- `books/`：协会藏书清单。
- `survive_scu_manual/`：川大学生自学经验归档，不作为协会主入口。

## 添加或修改页面

1. 在对应目录里编辑 Markdown 文件。
2. 页面标题优先使用一级标题，例如 `# 新人学习指南`。
3. 图片和附件尽量放在同一资料目录下，使用相对链接引用。
4. 不要添加空页面；暂时没有内容的主题先不要建文件。
5. 过期但有历史价值的内容，在正文开头标注“历史资料”或“旧版教程”。

## 重新生成站点

在仓库根目录运行：

```bash
python3 tools/build_handbook_wiki.py
```

如果需要联网检查外链，运行：

```bash
python3 tools/build_handbook_wiki.py --check-external
```

本地预览：

```bash
python3 -m http.server 4173 -d docs-site
```

然后访问 `http://127.0.0.1:4173/`。

## 内容整理原则

- 新人首先应该看到协会介绍、学习路线、教程和资源库。
- `SCU 自学手册` 属于扩展阅读，避免放在首页核心区域。
- 空白页、坏链接索引、只有一两个失效链接的页面应直接删除。
- 内部服务地址、历史软件安装包和账号配置类内容公开前必须人工审查。

## Git 基本流程

```bash
git status
git add <changed-files>
git commit -m "整理协会 Wiki"
```

如果只是本地整理和预览，不需要提交也可以直接重新生成站点。

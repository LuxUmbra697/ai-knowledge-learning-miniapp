# OpenSpec 使用教程（超简单版）

> 用 OpenSpec 给「LuxUmbra AI 闯关学习」项目扩展功能，傻子都能懂的 3 步教程。

---

## OpenSpec 是什么？（一句话）

OpenSpec 是一个帮你和 AI **先商量好要做什么，再动手写代码** 的工具。它会自动生成需求文档、设计方案和任务清单，让 AI 编码更靠谱。

---

## 第一步：安装和初始化

### 1. 安装 OpenSpec（全局安装一次就行）

```bash
npm install -g @fission-ai/openspec@latest
```

### 2. 在项目里初始化

```bash
cd c:\code\ai-code\luxumbra-ai-learn
openspec init --tools github-copilot
```

> 运行后会提示你选择配置，**一路回车选默认就行**。
>
> `--tools github-copilot` 表示你用的是 VS Code 里的 GitHub Copilot。如果你还用 Cursor 可以写 `--tools github-copilot,cursor`。

初始化完成后，项目里会多出一个 `openspec/` 文件夹：

```
openspec/
├── specs/          ← 存放系统现有行为的规格说明
├── changes/        ← 存放每次要改的需求（一个功能一个文件夹）
└── config.yaml     ← 配置文件
```

---

## 第二步：提出一个新功能（核心操作！）

在 VS Code 的 Copilot Chat 中，输入：

```
/opsx:propose 增加用户学习数据统计看板
```

> 💡 `/opsx:propose` 后面跟你想做的功能描述，用中文就行。

**AI 会自动帮你生成一整套文档：**

```
openspec/changes/增加用户学习数据统计看板/
├── proposal.md     ← 为什么做、做什么（需求提案）
├── specs/          ← 具体的需求规格
├── design.md       ← 怎么做（技术设计）
└── tasks.md        ← 任务清单（带 checkbox）
```

你可以检查这些文件，觉得不对就直接修改，改完再继续。

---

## 第三步：让 AI 干活 + 归档

### 3a. 让 AI 按任务清单写代码

```
/opsx:apply
```

AI 会按照 `tasks.md` 里的任务一个一个完成。

### 3b. 完成后归档

```
/opsx:archive
```

归档后，这次改动的规格会合并进 `openspec/specs/`，成为项目的正式文档。

---

## 完整流程总结

```
/opsx:propose "你想做的功能"   →   检查生成的文档   →   /opsx:apply   →   /opsx:archive
         提需求                    人工确认              AI 编码           归档
```

**就这 3 个命令，循环用就行了。**

---

## 实战举例

以下是本项目可以用 OpenSpec 扩展的功能示例：

| 功能 | 命令 |
|------|------|
| 增加排行榜 | `/opsx:propose 增加用户答题排行榜功能` |
| 支持视频输入 | `/opsx:propose 支持用户输入视频链接自动生成题目` |
| 错题本 | `/opsx:propose 增加错题本功能，记录用户答错的题目` |
| 学习提醒 | `/opsx:propose 增加每日学习提醒推送功能` |
| 多人对战 | `/opsx:propose 增加好友PK答题对战模式` |

---

## 常用 CLI 命令速查

```bash
openspec list              # 查看当前进行中的功能
openspec show <功能名>      # 查看某个功能的详情
openspec validate <功能名>  # 检查规格格式是否正确
openspec view              # 打开交互式看板
openspec update            # 更新 OpenSpec 到最新配置
```

---

## 注意事项

1. **Node.js 版本要求 ≥ 20.19.0**，运行 `node -v` 检查
2. 生成的文档不满意可以随时手动改，改完再 `/opsx:apply`
3. 推荐用高推理能力的模型（如 Claude Opus、GPT-5 系列）效果更好
4. 每次开始新功能前，建议清理一下聊天上下文，保持 AI 的注意力集中

# Testing / 可审计验证

## 三条独立路径

1. 确定性测试：禁止读取真实 dotenv，禁止默认调用外部付费服务；数据库只用隔离回环实例。
2. 少量真实供应商测试：显式开关、受控调用上限，使用合成材料和独立 COS 前缀。
3. 浏览器端到端：真实 H5 → API → worker → MySQL/Chroma；付费结果可保存后复用，不伪装重新调用。

从仓库根目录、已激活的 Python 环境运行：

```sh
python -m ruff check backend/app backend/tests backend/integration --select F
python scripts/test_offline.py -q --tb=short
python scripts/test_database.py --tb=short
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build:h5
npm --prefix frontend run build:weapp
node frontend/scripts/check-build.mjs --both
node frontend/scripts/measure-build.mjs --output .local/build-size.json
```

`test_offline.py` 在导入应用前关闭 dotenv 和网络；普通 pytest 不是推荐入口。
MySQL 测试需要 [隔离本地实例](development.md)，仅使用 `ai_learn_test`，不连接线上。
真实文件解析、SQL 事务、唯一约束、取消栅栏、租约恢复和服务端答案权限均在回归范围内。

## 浏览器

先启动 [本地完整系统](development.md)。在 frontend 目录：

```sh
npx playwright install chromium
npm run test:e2e
```

测试前确认 API ready。不要在浏览器测试中途重新构建 H5，避免产物被覆盖。
页面、网络响应和持久化共同检查；截图在 `docs/screenshots/h5/`。公开材料只使用合成内容。
页面截图不是小程序截图。默认跳过需要额外付费的测试，跳过不算通过。

真实付费结果复用由 `AI_LEARN_QUIZ_REUSE`、`AI_LEARN_TEXT_REUSE`、`AI_LEARN_PUBLIC_REUSE`、
`AI_LEARN_IMAGE_REUSE`、`AI_LEARN_TUTOR_REUSE`、`AI_LEARN_COMPANION_REUSE` 控制；
这些开关要求本机 `.local/` 已有相应私有账号和结果文件，不能在首次克隆或 CI 中假定存在。
`E2E_PYTHON` 可指定已安装依赖的 Python；CI 明确用隔离环境的 python。

## 真实调用

不要批量运行所有 smoke。先核对配置、权限和预算，选择一个所需场景：

```sh
python scripts/smoke_companion.py --paid
```

该场景验证两个角色隔离及确认记忆，最多三个对话阶段、每阶段三次尝试。
本次实际为 3 次模型调用、2523 tokens。没有查到货币账单，不把费用写成零。
其他真实题型、题图、公开搜索、辅导和引用测试的脚本位于 `scripts/smoke_*.py` 与
`scripts/verify_*.py`；执行前阅读脚本的目标地址、开关及调用上限，不在默认 CI 启用。
没有 Key/权限时记录具体错误，不用 Mock 结果顶替供应商验证。

## 算法

```sh
python scripts/evaluate_rag.py
python scripts/experiment_bkt.py --output .local/bkt-reproduction
```

RAG 使用已提交的合成材料向量缓存和真实本地 Chroma，零新增付费请求。
脚本更新原始结果文件，延迟可能改变；不为了保持旧指标而丢弃新观测。
BKT 运行真实轻量参数拟合及校准，但所有学习者记录为合成数据。
详见 [RAG](rag-evaluation.md) 与 [算法实验](algorithm-experiments.md)。

## 当前执行结果与限制

- 锁定 Python 3.13 环境：440 项离线通过、71 项 MySQL 通过，26 项前端单元通过。
- 本地 Chromium 全回归：27 项通过、4 项额外付费场景跳过，实际耗时约 2.6 分钟。
- H5/weapp 连续构建通过，入口和主包预算检查通过。官方编译器通过 8 个 WXSS 文件。
- 开发工具使用固定 AppID，实际页面与角色单击切换通过；私人设置关闭域名校验，合法域名和真机未验收。
- `frontend/scripts/check-weapp-selection.mjs` 验证指定角色进入、往返切换、头像与正文一致；不新增模型调用。
- 真实调用另外计数，复用测试不重复扣费。截图涵盖 320/390/1440 宽度、主题与主要业务。
- 没有“所有设备通过”、高并发或无故障承诺。语义引用正确性、长对话人物一致性、长期学习效果
  仍需独立数据评测，不能从结构化校验或短 smoke 外推。

`.github/workflows/verify.yml` 使用隔离 MySQL、无 Key 的 API/worker、双端构建和 H5 浏览器。
实际 CI 状态以对应 commit 的 Actions 为准，不因写了 YAML 就称通过。
每次 bug 修复先记录失败用例、再修复、重跑相关回归；私人工作记录位于忽略的 `.local/sdlc/`。

### 练习生成重试回归

`backend/tests/test_quiz_retry.py` 覆盖第十次成功、十次失败停止、检查点恢复、永久错误、限频退避，
以及跨批次重复只修复错误批次。`backend/integration/test_quiz_retry.py` 在隔离 MySQL 验证
所有批次共享十次预算、重启后次数保留、跨用户拒绝、客户端篡改拒绝、删除资料与重复点击幂等。
`frontend/e2e/quiz-retry.spec.ts` 验证刷新只读、显式重试与真实次数显示；该用例的失败状态为合成注入。
另行执行的真实 DeepSeek + 网页参考联调得到 8 道题（3 单选、1 多选、1 判断、1 填空、2 问答），
4 次模型尝试和 1 次搜索后完成，已返回用量为 11,967 tokens；一次模型超时未返回用量，不能视为免费。
完整性、题干去重、预答题答案隐藏、刷新恢复和重复请求复用均检查；不据此宣称所有题目事实正确。

## English Summary

Offline tests, bounded real-provider smoke tests and actual-browser tests are separate evidence.
The commands above disable developer dotenv and use isolated MySQL. Default CI has no model secrets
and never touches production. Saved live outputs can be reused locally, but are not new paid calls.
H5 and actual DevTools screenshots are labeled separately. See the stated counts and limitations; builds cannot prove native devices,
semantic entailment, long-term learning improvements or production capacity.

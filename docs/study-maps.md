# 学习梳理与错题关系图

完成全部作答即可在学习报告页查看图谱，不需要再次付费生成。图谱不是模型输出的一段
任意 Mermaid 字符串：`app/learning/maps.py` 从已经保存的题目标签、服务端判分和仍有效
的原文引用构造节点及边，校验节点唯一性、悬空边、循环和数量上限。

## 数据与权限

- `GET /api/v1/quiz/{quiz_id}/maps` 校验身份及练习归属；未完成返回 409，非本人返回 404。
- Migration 11 的 `quiz_learning_maps` 保存版本、内容哈希和结构化图谱。重复读取不会新增
  学习观察或模型调用。这是派生缓存，不是学习状态的权威来源。
- 每次读取重新核验引用的文档所有权、版本、分块和逐字引文。来源删除、重建或暂不可用时，
  不再返回该来源节点，并刷新派生哈希。原文跳转接口仍独立鉴权；不提供永久公开链接。
- 内容梳理显示主题、知识点和题目；关系网络加入共享原文；错题复盘按真实判分筛选并保留
  相关知识点与来源。知识点来自生成题目的标签，**不是人工确认或经过训练的知识图谱**。
  连线只表示包含、考查或原文支持，不代表前置条件、因果关系或学习效果。

## 两端渲染

H5 固定 Mermaid 11.17.2、DOMPurify 3.4.15，按需加载，使用 `securityLevel: strict`、
`htmlLabels: false`。节点 ID 由服务器产生且客户端再次校验。显示标签中的语法字符替换为
不可执行的全角字形，完整原始文本仍在下方文本列表中。原始模型 Mermaid、配置指令、
click 回调和外部 URL 都不能进入绘图。SVG 再经 SVG 白名单净化，移除活动标签和链接，
作为本地 Blob 图片显示，不作为业务 DOM 注入；离开页面释放 Blob 与临时测量节点。

小程序使用独立平台文件、Dagre 1.1.8 布局与原生 Canvas 2D。固定视口绘制，触摸平移、
缩放、轻点节点查看完整内容；不创建随图谱变大的巨大画布，也不引入 Mermaid/DOMPurify。
背景隐藏时取消绘制帧，卸载移除尺寸监听。完整节点及原文入口同时有普通组件列表。
**布局单元测试和 weapp 构建已通过；微信开发者工具服务端口尚未开启，Canvas 的 IDE 和
真机运行仍未验证，不能将 H5 截图当成小程序证据。**

## 实测与复现

```powershell
backend/venv/Scripts/python.exe scripts/test_offline.py -q backend/tests/test_learning_maps.py
backend/venv/Scripts/python.exe scripts/test_database.py -q backend/integration/test_learning_maps.py
cd frontend
npm test
npm run typecheck
npm run build:h5
npm run build:weapp
npx playwright test e2e/learning-map.spec.ts
```

数据库测试仅使用隔离库。浏览器测试需要先按本地开发说明启动隔离 API 和预览。
默认跳过已保存付费练习复用场景；只有已执行有预算的五题型联调并保留私有 fixture 后，
才设置 `AI_LEARN_TEXT_REUSE=1`。复用也不新增模型调用。

2026-09-15：两个 Chromium 场景通过，包含真实 API/MySQL、图谱持久化、中文 SVG 文本、
错题筛选、题目深链接、原文跳转、刷新、失败重试、恶意标签净化及 320/390/1440 宽度。
首轮截图发现实体编码未解码问题，添加 SVG 文本断言后修复，而非只判断图片非空。
共享异步依赖去重后异步 JS 约 4 MiB；H5 入口 gzip 120870 字节，weapp 主包 1033161 字节。
证据见 `evidence/study-maps-ui.json`、`evidence/study-maps-build-size.json` 及截图 37-38。
这些是本地结果，尚不表示公网部署或小程序发布。

## 参考与许可

- [Mermaid 安全级别](https://mermaid.js.org/config/schema-docs/config-properties-securitylevel.html)、
  [渲染 API](https://mermaid.js.org/config/usage)，MIT。
- [DOMPurify](https://github.com/cure53/DOMPurify)，Apache-2.0 OR MPL-2.0。
- [Dagre](https://github.com/dagrejs/dagre)，MIT，用于小程序布局而非自研图布局算法。
- [Taro 多端文件](https://docs.taro.zone/docs/envs/)、
  [节点获取](https://docs.taro.zone/docs/ref)，保留现有 Taro 4.1.11。

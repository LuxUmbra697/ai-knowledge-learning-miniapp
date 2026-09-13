# RAG 评测 / Retrieval Evaluation

## 数据与边界

初版 `eval/rag/dataset-v1.json` 有 **104 条样例、56 个片段、8 个主题**。所有材料由 AI 辅助编写，标签由明确的构造规则生成，不是真实用户记录，也不是人工正确率标注。引用了故意不一致的课堂规则和恶意工具指令，用于检查冲突与权限边界；不应执行其中的指令。

按主题和文档拆分：训练区 4 个主题，验证区 2 个，测试区 2 个。这里的“训练区”是预留划分，M2 没有训练模型。不同区仍共享问句模板，数据也较短，不能据此证明开放域泛化能力。单文档、多文档、跨章节、中文同义问句、无答案、冲突、提示注入和越权请求均有明确分类。

## 可复现命令

从仓库根目录、安装后端依赖的 Python 环境运行：

```sh
python scripts/build_rag_dataset.py
python scripts/evaluate_rag.py
```

第二步使用已提交的合成材料向量缓存和**真实本地 Chroma**，不读取真实 dotenv，不请求模型供应商，不连接业务数据库。缓存校验数据 SHA-256，Embedding 为实际接入的 `text-embedding-v4`，1024 维。评测使用真实 Chroma 的用户 collection 与检索前 scope 过滤，再执行与应用共用的 BM25/RRF/词项重排代码。

需要重新获取向量时，下面的命令会读取后端安全配置并产生少量供应商调用，不能放入默认 CI：

```sh
python scripts/embed_rag_dataset.py --confirm-max-16-batches
```

上限是 160 条唯一文本、30000 字符、16 个批次；SDK 不重试。已完成批次按文本 SHA-256 缓存。初次实测为 **15 个请求、144 条唯一文本、2437 tokens**。修改检索范围而未修改文本时复用缓存，不重新计费。货币账单未查询，不能将费用写为零。

## 初版结果

参数：随机种子 697（数据构造固定顺序），每路候选 20，RRF 常数 60，Top-K=4。当前 reranker 是最多处理 20 个候选的确定性词项覆盖规则，**不是神经重排模型、微调或训练成果**。

| 配置 | 全部有答案样例 Recall@4 | MRR | nDCG@4 |
| --- | ---: | ---: | ---: |
| dense-only | 1.000000 | 0.950000 | 0.955961 |
| BM25 + dense / RRF | 1.000000 | 0.929167 | 0.939980 |
| 混合 + 词项重排 | 1.000000 | 0.929167 | 0.936970 |

精确结果以 [results-v1.json](../eval/rag/results-v1.json) 为准，每条结果在 [raw-v1.jsonl](../eval/rag/raw-v1.jsonl)。各主题区分别列出指标，**没有实测提升，不声称混合或重排优于 dense**。高 Recall 很大程度来自较小候选范围，不能当成真实用户问答准确率。

每种配置均有 16 个权限负例在检索前被拒绝；其他候选均属于已选文档及用户范围。8 个无答案问题的空召回率都是 **0**：dense 总会返回近邻，这不是答案是否存在的分类器。冲突和提示注入的标签仅在本脚本衡量候选命中，不冒充模型行为评测。

缓存检索延迟包含 Chroma 查询与排名，不包含在线 Embedding 网络延迟。P50/P95 和完整运行条件保存在结果文件中，不用于宣传线上响应时间或并发吞吐。

## 回答与引用验证

实际浏览器 → API → MySQL/Chroma → 供应商 → 引用页面已执行。公开证据为 [索引闭环](evidence/m2-live-index.json) 和 [真实回答](evidence/m2-live-answer.json)。回答层验证引用 ID、文档版本和逐字摘录；生成后重新检查引用是否仍可访问。无证据、供应商失败、格式失败、资料变化和冲突使用不同状态。

一次通过的真实回答测得 1 个模型请求、553 tokens、3 条陈述及 3 个有效原文引用，约 2.02 秒；仅是一份短合成材料的单次测量。浏览器迭代中另外两次真实回答成功，但测试因 Taro 隐藏页面/导航标题造成的定位器歧义未完成，修正定位器后重新运行，没有将失败运行计为通过。

精确摘录匹配证明“引用可以回到这个片段”，**不能证明整条解释与原文语义蕴含关系**。当前没有人工正确率，也没有 LLM judge 评分。后续需要更长、更具歧义且经独立审核的数据，以及单独的回答语义评测。

## Sources and Reproduction Notes

The benchmark is synthetic and rule-labeled, split by document/topic. Cached embeddings were acquired from the configured provider; evaluation performs no paid calls. RRF combines ranks rather than incomparable raw scores. BM25 uses Chinese character bigrams and Latin tokens. The optional lexical reranker is a bounded rule, not a trained cross-encoder. Exact quote validation is not semantic entailment evaluation.

The measurements do not show an improvement from hybrid retrieval. Preserve the raw observations before changing models or ranking parameters; tuning must use the training/validation partitions, not the held-out topics.

## 方法来源

- RRF 排名融合公式来源：[Cormack、Clarke、Büttcher，SIGIR 2009](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf)。该论文结果不能替代本项目自己的测量。
- BM25 实现使用 [rank_bm25](https://github.com/dorianbrown/rank_bm25/blob/master/README.md)；中文预处理由本项目补充。
- Chroma 的查询前元数据约束使用 [metadata filtering](https://docs.trychroma.com/docs/querying-collections/metadata-filtering)，用户和 SQL 文档归属检查仍由本项目服务端负责。

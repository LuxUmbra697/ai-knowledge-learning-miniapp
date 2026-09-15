# 离线算法实验：BKT 拟合与概率校准

本实验已经实际执行，不是待实现方案。它验证从数据划分、参数拟合、验证集校准到独立测试
和原始预测保存的工程流程。**数据完全合成，没有真实学生，没有证明记忆保持或学习效果改善，
也没有给线上账户训练个人参数。** 系统中的 FSRS 调度与本实验的 BKT 作答概率预测职责不同。

## 数据与划分

- 版本 `synthetic-bkt-v1`，种子 20260915；NumPy 2.5.3，Python 3.13.9。
- 800 个合成学习者，每人 30 次二值作答，共 24000 次观察。模拟器的初始掌握、学习转移、
  猜测、失误概率分别为 0.08、0.06、0.18、0.22。单一知识点，无遗忘与题目难度。
- 按学习者 ID 划分训练 480 人、验证 160 人、测试 160 人，比例 60/20/20。同一个人的
  记录不跨集合。每次预测只使用其之前的答案，不读取当前或未来标签。
- [完整数据](../eval/learning/dataset-v1.jsonl) 保存观察和划分；
  [结果清单](../eval/learning/results-v1.json) 保存数据 SHA-256、环境、参数和运行时间。
  固定 LF 换行，避免 Windows 文本写入导致清单哈希与文件字节不一致。

## 实际计算

1. 常数基线只使用训练集整体正确率。默认 BKT 使用应用现有 `.2/.12/.25/.1` 参数。
2. 训练集上最小化一步前向预测的负对数似然：256 个有界随机候选，加最多 160 次逐坐标
   粗到细搜索。初始候选包含默认参数；保存每次最佳值更新，没有调用外部模型或 GPU。
3. 验证集上搜索 `sigmoid(logit(p)/T + b)` 的温度与偏置，选取验证损失最低组合。
   这是两参数 logit 校准，不冒充神经网络训练，也不是仅含温度的原版 temperature scaling。
4. 锁定参数后一次性计算测试集 Log Loss、Brier、10 个等宽概率箱的 ECE，均为越低越好。
   按学习者做 200 次配对 bootstrap，避免把同一学习者的相关作答当独立样本抽取。

核心实现 `backend/app/learning/bkt_experiment.py` 与运行时 `knowledge_tracing.py` 的更新公式
经逐步对照测试；实验模块不被 API 导入。运行时默认值没有被实验结果覆盖。

## 2026-09-15 实测

| 方法 | 测试 Log Loss | 测试 Brier | 测试 ECE-10 |
| --- | ---: | ---: | ---: |
| 训练集常数正确率 | 0.691309 | 0.249081 | 0.009167 |
| 默认 BKT | 0.588845 | 0.195521 | 0.106379 |
| 拟合 BKT | 0.552060 | 0.183290 | 0.011719 |
| 拟合 BKT + 校准 | 0.551767 | 0.183190 | 0.008572 |

拟合参数：initial 0.089586、learn 0.057584、guess 0.175888、slip 0.220984。
验证集选择 T=1.0、b=0.05。相对默认 BKT 的测试 Brier 差值 -0.012332；学习者配对
bootstrap 95% 区间 [-0.015314, -0.009402]。该区间仅描述本模拟分布的抽样不确定性。

常数基线的 ECE 也很低，但 Brier/Log Loss 明显较差：**校准好不等于预测有用**，不能只挑
ECE 写宣传结论。模拟器与拟合器同属 BKT 模型族，本实验天然偏向 BKT；换成真实分布、
多知识点或存在遗忘的数据，收益可能消失。未宣称 LoRA、蒸馏、大模型微调或线上 A/B 成绩。

完整拟合与评估在本机约 0.5 秒，零外部调用；这不是服务器吞吐量测试。
[逐步原始测试预测](../eval/learning/predictions-v1.csv) 可复算每一项指标。
同环境独立复跑的完整数据和预测文件 SHA-256 相同。

## 复现命令

仓库根目录，Windows PowerShell：

```powershell
backend/venv/Scripts/python.exe -m pip install -r backend/requirements-experiments.txt
backend/venv/Scripts/python.exe scripts/experiment_bkt.py
backend/venv/Scripts/python.exe scripts/experiment_bkt.py --output .local/bkt-reproduction
Get-FileHash eval/learning/dataset-v1.jsonl, .local/bkt-reproduction/dataset-v1.jsonl
backend/venv/Scripts/python.exe scripts/test_offline.py -q backend/tests/test_bkt_experiment.py
```

Linux/macOS 使用 `backend/venv/bin/python` 替代解释器路径，使用
`sha256sum eval/learning/dataset-v1.jsonl .local/bkt-reproduction/dataset-v1.jsonl` 校验。
实验不加载 `.env`，不连接数据库、不改用户状态。默认输出是公开的合成实验目录；可用
`--output` 指向独立目录重跑。不同 NumPy/平台浮点实现可能引起尾数差异，应比较数值容差。

## 方法来源

- [Corbett 与 Anderson 的 Knowledge Tracing 原文](https://perso.liris.cnrs.fr/pierre-antoine.champin/2014/m2iade-ia2/_static/893CorbettAnderson1995.pdf)。
- [Guo 等：On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a)，
  作为概率校准及 ECE 方法参考；其论文的真实数据结果不是本项目的结果。
- 数值计算使用 BSD-3-Clause 许可的 [NumPy](https://numpy.org/)。合成数据由本仓库脚本生成，
  未使用两个参考项目的数据或任何私人学习记录。

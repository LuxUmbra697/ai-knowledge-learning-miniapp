const stages: Record<string, string> = {
  staging: '等待上传完成', queued: '等待处理', preparing: '准备处理', recovering: '恢复检查点',
  parsing: '解析资料', parsed: '解析完成', publishing: '保存索引', query_embedding: '检索相关片段',
  retrieval: '整理来源证据', answer: '生成回答', validation: '校验引用', completed: '已完成', failed: '未完成', cancelled: '已取消',
  report_input_validated: '核对作答记录', report: '生成学习报告', report_validated: '报告校验完成',
}

export function taskPhase(stage: string) {
  return stage.startsWith('embedding_') ? '建立向量索引' : stages[stage] || '处理中'
}

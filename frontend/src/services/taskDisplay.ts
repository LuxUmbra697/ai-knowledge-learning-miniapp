const stages: Record<string, string> = {
  companion_context: '整理伙伴记忆', companion_chat: '伙伴正在回应', companion_validated: '保存本轮对话',
  staging: '等待上传完成', queued: '等待处理', preparing: '准备处理', recovering: '恢复检查点',
  parsing: '解析资料', parsed: '解析完成', publishing: '保存索引', query_embedding: '检索相关片段',
  retrieval: '整理来源证据', answer: '生成回答', validation: '校验引用', completed: '已完成', failed: '未完成', cancelled: '已取消',
  report_input_validated: '核对作答记录', report: '生成学习报告', report_validated: '报告校验完成',
  quiz_sources: '练习材料已就绪', quiz: '生成练习题目', quiz_validated: '练习校验完成',
  public_search: '获取网页参考',
  tutor_identify: '恢复辅导上下文', tutor_learning: '读取学习状态', tutor_review: '查看到期复习', tutor_evidence: '整理辅导证据', tutor_coach: '生成本轮提示', tutor_validated: '校验辅导引用',
  image_1: '生成第 1 张配图', image_2: '生成第 2 张配图', image_saved_1: '保存第 1 张配图', image_saved_2: '保存第 2 张配图',
  written_grade: '逐项评阅问答',
  written_grade_validated: '评阅依据校验完成',
}

export function taskPhase(stage: string) {
  return stage.startsWith('embedding_') ? '建立向量索引' : stage.startsWith('quiz_batch_') ? `生成第 ${stage.slice(11)} 批题目` : stages[stage] || '处理中'
}

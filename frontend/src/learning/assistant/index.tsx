import { requireLogin } from '../../services/access'
import { useEffect, useRef, useState } from 'react'
import { View, Text, Button, Textarea, Checkbox, CheckboxGroup, Label } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter } from '@tarojs/taro'
import { StudioShell, Notice, Empty, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'
import { useStudio } from '../../components/StudioProvider'
import { askKnowledge, cancelLearningTask, Evidence, getCachedUser, getKnowledgeDocuments, getLearningTask, getToken, GroundedAnswer, KnowledgeDocumentItem, LearningTask, waitForLogin } from '../../services/api'
import { PollControl, pollUntil } from '../../services/polling'
import { taskPhase } from '../../services/taskDisplay'
import { restorableAnswer } from '../../services/answerSession'

const statuses: Record<GroundedAnswer['status'], string> = {
  answered: '来自学习材料的回答', no_evidence: '没有找到支持证据', conflict: '材料中存在不同说法',
  retrieval_failed: '暂时无法检索材料，请稍后重试', provider_failed: '回答服务暂不可用，请稍后重试',
  validation_failed: '回答未通过引用校验，请调整问题后重试', stale_evidence: '材料已变更，请重新提问', timeout: '本次回答超时，请稍后重试',
}
export function openEvidence(item: Evidence) {
  Taro.navigateTo({ url: `/learning/document/index?docId=${encodeURIComponent(item.doc_id)}&chunkId=${encodeURIComponent(item.chunk_id)}&revision=${item.revision}` })
}
export default function AssistantPage() {
  const router = useRouter()
  const appearance = useStudio()
  const [documents, setDocuments] = useState<KnowledgeDocumentItem[]>([]), [selected, setSelected] = useState<string[]>([])
  const [query, setQuery] = useState(''), [submitted, setSubmitted] = useState(''), [answer, setAnswer] = useState<GroundedAnswer | null>(null)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true)
  const [task, setTask] = useState<LearningTask | null>(null)
  const live = useRef(true), locked = useRef(false), control = useRef<PollControl>(), initialized = useRef(false)
  const storageKey = () => `ai-learn:v1:answer:${getCachedUser()?.id}`
  const monitor = async (taskId: string, current: PollControl) => {
    const completed = await pollUntil(() => getLearningTask(taskId, current), status => {
      if (live.current) { setTask(status); if (!submitted) setSubmitted(status.title || '') }
      if (status.status === 'failed' || status.status === 'cancelled') throw new Error(status.error_message || '任务已取消')
      return status.status === 'completed'
    }, { control: current, intervalMs: 2000, maxAttempts: 100 })
    if (live.current) { setAnswer(completed.result); setSubmitted(completed.result.query || completed.title || '') }
  }
  const resume = async (taskId: string) => {
    control.current?.cancel(); const current = new PollControl(); control.current = current
    locked.current = true; setBusy(true)
    try { await monitor(taskId, current) }
    catch (reason) { if (live.current && !current.cancelled) setError(reason instanceof Error ? reason.message : '任务读取失败') }
    finally { if (control.current === current) { locked.current = false; if (live.current) setBusy(false) } }
  }
  useEffect(() => {
    if (answer) Taro.nextTick(() => { if (live.current) Taro.pageScrollTo({ selector: '#grounded-response', duration: appearance.reducedMotion ? 0 : 200 }) })
  }, [answer, appearance.reducedMotion])
  const load = async () => {
    await waitForLogin()
    if (!getToken()) { await requireLogin(undefined, true); return }
    try {
      const result = await getKnowledgeDocuments()
      if (!live.current) return
      const ready = result.items.filter(doc => doc.status === 'ready' && !doc.needs_reindex)
      setDocuments(ready)
      if (!initialized.current) setSelected(ready.filter(doc => doc.doc_id === router.params.docId).map(doc => doc.doc_id))
      else setSelected(previous => previous.filter(id => ready.some(doc => doc.doc_id === id)))
      initialized.current = true
      setError('')
      const saved = Taro.getStorageSync(storageKey())
      const taskId = restorableAnswer(router.params, saved)
      if (taskId && !locked.current) {
        if (saved?.taskId === taskId) { setQuery(saved.query); setSubmitted(saved.query); setSelected(saved.docIds.filter(id => ready.some(doc => doc.doc_id === id))) }
        resume(taskId)
      }
    } catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '材料读取失败') }
    finally { if (live.current) setLoading(false) }
  }
  useDidShow(() => { live.current = true; locked.current = false; setBusy(false); load() })
  useDidHide(() => { live.current = false; control.current?.cancel(); locked.current = false })
  const ask = async () => {
    if (locked.current) return
    if (!query.trim() || !selected.length) { setError('请选择材料并填写问题'); return }
    locked.current = true; setBusy(true); setError(''); setAnswer(null); setTask(null); setSubmitted(query.trim())
    const current = new PollControl(); control.current = current
    const previous = Taro.getStorageSync(storageKey())
    const saved = { query: query.trim(), docIds: [...selected].sort(), key: `ask_${Date.now()}_${Math.random().toString(36).slice(2)}`, taskId: '' }
    if (previous && !previous.taskId && previous.query === saved.query && JSON.stringify(previous.docIds) === JSON.stringify(saved.docIds)) saved.key = previous.key
    Taro.setStorageSync(storageKey(), saved)
    try {
      const response = await askKnowledge(saved.query, saved.docIds, current, saved.key)
      saved.taskId = response.task_id; Taro.setStorageSync(storageKey(), saved)
      await monitor(response.task_id, current)
    } catch (reason) { if (live.current && !current.cancelled) setError(reason instanceof Error ? reason.message : '回答失败') }
    finally { if (control.current === current) { locked.current = false; if (live.current) setBusy(false) } }
  }
  const cancel = async () => {
    if (!task) return
    const confirmation = await Taro.showModal({ title: '取消回答', content: '已开始的模型调用可能仍会产生费用。是否取消本次任务？' })
    if (!confirmation.confirm) return
    try { await cancelLearningTask(task.task_id); control.current?.cancel(); locked.current = false; setBusy(false); setError('任务已取消') }
    catch (reason) { setError(reason instanceof Error ? reason.message : '取消失败') }
  }
  return <StudioShell active='assistant' title='证据学习助手' subtitle='读懂一段知识，也找到它的来处。'>
    <View className='section-heading'><Text className='tag'>知识问答</Text><Button className='secondary-button' onClick={() => Taro.navigateTo({ url: '/learning/tutor/index' })}><Icon name='chat' size={16} />逐步辅导</Button></View>
    <View className='assistant-layout'>
      <View className='source-column'><Text className='section-title'>本次学习材料</Text>
        {!documents.length && <Empty title={loading ? '正在读取材料' : '暂无已就绪材料'} text='先到知识书架添加一份笔记。' />}
        <CheckboxGroup onChange={event => setSelected(event.detail.value)}>
          {documents.map(doc => <View className='source-choice' key={doc.doc_id}><Checkbox id={`source-${doc.doc_id}`} value={doc.doc_id} checked={selected.includes(doc.doc_id)} disabled={busy} /><Label for={`source-${doc.doc_id}`} className='row-copy'><Text className='row-title'>{doc.file_name}</Text><Text className='muted'>{doc.chunk_count} 个片段 · 版本 {doc.revision || 1}</Text></Label></View>)}
        </CheckboxGroup>
        <Button className='text-button' onClick={() => navigate('/pages/knowledge/index')}><Icon name='library' size={16} />管理学习材料</Button>
      </View>
      <View className='conversation-column'>
        <Text className='field-label'>我的问题</Text><Textarea className='studio-textarea' placeholder='例如：学习率过大时，为什么会发生震荡？' maxlength={1000} value={query} disabled={busy} onInput={event => setQuery(event.detail.value)} />
        <View className='ask-actions'><Text className='muted'>已选择 {selected.length} 篇材料</Text><Button className='primary-button' disabled={busy || !documents.length} onClick={ask}><Icon name='chat' size={18} />{busy ? (task ? taskPhase(task.stage) : '提交问题') : '提问'}</Button></View>
        {task && <View className='document-actions'><Button className='text-button' onClick={() => Taro.navigateTo({ url: '/learning/tasks/index' })}><Icon name='clock' size={16} />任务记录</Button>{busy && <Button className='text-button' onClick={cancel}><Icon name='close' size={16} />取消任务</Button>}</View>}
        {error && <Notice message={error} />}
        {answer && <View className='grounded-response' id='grounded-response'><Text className='submitted-question'>{submitted}</Text><Text className='section-title'>{statuses[answer.status]}</Text>
          {answer.retrieval_status === 'degraded' && <Notice message='向量检索暂不可用，本次仅使用关键词召回的材料。' />}
          {answer.claims.map((claim, index) => <View className='claim-block' key={index}><Text className='claim-text' selectable>{claim.text}</Text>
            <View className='citation-links'>{claim.citations.map((citation, citationIndex) => {
              const item = answer.evidence.find(source => source.id === citation.evidence_id)
              return item && <Button key={citationIndex} className='text-button citation-link' onClick={() => openEvidence(item)}><Icon name='book' size={15} /><Text>{item.file_name}{item.page ? ` · 第 ${item.page} 页` : item.section ? ` · ${item.section}` : ''}</Text></Button>
            })}</View></View>)}
          {!!answer.evidence.length && <View className='evidence-summary'><Text className='tiny-label'>本次参考材料</Text>{answer.evidence.map(item => <View className='evidence-row' key={item.id}><Text className='tag'>{item.id}</Text><View className='row-copy'><Button className='text-button source-title' onClick={() => openEvidence(item)}>{item.file_name}</Button><Text className='muted source-excerpt'>{item.content.slice(0, 160)}{item.content.length > 160 ? '…' : ''}</Text></View></View>)}</View>}
        </View>}
      </View>
    </View>
  </StudioShell>
}

import { useRef, useState } from 'react'
import { View, Text, Textarea, Button, Checkbox, CheckboxGroup, Label } from '@tarojs/components'
import Taro, { useDidShow, useDidHide, useRouter } from '@tarojs/taro'
import { StudioShell, Notice, Empty, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'
import { getCachedUser, getKnowledgeDocuments, getLearningTask, cancelLearningTask, KnowledgeDocumentItem, LearningTask, waitForLogin, getToken, updateReviewCard } from '../../services/api'
import { createTutor, deleteTutor, getTutorContext, getTutorSession, listTutorSessions, sendTutorTurn, confirmTutorPractice, TutorConfig, TutorDraft, TutorEvidence, TutorResponse, TutorSession } from '../../services/tutor'
import { tutorDraft } from '../../services/tutorSession'
import { PollControl, pollUntil } from '../../services/polling'
import { taskPhase } from '../../services/taskDisplay'

const reasons: Record<string, string> = { concept_confusion: '概念混淆', missing_prerequisite: '前置知识待补充', careless: '可能疏忽', reasoning_gap: '推理步骤待补充', unknown: '暂不能判断' }
const newKey = () => `tutor_${Date.now()}_${Math.random().toString(36).slice(2)}`

export default function TutorPage() {
  const router = useRouter()
  const [documents, setDocuments] = useState<KnowledgeDocumentItem[]>([]), [selected, setSelected] = useState<string[]>([])
  const [sessions, setSessions] = useState<TutorSession[]>([]), [session, setSession] = useState<TutorSession | null>(null)
  const [goal, setGoal] = useState(''), [message, setMessage] = useState(''), [cardId, setCardId] = useState(router.params.cardId || '')
  const [task, setTask] = useState<LearningTask | null>(null), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true)
  const live = useRef(true), lock = useRef(false), control = useRef<PollControl>()
  const storageKey = () => `ai-learn:v1:tutor:${getCachedUser()?.id}`
  const save = (draft: TutorDraft) => Taro.setStorageSync(storageKey(), draft)
  const showFailure = (reason: unknown, current?: PollControl) => { if (live.current && !current?.cancelled) setError(reason instanceof Error ? reason.message : '辅导暂不可用，请重试') }

  const monitor = async (id: string, current: PollControl) => {
    const completed = await pollUntil(() => getLearningTask(id, current), value => {
      if (live.current && !current.cancelled) setTask(value)
      if (['failed', 'cancelled'].includes(value.status)) {
        const draft = tutorDraft(Taro.getStorageSync(storageKey()))
        if (draft?.taskId === id) save({ config: draft.config, createKey: draft.createKey, sessionId: draft.sessionId })
        throw new Error(value.error_message || '本轮辅导已取消，未发布新提示')
      }
      return value.status === 'completed'
    }, { control: current, intervalMs: 2000, maxAttempts: 100 })
    const result = await getTutorSession(completed.result.session_id, current)
    if (!live.current || current.cancelled) return
    setSession(result); setMessage('')
    const draft = tutorDraft(Taro.getStorageSync(storageKey()))
    if (draft?.sessionId === result.session_id) save({ config: draft.config, createKey: draft.createKey, sessionId: result.session_id })
    setSessions((await listTutorSessions(current)).items)
  }

  const open = async (id: string, current: PollControl) => {
    const result = await getTutorSession(id, current)
    if (!live.current || current.cancelled) return
    setSession(result); setGoal(result.goal); setSelected(result.doc_ids); setCardId(result.card_id || '')
    const draft = tutorDraft(Taro.getStorageSync(storageKey()))
    if (draft?.sessionId === id && draft.version === result.version && draft.message) setMessage(draft.message)
    if (result.pending_task_id) {
      const status = await getLearningTask(result.pending_task_id, current)
      if (live.current) setTask(status)
      if (!['completed', 'failed', 'cancelled'].includes(status.status)) {
        lock.current = true; setBusy(true)
        await monitor(result.pending_task_id, current)
      } else if (status.status !== 'completed') {
        if (draft?.sessionId === id) save({ config: draft.config, createKey: draft.createKey, sessionId: id })
        setError(status.error_message || '本轮辅导已取消，未发布新提示')
      }
    }
  }

  const load = async () => {
    control.current?.cancel(); const current = new PollControl(); control.current = current
    try {
      await waitForLogin()
      if (!getToken()) { navigate('/pages/login/index'); return }
      const docs = await getKnowledgeDocuments()
      const list = await listTutorSessions(current)
      if (!live.current || current.cancelled) return
      setDocuments(docs.items.filter(doc => doc.status === 'ready' && !doc.needs_reindex)); setSessions(list.items); setError('')
      let card = router.params.cardId || ''
      if (router.params.quizId && router.params.questionId) card = (await getTutorContext(router.params.quizId, router.params.questionId, current)).card_id
      if (card) { setCardId(card); setGoal('梳理这道错题中的理解偏差') }
      const draft = tutorDraft(Taro.getStorageSync(storageKey()))
      const compatible = draft && (card ? draft.config.card_id === card : !draft.config.card_id)
      const id = router.params.sessionId || (compatible ? draft.sessionId : '')
      if (id) await open(id, current)
      else if (compatible) { setGoal(draft.config.goal); setSelected(draft.config.doc_ids) }
      else if (router.params.docId) setSelected([router.params.docId])
    } catch (reason) { showFailure(reason, current) }
    finally { if (control.current === current) { lock.current = false; if (live.current) { setBusy(false); setLoading(false) } } }
  }
  useDidShow(() => { live.current = true; load() })
  useDidHide(() => { live.current = false; control.current?.cancel() })

  const send = async () => {
    if (lock.current) return
    const config: TutorConfig = session ? { goal: session.goal, mode: session.mode, doc_ids: session.mode === 'diagnosis' ? [] : session.doc_ids, ...(session.card_id ? { card_id: session.card_id } : {}) }
      : { goal: goal.trim(), mode: cardId ? 'diagnosis' : 'socratic', doc_ids: cardId ? [] : [...selected].sort(), ...(cardId ? { card_id: cardId } : {}) }
    if (!config.goal || (config.mode === 'socratic' && (!config.doc_ids.length || config.doc_ids.length > 3)) || (session && !message.trim())) { setError('填写学习目标，并选择 1 至 3 篇材料；继续时填写你的回应。'); return }
    lock.current = true; setBusy(true); setError(''); setNotice(''); control.current?.cancel()
    const current = new PollControl(); control.current = current
    try {
      const previous = tutorDraft(Taro.getStorageSync(storageKey()))
      let draft: TutorDraft = previous && JSON.stringify(previous.config) === JSON.stringify(config) && (!session || previous.sessionId === session.session_id)
        ? previous : { config, createKey: newKey(), ...(session ? { sessionId: session.session_id } : {}) }
      save(draft)
      let target = session
      if (!target) {
        target = draft.sessionId ? await getTutorSession(draft.sessionId, current) : await createTutor(config, draft.createKey, current)
        draft = { ...draft, sessionId: target.session_id }; save(draft)
        if (live.current) setSession(target)
      }
      const text = session ? message.trim() : '请从一个小问题开始帮助我理解。'
      if (!draft.turnKey || draft.version !== target.version || draft.message !== text) draft = { ...draft, turnKey: newKey(), version: target.version, message: text, taskId: undefined }
      save(draft)
      const created = await sendTutorTurn(target.session_id, target.version, text, draft.turnKey!, current)
      draft = { ...draft, taskId: created.task_id }; save(draft)
      await monitor(created.task_id, current)
    } catch (reason) { showFailure(reason, current) }
    finally { if (control.current === current) { lock.current = false; if (live.current) setBusy(false) } }
  }

  const cancel = async () => {
    if (!task) return
    if (!(await Taro.showModal({ title: '取消本轮辅导', content: '已经开始的模型调用可能产生费用；之前的对话会保留。' })).confirm) return
    try { await cancelLearningTask(task.task_id); control.current?.cancel(); lock.current = false; setBusy(false); await load() }
    catch (reason) { showFailure(reason) }
  }
  const remove = async (item: TutorSession) => {
    if (!(await Taro.showModal({ title: '删除辅导会话', content: '删除此会话的对话记录？不会删除学习材料、错题或复习计划。' })).confirm) return
    try {
      await deleteTutor(item.session_id)
      if (tutorDraft(Taro.getStorageSync(storageKey()))?.sessionId === item.session_id) Taro.removeStorageSync(storageKey())
      if (session?.session_id === item.session_id) { Taro.redirectTo({ url: '/learning/tutor/index' }); return }
      setSessions((await listTutorSessions()).items)
    } catch (reason) { showFailure(reason) }
  }
  const evidence = (item: TutorEvidence) => Taro.navigateTo({ url: item.source_type === 'private_document'
    ? `/learning/document/index?docId=${encodeURIComponent(item.doc_id)}&chunkId=${encodeURIComponent(item.chunk_id)}&revision=${item.revision}`
    : `/pages/quiz/index?quizId=${encodeURIComponent(item.quiz_id)}&questionId=${encodeURIComponent(item.question_id)}` })
  const confirmDiagnosis = async (value: string) => {
    if (!session?.card_id || value === 'unknown') return
    if (!(await Taro.showModal({ title: '确认错因标记', content: `将“${reasons[value]}”记录为你确认的错因？这不会改变判分和复习日期。` })).confirm) return
    try { await updateReviewCard(session.card_id, { diagnosis: value }); if (live.current) { setSession(previous => previous && ({ ...previous, confirmed_diagnosis: value })); setNotice('已记录为你确认的错因，原判分和复习计划未改变。') } }
    catch (reason) { showFailure(reason) }
  }
  const practice = async (response: TutorResponse, turn: number) => {
    if (lock.current || !response.practice || !session) return
    const proposal = response.practice
    if (!(await Taro.showModal({ title: '生成建议练习', content: `创建 ${proposal.count} 道“${proposal.focus}”练习？这会调用付费模型。` })).confirm) return
    lock.current = true; setBusy(true)
    try {
      const result = await confirmTutorPractice(session.session_id, turn, session.version)
      if (live.current) Taro.navigateTo({ url: `/pages/quiz/index?taskId=${encodeURIComponent(result.task_id)}` })
    } catch (reason) { showFailure(reason) }
    finally { lock.current = false; if (live.current) setBusy(false) }
  }

  return <StudioShell active='assistant' focus title={cardId || session?.mode === 'diagnosis' ? '错题辅导' : '逐步辅导'} subtitle='带着自己的思考，往前走一小步。'>
    <View className='section-heading'><Button className='text-button' onClick={() => Taro.navigateBack()}><Icon name='arrow' size={16} />返回</Button><Button className='secondary-button' disabled={busy} onClick={() => { Taro.removeStorageSync(storageKey()); Taro.redirectTo({ url: '/learning/tutor/index' }) }}><Icon name='add' size={16} />新会话</Button></View>
    {error && <Notice message={error} retry={load} />}{notice && <Text className='tutor-notice'>{notice}</Text>}
    {loading && <Text className='muted'>正在读取辅导记录</Text>}
    {!loading && !session && <View className='tutor-setup'>
      <Text className='field-label'>学习目标</Text><Textarea className='studio-textarea' maxlength={1000} value={goal} disabled={busy} onInput={event => setGoal(event.detail.value)} placeholder='例如：我想理解为什么学习率过大会发生震荡' />
      {cardId ? <Text className='muted'>基于这道错题的实际作答与已保存解析</Text> : <>
        <Text className='field-label'>本次材料 · 最多 3 篇</Text>
        {!documents.length && <Empty title='暂无已就绪材料' text='先在知识书架添加学习材料。' />}
        <CheckboxGroup onChange={event => setSelected(event.detail.value)}>{documents.map(doc => <View className='source-choice' key={doc.doc_id}><Checkbox id={`tutor-${doc.doc_id}`} value={doc.doc_id} checked={selected.includes(doc.doc_id)} disabled={busy || (!selected.includes(doc.doc_id) && selected.length >= 3)} /><Label for={`tutor-${doc.doc_id}`} className='row-title'>{doc.file_name}</Label></View>)}</CheckboxGroup>
      </>}
      <Button className='primary-button' disabled={busy || !goal.trim() || (!cardId && !selected.length)} onClick={send}><Icon name='chat' size={18} />{busy ? '正在开始' : '开始辅导'}</Button>
    </View>}
    {session && <View className='tutor-dialogue'>
      <View className='section-heading'><Text className='section-title'>{session.goal}</Text><Text className='tag'>{session.version} / {session.max_turns} 轮</Text></View>
      {(session.turns || []).map(turn => <View className='tutor-turn' key={turn.number}>
        <Text className='tiny-label'>第 {turn.number} 轮 · 我的回应</Text><Text className='tutor-student' selectable>{turn.message}</Text>
        <Text className='tutor-hint' selectable>{turn.response.hint}</Text><Text className='tutor-question' selectable>{turn.response.question}</Text>
        {turn.response.tool_summary && <Text className='tiny-label'>参考 {turn.response.tool_summary.evidence_count} 个资料片段 · 读取 {turn.response.tool_summary.learning_concepts} 个学习标签 · 到期复习样本 {turn.response.tool_summary.due_review_sample} 道</Text>}
        {turn.response.retrieval_status === 'degraded' && <Text className='muted'>本轮使用关键词召回，向量检索暂不可用。</Text>}
        {turn.response.citations.map((citation, i) => { const item = turn.response.evidence.find(source => source.id === citation.evidence_id); return item && <View className='tutor-citation' key={i}><Text selectable>{citation.quote}</Text><Button className='text-button' onClick={() => evidence(item)}><Icon name='book' size={16} />{item.file_name}</Button>{item.source_type === 'stored_practice' && <Text className='muted'>已生成题目的参考解析，未经独立事实核验</Text>}</View> })}
        {turn.response.diagnosis && <View className='document-actions'><Text className='muted'>模型建议 · {reasons[turn.response.diagnosis]} · {session.confirmed_diagnosis === turn.response.diagnosis ? '你已确认此标记' : '待你确认'}</Text>{turn.response.diagnosis !== 'unknown' && session.confirmed_diagnosis !== turn.response.diagnosis && <Button className='text-button' onClick={() => confirmDiagnosis(turn.response.diagnosis!)}>确认错因</Button>}</View>}
        {turn.response.practice && <Button className='secondary-button' disabled={busy} onClick={() => practice(turn.response, turn.number)}><Icon name='review' size={16} />建议练习 · {turn.response.practice.count} 题</Button>}
      </View>)}
      {session.version < session.max_turns ? <View className='tutor-composer'><Text className='field-label'>我的回应</Text><Textarea className='studio-textarea' value={message} maxlength={1000} disabled={busy} onInput={event => setMessage(event.detail.value)} placeholder='说说你的想法，或者你仍不理解的部分' /><Button className='primary-button' disabled={busy || !message.trim()} onClick={send}>继续这一轮<Icon name='arrow' size={16} /></Button></View> : <Text className='tutor-notice'>本次辅导已完成，可以回到材料、开始练习或新建会话。</Text>}
    </View>}
    {task && <View className='document-actions'><Text className='muted'>{busy ? taskPhase(task.stage) : '本轮调用'} · {task.trace.model_calls} 次外部调用</Text>{busy && <Button className='text-button' onClick={cancel}><Icon name='close' size={16} />取消本轮</Button>}<Button className='text-button' onClick={() => Taro.navigateTo({ url: '/learning/tasks/index' })}>执行记录</Button></View>}
    {!!sessions.length && <View className='tutor-history'><Text className='section-title'>辅导记录</Text>{sessions.map(item => <View className='tutor-history-row' key={item.session_id}><Button className='text-button row-copy' disabled={busy} onClick={() => Taro.redirectTo({ url: `/learning/tutor/index?sessionId=${encodeURIComponent(item.session_id)}` })}>{item.goal}</Button><Text className='muted'>{item.version} 轮</Text><Button className='icon-button' aria-label={`删除会话：${item.goal}`} disabled={busy} onClick={() => remove(item)}><Icon name='trash' size={17} /></Button></View>)}</View>}
  </StudioShell>
}

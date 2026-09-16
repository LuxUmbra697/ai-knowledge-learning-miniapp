import { requireLogin } from '../../services/access'
import { useEffect, useRef, useState } from 'react'
import { Button, View, Text, Textarea, Image, Input, Picker, ScrollView } from '@tarojs/components'
import Taro, { useDidShow, useDidHide, useRouter } from '@tarojs/taro'
import { StudioShell, Notice, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'
import { useStudio } from '../../components/StudioProvider'
import { getCachedUser, waitForLogin, getToken, LearningTask, getLearningTask, cancelLearningTask } from '../../services/api'
import { CharacterId, CompanionDetail, CompanionMemory, companionDraft, getCompanion, sendCompanion, saveCompanionMemory, resetCompanion } from '../../services/companion'
import { PollControl, pollUntil } from '../../services/polling'
import { taskPhase } from '../../services/taskDisplay'
import { syncCompanionRoute } from '../../services/companionRoute'
import { companionFrames as frames } from '../../services/assets'
const moods = { calm: '安静相伴', happy: '眉眼弯弯', shy: '有一点害羞', warm: '认真听你说', thoughtful: '想一想' }
const kinds = ['称呼', '学习偏好', '相处方式'], kindIds = ['name', 'study', 'support'] as const
const key = () => `companion_${Date.now()}_${Math.random().toString(36).slice(2)}`

export default function CompanionPage() {
  const router = useRouter(), settings = useStudio()
  const [ready, setReady] = useState(false)
  const identity = settings.companionForm
  useEffect(() => {
    const entry = router.params.character
    if (entry === 'pink' || entry === 'orange') settings.update({ companionForm: entry })
    setReady(true)
  }, [])
  useEffect(() => { if (ready) syncCompanionRoute(identity) }, [ready, identity])
  const select = (value: CharacterId) => {
    if (value === identity) return
    settings.update({ companionForm: value })
  }
  if (!ready) return <StudioShell focus compact title='伙伴手札'><Text className='muted'>正在翻开伙伴手札</Text></StudioShell>
  return <CompanionRoom key={identity} identity={identity} onSelect={select} />
}

function CompanionRoom({ identity, onSelect }: { identity: CharacterId; onSelect: (value: CharacterId) => void }) {
  const settings = useStudio()
  const [detail, setDetail] = useState<CompanionDetail | null>(null), [tab, setTab] = useState<'chat' | 'memory' | 'story'>('chat')
  const [text, setText] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false), [task, setTask] = useState<LearningTask | null>(null)
  const [memoryText, setMemoryText] = useState(''), [memoryKind, setMemoryKind] = useState(1), [editId, setEditId] = useState('')
  const [pose, setPose] = useState(0), [reacting, setReacting] = useState(false)
  const lock = useRef(false), live = useRef(true), control = useRef<PollControl>(), reaction = useRef<ReturnType<typeof setTimeout>>()
  const storage = () => `ai-learn:v1:companion-draft:${getCachedUser()?.id}:${identity}`
  const fail = (reason: unknown, current?: PollControl) => { if (live.current && !current?.cancelled) setError(reason instanceof Error ? reason.message : '伙伴暂时无法回应，请重试') }

  const monitor = async (id: string, current: PollControl) => {
    await pollUntil(() => getLearningTask(id, current), item => {
      if (live.current) setTask(item)
      if (item.status === 'failed' || item.status === 'cancelled') {
        Taro.removeStorageSync(storage())
        throw new Error(item.error_message || '这次对话已取消')
      }
      return item.status === 'completed'
    }, { control: current, intervalMs: 2000, maxAttempts: 100 })
    const next = await getCompanion(identity, current)
    if (live.current && !current.cancelled) { setDetail(next); setText(''); Taro.removeStorageSync(storage()) }
  }
  const load = async () => {
    control.current?.cancel(); const current = new PollControl(); control.current = current
    try {
      await waitForLogin(); if (!getToken()) { await requireLogin(undefined, true); return }
      const next = await getCompanion(identity, current)
      if (!live.current || current.cancelled) return
      setDetail(next); setError('')
      const draft = companionDraft(Taro.getStorageSync(storage()))
      if (draft?.version === next.version) setText(draft.text)
      if (next.pending_task_id) {
        const pending = await getLearningTask(next.pending_task_id, current); setTask(pending)
        if (!['failed', 'completed', 'cancelled'].includes(pending.status)) { lock.current = true; setBusy(true); await monitor(pending.task_id, current) }
        else if (pending.status !== 'completed') setError(pending.error_message || '上一轮已取消，可以重新发送')
      }
    } catch (reason) { fail(reason, current) }
    finally { if (control.current === current) { lock.current = false; if (live.current) setBusy(false) } }
  }
  useEffect(() => {
    live.current = true; void load()
    return () => { live.current = false; control.current?.cancel(); clearTimeout(reaction.current) }
  }, [])
  useDidShow(() => { if (!live.current) { live.current = true; void load() } })
  useDidHide(() => { live.current = false; control.current?.cancel(); clearTimeout(reaction.current) })
  const send = async () => {
    if (lock.current || !detail || !text.trim()) return
    lock.current = true; setBusy(true); setError(''); control.current?.cancel()
    const current = new PollControl(); control.current = current
    try {
      const old = companionDraft(Taro.getStorageSync(storage()))
      const draft = old && old.version === detail.version && old.text === text.trim() ? old : { character: identity, version: detail.version, text: text.trim(), key: key() }
      Taro.setStorageSync(storage(), draft)
      const created = await sendCompanion(identity, draft.version, draft.text, draft.key, current)
      Taro.setStorageSync(storage(), { ...draft, taskId: created.task_id })
      await monitor(created.task_id, current)
    } catch (reason) { fail(reason, current) }
    finally { if (control.current === current) { lock.current = false; if (live.current) setBusy(false) } }
  }
  const cancel = async () => {
    if (!task || !(await Taro.showModal({ title: '取消本轮回应', content: '已开始的调用可能产生费用，之前的对话会保留。' })).confirm) return
    try { await cancelLearningTask(task.task_id); await load() } catch (reason) { fail(reason) }
  }
  const saveMemory = async (items: CompanionMemory[]) => {
    if (!detail || lock.current) return
    lock.current = true; setBusy(true); setError('')
    try { setDetail(await saveCompanionMemory(identity, detail.version, items)); setMemoryText(''); setEditId('') }
    catch (reason) { fail(reason) }
    finally { lock.current = false; if (live.current) setBusy(false) }
  }
  const addMemory = async () => {
    if (!detail || !memoryText.trim()) return
    const item = { id: editId || key(), kind: kindIds[memoryKind], text: memoryText.trim() }
    if (!(await Taro.showModal({ title: editId ? '修改这段记忆' : '记住这件事', content: `仅${detail.character.name}会使用这条已确认的偏好：${item.text}` })).confirm) return
    await saveMemory([...detail.memories.filter(memory => memory.id !== editId), item])
  }
  const removeMemory = async (item: CompanionMemory) => {
    if (!detail || !(await Taro.showModal({ title: '删除这段记忆', content: '删除长期记忆条目；若也要清除历史对话中的内容，请使用“清除记忆与对话”。' })).confirm) return
    await saveMemory(detail.memories.filter(value => value.id !== item.id))
  }
  const reset = async (mode: 'history' | 'memory' | 'all') => {
    if (!detail || lock.current) return
    const messages = { history: '删除最近对话与任务内容，保留已确认记忆和故事进度。', memory: '清除全部记忆、对话和任务内容，保留故事进度。', all: '清除记忆、对话与故事进度，重新认识这位伙伴。' }
    if (!(await Taro.showModal({ title: '确认清除', content: messages[mode] })).confirm) return
    lock.current = true; setBusy(true)
    try { setDetail(await resetCompanion(identity, detail.version, mode)); Taro.removeStorageSync(storage()); setText(''); setTask(null); setError('') }
    catch (reason) { fail(reason) }
    finally { lock.current = false; if (live.current) setBusy(false) }
  }
  const touchPortrait = () => { setPose(value => (value + 1) % 3); setReacting(true); clearTimeout(reaction.current); reaction.current = setTimeout(() => setReacting(false), 1400) }
  const lastTurn = detail?.turns[detail.turns.length - 1]
  const latest = lastTurn?.response
  const emotion = reacting ? 'happy' : latest?.emotion || 'calm'
  const frame = reacting ? pose : latest?.action === 'celebrate' ? 2 : latest?.action === 'wave' ? 1 : 0
  return <StudioShell focus compact title='伙伴手札' subtitle={detail?.character.motif}>
    <View className='companion-room-toolbar'><Button className='text-button' onClick={() => Taro.navigateBack().catch(() => navigate('/pages/index/index'))}><Icon name='arrow' size={16} />返回学习</Button><View className='room-character-tabs' data-character={identity}>
      {(['pink', 'orange'] as const).map(value => <Button key={value} disabled={busy} className={identity === value ? 'active' : ''} onClick={() => onSelect(value)}>{value === 'pink' ? '樱野小满' : '秋庭澄'}</Button>)}
    </View></View>
    {error && <Notice message={error} retry={load} />}
    {!detail ? <Text className='muted'>正在翻开伙伴手札</Text> : <View className={`companion-room room-${identity}`}>
      <View className='room-character'><View className={`room-portrait emotion-${emotion} action-${latest?.action || 'read'} ${settings.reducedMotion ? '' : 'room-motion'}`} onClick={touchPortrait}>
        <Image src={frames[identity][frame]} mode='aspectFit' /><Text className='room-emotion'>{moods[emotion]}</Text>
      </View><Text className='room-name'>{detail.character.name}</Text><Text className='room-role'>{detail.character.age} 岁 · {detail.character.role}</Text><Text className='room-personality'>{detail.character.primary}</Text><Text className='tiny-label'>虚构学习伙伴 · {detail.turn_count} 次对话</Text></View>
      <View className='room-content'><View className='room-tabs'>{(['chat', 'memory', 'story'] as const).map((value, index) => <Button key={value} className={tab === value ? 'active' : ''} onClick={() => setTab(value)}>{['对话', `记忆 ${detail.memories.length}`, `故事 ${detail.story.length}/4`][index]}</Button>)}</View>
        {tab === 'chat' && <><ScrollView className='room-transcript' scrollY scrollIntoView={`companion-turn-${lastTurn?.number || 0}`}>
          <View className='room-greeting'><Text>{detail.character.intro}</Text></View>
          {detail.turns.map(turn => <View className='room-turn' id={`companion-turn-${turn.number}`} key={turn.number}>
            <Text className='room-user-text' selectable>{turn.message}</Text><View className={`room-reply emotion-${turn.response.emotion}`}><Text className='tiny-label'>{detail.character.name} · {moods[turn.response.emotion]}</Text><Text selectable>{turn.response.dialogue}</Text>
              {!!turn.response.used_memory_ids.length && <Text className='room-memory-used'>记起了：{turn.response.used_memory_ids.map(id => detail.memories.find(item => item.id === id)?.text).filter(Boolean).join('；') || '当时的已确认记忆'}</Text>}
              {turn.response.memory_suggestion && !detail.memories.some(item => item.text === turn.response.memory_suggestion?.text) && <Button className='text-button' disabled={busy || detail.memories.length >= 12} onClick={() => { setMemoryText(turn.response.memory_suggestion!.text); setMemoryKind(kindIds.indexOf(turn.response.memory_suggestion!.kind)); setEditId(''); setTab('memory') }}><Icon name='add' size={16} />确认记住这件事</Button>}
            </View></View>)}
        </ScrollView><View className='room-composer'><Textarea className='studio-textarea' value={text} maxlength={1000} disabled={busy} onInput={event => setText(event.detail.value)} placeholder='聊聊今天的小事，或此刻的心情' /><View className='section-heading'><Text className='tiny-label'>{busy && task ? taskPhase(task.stage) : '最近保留 100 轮 · 发送会调用 AI'}</Text>{busy && task ? <Button className='secondary-button' onClick={cancel}><Icon name='close' size={16} />取消回应</Button> : <Button className='primary-button' disabled={busy || !text.trim()} onClick={send}><Icon name='chat' size={16} />发送</Button>}</View></View></>}
        {tab === 'memory' && <View className='room-memories'><Text className='muted'>只有你确认的称呼、学习偏好和相处方式会成为长期记忆。不要填写密码或私密资料。</Text>
          {detail.memories.map(item => <View className='room-memory-row' key={item.id}><View><Text className='tiny-label'>{kinds[kindIds.indexOf(item.kind)]}</Text><Text>{item.text}</Text></View><Button className='text-button' disabled={busy} onClick={() => { setEditId(item.id); setMemoryText(item.text); setMemoryKind(kindIds.indexOf(item.kind)) }}>编辑</Button><Button className='icon-button' aria-label={`删除记忆：${item.text}`} disabled={busy} onClick={() => removeMemory(item)}><Icon name='trash' size={16} /></Button></View>)}
          <View className='room-memory-editor'><Picker mode='selector' range={kinds} value={memoryKind} onChange={event => setMemoryKind(Number(event.detail.value))}><Text className='field-label'>{kinds[memoryKind]}</Text></Picker><Input className='studio-input' value={memoryText} maxlength={160} disabled={busy} onInput={event => setMemoryText(event.detail.value)} placeholder='希望伙伴记住的偏好' /><Button className='secondary-button' disabled={busy || !memoryText.trim() || (!editId && detail.memories.length >= 12)} onClick={addMemory}><Icon name='check' size={16} />{editId ? '确认修改' : '确认记住'}</Button></View>
          <View className='room-reset'><Button className='text-button' disabled={busy} onClick={() => reset('history')}>清除最近对话</Button><Button className='text-button' disabled={busy} onClick={() => reset('memory')}>清除记忆与对话</Button><Button className='text-button' disabled={busy} onClick={() => reset('all')}>重新认识</Button></View>
        </View>}
        {tab === 'story' && <View className='room-story'><Text className='room-personality'>{detail.character.primary}</Text><Text className='room-personality'>{detail.character.secondary}</Text>{detail.chapters.map(chapter => <View className='room-chapter' key={chapter.id}><Text className='section-title'>{chapter.title}</Text><Text selectable>{chapter.unlocked ? detail.story.find(item => item.id === chapter.id)?.text : `在第 ${chapter.threshold} 次对话后，翻开这一页。`}</Text></View>)}</View>}
      </View>
    </View>}
  </StudioShell>
}

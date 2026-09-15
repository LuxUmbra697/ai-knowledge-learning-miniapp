import { useMemo, useRef, useState } from 'react'
import { View, Text, Button, Picker, Slider } from '@tarojs/components'
import Taro, { useDidShow, useDidHide, useRouter } from '@tarojs/taro'
import { StudioShell, Notice, Empty, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'
import Diagram from '../../components/study-map/Diagram'
import { getToken, waitForLogin } from '../../services/api'
import { PollControl } from '../../services/polling'
import { getLearningPath, saveLearningPath, previewPlan, listPlans, getPlan, confirmPlan, markPlanRead, pathDiagram,
  LearningPath, LearningPlan, PlanItem, PlanListItem } from '../../services/learningPlan'

const zones = ['Asia/Shanghai', 'UTC', 'America/New_York', 'Europe/London']
const zoneLabels = ['中国标准时间', 'UTC', '纽约', '伦敦']

export default function PathPage() {
  const router = useRouter()
  const [path, setPath] = useState<LearningPath | null>(null), [preview, setPreview] = useState<LearningPlan | null>(null)
  const [plan, setPlan] = useState<LearningPlan | null>(null), [history, setHistory] = useState<PlanListItem[]>([])
  const [tab, setTab] = useState('today'), [minutes, setMinutes] = useState(15), [zone, setZone] = useState('Asia/Shanghai')
  const [source, setSource] = useState(0), [target, setTarget] = useState(1)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true)
  const live = useRef(true), lock = useRef(false), control = useRef<PollControl>()
  const diagram = useMemo(() => path ? pathDiagram(path) : null, [path])
  const fail = (reason: unknown, current?: PollControl) => { if (live.current && !current?.cancelled) setError(reason instanceof Error ? reason.message : '学习计划暂不可用') }
  const load = async (selectedId?: string, onlyPreview = false, count = minutes, timezone = zone) => {
    control.current?.cancel(); const current = new PollControl(); control.current = current; setLoading(true)
    try {
      await waitForLogin()
      if (!getToken()) { navigate('/pages/login/index'); return }
      const relations = await getLearningPath(current), recent = await listPlans(current), proposed = await previewPlan(count, timezone, current)
      const id = selectedId || plan?.plan_id || router.params.planId || recent.items[0]?.plan_id
      const saved = !onlyPreview && id ? await getPlan(id, current) : null
      if (!live.current || current.cancelled) return
      setPath(relations); setHistory(recent.items); setPreview(proposed); setPlan(saved); setError('')
    } catch (reason) { fail(reason, current) }
    finally { if (live.current && !current.cancelled) setLoading(false) }
  }
  useDidShow(() => { live.current = true; void load() })
  useDidHide(() => { live.current = false; control.current?.cancel() })
  const updateEdges = async (edges: [string, string][]) => {
    if (!path || lock.current) return
    if (!(await Taro.showModal({ title: '确认前置关系', content: '保存你设定的学习先后关系？系统会检查循环；这不是自动推断的事实，也不会改动原作答。' })).confirm) return
    lock.current = true; setBusy(true)
    try { await saveLearningPath(path.version, edges); await load() }
    catch (reason) { fail(reason) }
    finally { lock.current = false; if (live.current) setBusy(false) }
  }
  const confirm = async () => {
    if (!preview || lock.current) return
    if (!(await Taro.showModal({ title: '确认本轮计划', content: `保留 ${preview.items.length} 项任务，预计 ${preview.minutes} 分钟？不会修改原复习日期，也不会调用模型。` })).confirm) return
    lock.current = true; setBusy(true)
    try { const result = await confirmPlan(preview); await load(result.plan_id) }
    catch (reason) { fail(reason) }
    finally { lock.current = false; if (live.current) setBusy(false) }
  }
  const read = async (item: PlanItem) => {
    if (!plan?.plan_id || lock.current) return
    if (!(await Taro.showModal({ title: '确认已阅读', content: '将此项标为已阅读？这只是你的阅读确认，不增加掌握度、积分或复习次数。' })).confirm) return
    lock.current = true; setBusy(true)
    try { await markPlanRead(plan.plan_id, item.id); await load(plan.plan_id) }
    catch (reason) { fail(reason) }
    finally { lock.current = false; if (live.current) setBusy(false) }
  }
  const openItem = (item: PlanItem) => Taro.navigateTo({ url: item.kind === 'review'
    ? `/learning/review/index?cardId=${encodeURIComponent(item.card_id)}`
    : `/pages/quiz/index?quizId=${encodeURIComponent(item.quiz_id)}&questionId=${encodeURIComponent(item.question_id)}` })
  const shown = plan || preview
  const name = (id: string) => path?.concepts.find(node => node.concept_id === id)?.label || '不可用知识点'
  return <StudioShell active='home' focus title='学习路径与计划' subtitle='先理清来路，再安排今天的一小步。'>
    <View className='map-tabs'>{[['today', '本轮计划'], ['relations', '前置关系'], ['history', '历史计划']].map(([id, label]) => <Button key={id} className={`text-button ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</Button>)}</View>
    {error && <Notice message={error} retry={() => load()} />}
    {loading && <Text className='muted'>正在读取学习记录</Text>}
    {tab === 'today' && <View className='path-plan'>
      {plan ? <View className='section-heading'><View><Text className='section-title'>已确认计划 · {plan.day}</Text><Text className='muted'>完成 {plan.items.filter(item => item.completed).length} / {plan.items.length} 项 · {plan.timezone}</Text></View><Button className='text-button' disabled={loading || busy} onClick={() => load(undefined, true)}><Icon name='refresh' size={16} />重新安排</Button></View> : <>
        <Text className='field-label'>本轮时长 · {minutes} 分钟</Text><Slider min={5} max={60} step={5} value={minutes} disabled={busy} onChange={event => { setMinutes(event.detail.value); void load(undefined, true, event.detail.value) }} />
        <Picker mode='selector' range={zoneLabels} value={zones.indexOf(zone)} onChange={event => { const value = zones[Number(event.detail.value)]; setZone(value); void load(undefined, true, minutes, value) }}><View className='secondary-button'>{zoneLabels[zones.indexOf(zone)]}</View></Picker>
        <Text className='muted'>预览 · 复习每题按 3 分钟、阅读每项按 2 分钟估计，不是实测学习时长。</Text>
      </>}
      {(plan?.path_changed || plan?.previous_day) && <Text className='notice'>关系或日期已变化。这是原计划记录，可以重新安排。</Text>}
      {!loading && !shown?.items.length && <Empty title='暂时没有待安排任务' text='完成一次练习后，这里会根据实际作答与复习日期提出建议。' />}
      {shown?.items.map((item, i) => <View className='plan-item' key={item.id} data-completed={item.completed ? 'true' : 'false'}>
        <View className='section-heading'><Text className='section-title'>{i + 1}. {item.label}</Text><Text className='tag'>{item.kind === 'review' ? '复习' : '阅读'} · {item.minutes} 分钟</Text></View>
        <Text className='muted'>默认掌握估计 {Math.round(item.basis.mastery * 100)}% · {item.basis.attempts} 次作答{item.basis.due ? ` · 已到期 ${item.basis.overdue_days} 天` : ' · 尚未到复习日'}{item.basis.supports_prerequisite ? ' · 支持后续学习' : ''}</Text>
        {plan && <View className='document-actions'>{item.completed ? <Text className='plan-complete'><Icon name='check' size={16} />{item.completion_source === 'server_review_event' ? '已实际完成复习' : '你已确认阅读'}</Text> : <Button className='secondary-button' onClick={() => openItem(item)}><Icon name={item.kind === 'review' ? 'review' : 'book'} size={16} />{item.kind === 'review' ? '开始这项复习' : '回看题目与解析'}</Button>}{item.kind === 'read' && !item.completed && <Button className='text-button' disabled={busy} onClick={() => read(item)}><Icon name='check' size={16} />已阅读</Button>}</View>}
      </View>)}
      {shown && Object.entries(shown.blocked).length > 0 && <View className='path-blocked'><Text className='section-title'>前置条件待巩固</Text>{Object.entries(shown.blocked).map(([id, parents]) => <Text key={id}>{shown.concepts.find(node => node.concept_id === id)?.label}：先巩固 {parents.map(parent => shown.concepts.find(node => node.concept_id === parent)?.label).join('、')}</Text>)}<Text className='muted'>当前规则：前置知识点至少 3 次作答且默认掌握估计达到 70%。这是安排建议，不是考试通过线。</Text></View>}
      {!plan && !!preview?.items.length && <Button className='primary-button' disabled={busy || loading} onClick={confirm}><Icon name='check' size={17} />确认本轮计划</Button>}
      {shown?.truncated && <Text className='notice'>本次使用最多 100 个知识点、500 道已作答题目；优先保留已设关系与薄弱点。</Text>}
    </View>}
    {tab === 'relations' && path && <View className='path-relations'>
      <Text className='muted'>关系由你设定；知识点标签来自题目，尚未经人工系统标注。</Text>
      {path.concepts.length >= 2 ? <View className='path-edge-editor'>
        <Text className='field-label'>先学习</Text><Picker mode='selector' range={path.concepts.map(node => node.label)} value={source} onChange={event => setSource(Number(event.detail.value))}><View className='secondary-button'>{path.concepts[source]?.label || '选择知识点'}</View></Picker>
        <Text className='field-label'>再学习</Text><Picker mode='selector' range={path.concepts.map(node => node.label)} value={target} onChange={event => setTarget(Number(event.detail.value))}><View className='secondary-button'>{path.concepts[target]?.label || '选择知识点'}</View></Picker>
        <Button className='secondary-button' disabled={busy || source === target || !path.concepts[source] || !path.concepts[target]} onClick={() => updateEdges([...path.edges, [path.concepts[source].concept_id, path.concepts[target].concept_id]])}><Icon name='add' size={16} />添加关系</Button>
      </View> : <Empty title='还需要更多学习记录' text='至少有两个已作答知识点后，可以设置前置关系。' />}
      {path.edges.map(([a, b], i) => <View className='path-edge' key={`${a}-${b}`}><Text>{name(a)}<Icon name='arrow' size={16} />{name(b)}</Text><Button className='icon-button' aria-label={`删除关系 ${i + 1}`} disabled={busy} onClick={() => updateEdges(path.edges.filter((_, index) => index !== i))}><Icon name='trash' size={16} /></Button></View>)}
      {!!path.edges.length && diagram && <Diagram data={diagram} />}
      <View className='path-outline'>{(preview?.order || path.concepts.map(node => node.concept_id)).map((id, index) => <View className='path-node' key={id}><Text>{index + 1}. {name(id)}</Text><Text className='muted'>{path.edges.filter(edge => edge[1] === id).map(edge => name(edge[0])).join('、') || '未设置前置条件'}</Text></View>)}</View>
    </View>}
    {tab === 'history' && <View className='path-history'>{!history.length && <Empty title='还没有确认的计划' text='预览不会写入计划，确认后会保留原来的安排。' />}{history.map(item => <View className='history-row' key={item.plan_id}><Button className='text-button' onClick={() => { setTab('today'); void load(item.plan_id) }}>{item.day} · 预计 {item.minutes} 分钟<Icon name='arrow' size={16} /></Button><Text className='muted'>{new Date(item.created_at).toLocaleTimeString()}</Text></View>)}</View>}
  </StudioShell>
}

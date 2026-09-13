import { useState, useRef } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidShow, useDidHide } from '@tarojs/taro'
import { getKnowledgeDocuments, getKnowledgeDocumentStatus, uploadKnowledgeDocument, deleteKnowledgeDocument, generateQuizAsync, pollQuizTask, waitForLogin, getToken, KnowledgeDocumentItem, reindexDocument } from '../../services/api'
import { PollControl, pollUntil } from '../../services/polling'
import { chooseDocument } from '../../services/chooseDocument'
import { StudioShell, Notice, Empty, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'

const statusText = { processing: '解析中', ready: '已就绪', failed: '解析失败' }
export default function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocumentItem[]>([])
  const [busy, setBusy] = useState(''), [error, setError] = useState(''), [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const live = useRef(true), lock = useRef(false), polls = useRef(new Map<string, PollControl>())
  const watch = async (docId: string) => {
    if (polls.current.has(docId)) return
    const control = new PollControl(); polls.current.set(docId, control)
    try {
      await pollUntil(() => getKnowledgeDocumentStatus(docId, control), status => {
        if (live.current) setDocuments(previous => previous.map(doc => doc.doc_id === docId ? { ...doc, ...status } : doc))
        return status.status !== 'processing'
      }, { control, intervalMs: 3000, maxAttempts: 100 })
    } catch (reason) { if (!control.cancelled && live.current) setError(reason instanceof Error ? reason.message : '状态读取失败') }
    finally { polls.current.delete(docId) }
  }
  const load = async () => {
    await waitForLogin()
    if (!getToken()) { navigate('/pages/login/index'); return }
    try {
      const result = await getKnowledgeDocuments()
      if (!live.current) return
      setDocuments(result.items); setError('')
      result.items.filter(doc => doc.status === 'processing').forEach(doc => watch(doc.doc_id))
    } catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '加载失败') }
    finally { if (live.current) setLoading(false) }
  }
  useDidShow(() => { live.current = true; load() })
  useDidHide(() => { live.current = false; polls.current.forEach(control => control.cancel()); polls.current.clear() })
  const upload = async () => {
    if (lock.current) return
    lock.current = true
    let release: (() => void) | undefined
    try {
      const file = await chooseDocument()
      if (!file) return
      release = file.release
      if (!/\.(pdf|docx|txt|md)$/i.test(file.name)) throw new Error('请选择 PDF、DOCX、TXT 或 Markdown 文件')
      if (!file.size || file.size > 10 * 1024 * 1024) throw new Error('文件须非空，且不超过 10MB')
      setBusy('正在上传文档'); setError('')
      const uploaded = await uploadKnowledgeDocument(file.path, file.name)
      setNotice(uploaded.duplicate ? '这份材料已在书架中，没有重复建立索引。' : '')
      await load()
    } catch (reason: any) { if (live.current && !reason?.errMsg?.includes('cancel')) setError(reason instanceof Error ? reason.message : '上传失败，请重试') }
    finally { release?.(); lock.current = false; if (live.current) setBusy('') }
  }
  const remove = async (doc: KnowledgeDocumentItem) => {
    if (lock.current) return
    const result = await Taro.showModal({ title: '删除文档', content: `删除《${doc.file_name}》及其检索索引？此操作不可撤销。` })
    if (!result.confirm) return
    lock.current = true
    try { await deleteKnowledgeDocument(doc.doc_id); polls.current.get(doc.doc_id)?.cancel(); setDocuments(previous => previous.filter(item => item.doc_id !== doc.doc_id)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '删除失败') }
    finally { lock.current = false }
  }
  const practice = async (doc: KnowledgeDocumentItem) => {
    if (lock.current || doc.status !== 'ready') return
    lock.current = true; setBusy('正在创建练习'); setError('')
    try {
      const { task_id } = await generateQuizAsync(`根据文档《${doc.file_name}》生成知识练习`, 5, doc.doc_id)
      if (!live.current) return
      const control = new PollControl(); polls.current.set(task_id, control)
      const quiz = await pollQuizTask(task_id, stage => setBusy(stage === 'pending' ? '等待处理' : '正在生成练习'), 3000, 100, control)
      polls.current.delete(task_id)
      if (live.current) Taro.navigateTo({ url: `/pages/quiz/index?quizId=${quiz.quiz_id}` })
    } catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '练习生成失败') }
    finally { lock.current = false; if (live.current) setBusy('') }
  }
  const rebuild = async (doc: KnowledgeDocumentItem) => {
    if (lock.current) return
    lock.current = true; setBusy('正在提交重建')
    try { await reindexDocument(doc.doc_id); await load() }
    catch (reason) { setError(reason instanceof Error ? reason.message : '重建失败') }
    finally { lock.current = false; if (live.current) setBusy('') }
  }
  return <StudioShell active='knowledge' title='我的知识书架' subtitle='让自己的学习材料，成为每次探索的起点。'>
    <View className='upload-band'><Button className='primary-button' disabled={!!busy} onClick={upload}><Icon name='upload' size={18} />{busy || '添加学习材料'}</Button><Text className='field-hint'>PDF / DOCX / TXT / Markdown · 最大 10MB · 暂不支持扫描件 OCR</Text></View>
    {error && <Notice message={error} retry={load} />}
    {notice && <Text className='field-hint'>{notice}</Text>}
    <View className='section-heading'><Text className='section-title'>全部文档</Text><Button className='icon-button' aria-label='刷新文档' onClick={load}><Icon name='refresh' /></Button></View>
    {!documents.length && <Empty title={loading ? '正在读取书架' : '书架上还没有学习材料'} text='添加一份笔记、讲义或课程资料，开启自己的知识积累。' />}
    {documents.map(doc => <View className='document-row' key={doc.doc_id}><Icon name='book' size={26} /><View className='row-copy'><Text className='row-title'>{doc.file_name}</Text><Text className='muted'>{doc.needs_reindex ? '需要重建索引' : statusText[doc.status]} · {(doc.file_size / 1024).toFixed(1)} KB{doc.status === 'ready' ? ` · ${doc.chunk_count} 个片段` : ''}</Text>{doc.error_message && <Text className='muted'>{doc.error_message}</Text>}<View className='document-actions'>
      {doc.status === 'ready' && !doc.needs_reindex && <><Button className='secondary-button' disabled={!!busy} onClick={() => Taro.navigateTo({ url: `/learning/assistant/index?docId=${doc.doc_id}` })}><Icon name='chat' size={16} />向材料提问</Button><Button className='text-button' onClick={() => Taro.navigateTo({ url: `/learning/document/index?docId=${doc.doc_id}` })}>查看原文</Button><Button className='text-button' disabled={!!busy} onClick={() => practice(doc)}>知识练习</Button></>}
      {(doc.status === 'failed' || doc.needs_reindex) && doc.status !== 'processing' && <Button className='secondary-button' disabled={!!busy} onClick={() => rebuild(doc)}><Icon name='refresh' size={16} />重新建立索引</Button>}
      <Button className='text-button' disabled={!!busy} onClick={() => remove(doc)}>删除文档</Button></View></View></View>)}
  </StudioShell>
}

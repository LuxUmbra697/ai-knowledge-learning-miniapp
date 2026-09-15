import { useRef, useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidShow, useDidHide, useRouter } from '@tarojs/taro'
import { StudioShell, Notice, Empty, navigate } from '../../components/StudioShell'
import { Evidence, getDocumentChunks, getEvidence, getToken, waitForLogin } from '../../services/api'
import { PollControl } from '../../services/polling'

export default function DocumentPage() {
  const router = useRouter(), live = useRef(true), control = useRef<PollControl>()
  const [items, setItems] = useState<Evidence[]>([]), [total, setTotal] = useState(0), [page, setPage] = useState(1)
  const [error, setError] = useState(''), [loading, setLoading] = useState(true)
  const load = async (next = 1) => {
    await waitForLogin()
    if (!getToken()) { navigate('/pages/login/index'); return }
    const docId = router.params.docId
    if (!docId) { setError('未指定文档'); setLoading(false); return }
    control.current?.cancel(); const current = new PollControl(); control.current = current
    setLoading(true); setError('')
    try {
      const { chunkId, revision } = router.params
      const response = chunkId ? { items: [await getEvidence(docId, chunkId, Number(revision), current)], total: 1, page: 1 } : await getDocumentChunks(docId, next, current)
      if (live.current) { setItems(response.items); setTotal(response.total); setPage(response.page) }
    } catch (reason) { if (live.current && !current.cancelled) setError(reason instanceof Error ? reason.message : '原文读取失败') }
    finally { if (live.current && !current.cancelled) setLoading(false) }
  }
  useDidShow(() => { live.current = true; load(page) })
  useDidHide(() => { live.current = false; control.current?.cancel() })
  return <StudioShell active='knowledge' title='原文证据' subtitle={items[0]?.file_name} focus>
    <View className='section-heading'><Button className='text-button' onClick={() => Taro.navigateBack({ fail: () => navigate('/pages/knowledge/index') })}>返回</Button>{items[0] && <Text className='muted'>文档版本 {items[0].revision} · {total} 个片段</Text>}</View>
    {error && <Notice message={error} retry={() => load(page)} />}
    {!items.length && !error && <Empty title={loading ? '正在读取原文' : '暂无可用片段'} text='' />}
    {items.map(item => <View className='source-fragment' key={item.chunk_id}><Text className='section-title'>{item.page ? `第 ${item.page} 页` : item.section || '正文'}</Text><Text className='original-content' selectable>{item.content}</Text><Text className='tiny-label source-fingerprint'>片段 {item.chunk_id.slice(0, 12)} · 内容校验 {item.content_hash.slice(0, 12)}</Text></View>)}
    {total > 20 && <View className='practice-navigation'><Button className='secondary-button' disabled={page === 1 || loading} onClick={() => load(page - 1)}>上一页</Button><Text>{page} / {Math.ceil(total / 20)}</Text><Button className='secondary-button' disabled={page * 20 >= total || loading} onClick={() => load(page + 1)}>下一页</Button></View>}
  </StudioShell>
}

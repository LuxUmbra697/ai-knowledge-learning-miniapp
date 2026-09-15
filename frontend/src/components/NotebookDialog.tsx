import { useEffect, useRef, useState } from 'react'
import { View, Text, Button, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Icon } from './Icon'
import { Notice } from './StudioShell'
import { PollControl } from '../services/polling'
import { Notebook, NotebookTarget, listNotebooks, createNotebook, renameNotebook, addNotebookQuestion } from '../services/notebooks'

export function NotebookDialog({ target, existing, onClose, onSaved }: {
  target?: NotebookTarget; existing?: Notebook; onClose: () => void; onSaved?: (book: Notebook) => void
}) {
  const [books, setBooks] = useState<Notebook[]>([]), [name, setName] = useState(existing?.name || '')
  const [error, setError] = useState(''), [loading, setLoading] = useState(!!target), [busy, setBusy] = useState(false)
  const control = useRef(new PollControl()), lock = useRef(false)
  const load = () => {
    setLoading(true)
    listNotebooks(control.current).then(data => { setBooks(data.items); setError('') })
      .catch(reason => { if (!control.current.cancelled) setError(reason.message || '错题本读取失败') })
      .finally(() => { if (!control.current.cancelled) setLoading(false) })
  }
  useEffect(() => { if (target) load(); return () => control.current.cancel() }, [])
  const save = async (selected?: Notebook) => {
    if (lock.current || (!selected && !name.trim())) return
    lock.current = true; setBusy(true); setError('')
    try {
      const book = selected || (existing ? await renameNotebook(existing, name.trim(), control.current) : await createNotebook(name.trim(), control.current))
      if (target) {
        const result = await addNotebookQuestion(book.notebook_id, target, control.current)
        Taro.showToast({ title: result.added ? '已加入错题本' : '已在此错题本中', icon: 'none' })
      }
      onSaved?.(book); onClose()
    } catch (reason) { if (!control.current.cancelled) setError(reason instanceof Error ? reason.message : '保存失败') }
    finally { lock.current = false; if (!control.current.cancelled) setBusy(false) }
  }
  return <View className='modal-backdrop' onClick={onClose}><View className='appearance-dialog notebook-dialog' onClick={event => event.stopPropagation()}>
    <View className='section-heading'><Text className='section-title'>{existing ? '重命名错题本' : target ? '加入错题本' : '新建错题本'}</Text><Button className='icon-button' aria-label='关闭错题本对话框' onClick={onClose}><Icon name='close' /></Button></View>
    {error && <Notice message={error} retry={target ? load : undefined} />}
    {loading && <Text className='muted'>正在读取错题本</Text>}
    {target && !loading && <View className='notebook-destinations'>{books.length ? books.map(book => <Button key={book.notebook_id} className='notebook-destination' disabled={busy} onClick={() => save(book)}><Icon name='book' size={18} /><Text>{book.name}</Text><Text className='muted'>{book.question_count || 0} 题</Text></Button>) : <Text className='muted'>还没有命名错题本</Text>}</View>}
    <Text className='field-label'>{existing ? '新名称' : '新建错题本'}</Text>
    <Input className='studio-input' placeholder='错题本名称' maxlength={80} value={name} onInput={event => setName(event.detail.value)} />
    <View className='notebook-form-actions'><Button className='primary-button' disabled={busy || !name.trim()} onClick={() => save()}>{busy ? '正在保存' : existing ? '保存名称' : target ? '新建并加入' : '创建错题本'}</Button></View>
  </View></View>
}

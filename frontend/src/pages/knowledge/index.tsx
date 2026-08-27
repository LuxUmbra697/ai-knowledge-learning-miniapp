import { useState, useRef, useCallback, useEffect } from 'react'
import { View, Text } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import {
  getKnowledgeDocuments,
  getKnowledgeDocumentStatus,
  uploadKnowledgeDocument,
  deleteKnowledgeDocument,
  generateQuizAsync,
  pollQuizTask,
  waitForLogin,
} from '../../services/api'
import type { KnowledgeDocumentItem } from '../../services/api'
import './index.scss'

const SUPPORTED_EXTENSIONS = ['pdf', 'docx', 'md', 'txt']
const MAX_FILE_SIZE = 10 * 1024 * 1024
const STATUS_TEXT: Record<string, string> = {
  processing: '解析中',
  ready: '已就绪',
  failed: '解析失败',
}

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocumentItem[]>([])
  const [uploading, setUploading] = useState(false)
  const [generatingDocId, setGeneratingDocId] = useState<string | null>(null)
  const [generatingText, setGeneratingText] = useState('生成中...')

  const pollTimers = useRef<Record<string, ReturnType<typeof setInterval>>>({})

  const loadDocuments = useCallback(async () => {
    await waitForLogin()
    try {
      const res = await getKnowledgeDocuments()
      setDocuments(res.items)
    } catch {
      // 静默失败，保留当前列表
    }
  }, [])

  useDidShow(() => {
    loadDocuments()
  })

  // 页面卸载时清理所有轮询定时器
  useEffect(() => {
    return () => {
      Object.values(pollTimers.current).forEach((timer) => clearInterval(timer))
    }
  }, [])

  const pollDocumentStatus = useCallback((docId: string) => {
    let attempts = 0
    const timer = setInterval(async () => {
      attempts++
      try {
        const status = await getKnowledgeDocumentStatus(docId)
        setDocuments((prev) =>
          prev.map((doc) =>
            doc.doc_id === docId
              ? { ...doc, status: status.status, chunk_count: status.chunk_count, error_message: status.error_message }
              : doc,
          ),
        )
        if (status.status === 'ready' || status.status === 'failed' || attempts >= 40) {
          clearInterval(timer)
          delete pollTimers.current[docId]
        }
      } catch {
        clearInterval(timer)
        delete pollTimers.current[docId]
      }
    }, 3000)
    pollTimers.current[docId] = timer
  }, [])

  const handleUpload = async () => {
    if (uploading) return
    try {
      const chooseRes = await Taro.chooseMessageFile({
        count: 1,
        type: 'file',
        extension: SUPPORTED_EXTENSIONS,
      })
      const file = chooseRes.tempFiles?.[0]
      if (!file) return

      const ext = (file.name.split('.').pop() || '').toLowerCase()
      if (!SUPPORTED_EXTENSIONS.includes(ext)) {
        Taro.showToast({ title: '仅支持 PDF/Word/Markdown/文本文件', icon: 'none' })
        return
      }
      if (file.size > MAX_FILE_SIZE) {
        Taro.showToast({ title: '文件大小不能超过 10MB', icon: 'none' })
        return
      }

      setUploading(true)
      const result = await uploadKnowledgeDocument(file.path, file.name)

      setDocuments((prev) => [
        {
          doc_id: result.doc_id,
          file_name: result.file_name,
          file_type: ext,
          file_size: file.size,
          status: result.status,
          chunk_count: 0,
          error_message: null,
          created_at: new Date().toISOString(),
        },
        ...prev,
      ])
      Taro.showToast({ title: '上传成功，正在解析', icon: 'success' })
      pollDocumentStatus(result.doc_id)
    } catch (err: any) {
      if (err?.errMsg?.includes('cancel')) return
      Taro.showToast({ title: err.message || '上传失败，请稍后重试', icon: 'none' })
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = (doc: KnowledgeDocumentItem) => {
    Taro.showModal({
      title: '删除文档',
      content: `确定删除《${doc.file_name}》吗？删除后知识库内容将无法恢复`,
      success: async (res) => {
        if (!res.confirm) return
        try {
          await deleteKnowledgeDocument(doc.doc_id)
          setDocuments((prev) => prev.filter((item) => item.doc_id !== doc.doc_id))
        } catch (err: any) {
          Taro.showToast({ title: err.message || '删除失败', icon: 'none' })
        }
      },
    })
  }

  const handleStartQuiz = async (doc: KnowledgeDocumentItem) => {
    if (doc.status !== 'ready' || generatingDocId) return

    setGeneratingDocId(doc.doc_id)
    setGeneratingText('正在创建任务...')
    try {
      const userInput = `请基于我上传的知识库文档《${doc.file_name}》生成一套闯关题`
      const { task_id } = await generateQuizAsync(userInput, 5, doc.doc_id)

      setGeneratingText('AI 正在阅读知识库并生成题目...')
      const quizData = await pollQuizTask(task_id, (status) => {
        if (status === 'running') setGeneratingText('AI 正在生成题目...')
      })

      Taro.navigateTo({
        url: `/pages/quiz/index?quizData=${encodeURIComponent(JSON.stringify(quizData))}`,
      })
    } catch (err: any) {
      Taro.showToast({ title: err.message || '生成失败，请稍后重试', icon: 'none' })
    } finally {
      setGeneratingDocId(null)
      setGeneratingText('生成中...')
    }
  }

  return (
    <View className='knowledge-page'>
      <View className='knowledge-content'>
        <View className='upload-card' onClick={handleUpload}>
          <Text className='upload-icon'>{uploading ? '⏳' : '＋'}</Text>
          <Text className='upload-text'>{uploading ? '上传中...' : '上传文档建知识库'}</Text>
          <Text className='upload-hint'>支持 PDF / Word / Markdown / 文本，最大 10MB</Text>
        </View>

        <Text className='section-title'>我的文档</Text>

        {documents.length === 0 ? (
          <View className='empty-list'>
            <Text className='empty-text'>暂无知识库文档，上传一篇试试吧</Text>
          </View>
        ) : (
          <View className='doc-list'>
            {documents.map((doc) => (
              <View key={doc.doc_id} className='doc-item'>
                <View className='doc-main'>
                  <Text className='doc-name'>{doc.file_name}</Text>
                  <View className='doc-meta-row'>
                    <Text className={`doc-status doc-status-${doc.status}`}>
                      {STATUS_TEXT[doc.status] || doc.status}
                    </Text>
                    {doc.status === 'ready' && (
                      <Text className='doc-meta'>共 {doc.chunk_count} 个知识片段</Text>
                    )}
                    {doc.status === 'failed' && doc.error_message && (
                      <Text className='doc-meta doc-meta-error'>{doc.error_message}</Text>
                    )}
                  </View>
                </View>
                <View className='doc-actions'>
                  {doc.status === 'ready' && (
                    <View
                      className={`quiz-btn ${generatingDocId === doc.doc_id ? 'is-loading' : ''}`}
                      onClick={() => handleStartQuiz(doc)}
                    >
                      <Text>{generatingDocId === doc.doc_id ? generatingText : '开始闯关'}</Text>
                    </View>
                  )}
                  <View className='delete-btn' onClick={() => handleDelete(doc)}>
                    <Text>删除</Text>
                  </View>
                </View>
              </View>
            ))}
          </View>
        )}
      </View>
    </View>
  )
}

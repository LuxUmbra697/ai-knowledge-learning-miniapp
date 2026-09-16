const publicPages = ['/pages/index/index', '/pages/login/index', '/pages/privacy/index']
const privatePages = ['quiz', 'report', 'profile', 'knowledge'].map(page => `/pages/${page}/index`)
  .concat(['assistant', 'document', 'tasks', 'review', 'tutor', 'path', 'companion', 'security'].map(page => `/learning/${page}/index`))
export function isPublicPage(path: string) { return publicPages.includes(path.split('?')[0]) }
export function pageReturnPath(route: string, params: Record<string, string | undefined>) {
  const query = ['quizId', 'docId', 'taskId', 'character'].filter(key => params[key]).map(key => `${key}=${encodeURIComponent(params[key]!)}`).join('&')
  const path = route.startsWith('/ai-learn/') ? route.slice('/ai-learn'.length) : route
  return safeReturnPath((path.startsWith('/') ? path : '/' + path) + (query ? '?' + query : ''))
}
export function safeReturnPath(value: unknown): string {
  if (typeof value !== 'string' || value.length > 600) return '/pages/index/index'
  const [path, query = '', extra] = value.split('?')
  if (extra !== undefined || !privatePages.concat('/pages/index/index').includes(path)) return '/pages/index/index'
  if (query && !query.split('&').every(part => /^(quizId|docId|taskId|character)=[a-zA-Z0-9_-]{1,120}$/.test(part))) return '/pages/index/index'
  return value
}

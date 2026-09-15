import { expect, request, FullConfig } from '@playwright/test'

export default async function setup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL!
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(new URL(baseURL).hostname)) throw new Error('Synthetic E2E must use an isolated loopback environment')
  const client = await request.newContext({ baseURL })
  try {
    await expect.poll(async () => {
      try {
        const health = await client.get('api/v1/health', { timeout: 2000 })
        return health.ok() && (await health.json()).status === 'ok'
      } catch { return false }
    }, { timeout: 30000, message: 'The isolated API must finish startup before browser scenarios' }).toBe(true)
  } finally { await client.dispose() }
}

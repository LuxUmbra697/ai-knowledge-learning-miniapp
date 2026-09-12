import http from 'node:http'
import { createReadStream } from 'node:fs'
import { stat } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../dist/h5/', import.meta.url))
const prefix = '/ai-learn/'
const port = Number(process.env.PREVIEW_PORT || 18082)
const api = new URL(process.env.PREVIEW_API || 'http://127.0.0.1:18081')
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.json': 'application/json' }

http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  if (url.pathname === '/ai-learn') { res.writeHead(308, { Location: prefix + url.search }); res.end(); return }
  if (url.pathname.startsWith('/ai-learn/api/')) {
    const upstream = http.request(new URL(url.pathname.slice('/ai-learn'.length) + url.search, api), {
      method: req.method, headers: { ...req.headers, host: api.host }, timeout: 125000,
    }, response => { res.writeHead(response.statusCode, response.headers); response.pipe(res) })
    upstream.on('error', () => { if (!res.headersSent) res.writeHead(502, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ code: 502, message: 'Local API unavailable' })) })
    upstream.on('timeout', () => upstream.destroy())
    req.on('aborted', () => upstream.destroy())
    req.pipe(upstream)
    return
  }
  if (!url.pathname.startsWith(prefix)) { res.writeHead(404); res.end(); return }
  let target
  try { target = path.resolve(root, decodeURIComponent(url.pathname.slice(prefix.length)) || 'index.html') }
  catch { res.writeHead(400); res.end(); return }
  if (!target.startsWith(root)) { res.writeHead(403); res.end(); return }
  try {
    const info = await stat(target).catch(() => null)
    if (!info?.isFile()) {
      if (path.extname(target)) { res.writeHead(404); res.end(); return }
      target = path.join(root, 'index.html')
    }
    await stat(target)
    res.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'application/octet-stream', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' })
    createReadStream(target).pipe(res)
  } catch { res.writeHead(503); res.end('Build H5 first') }
}).listen(port, '127.0.0.1', () => process.stdout.write(`H5 preview: http://127.0.0.1:${port}${prefix}\n`))

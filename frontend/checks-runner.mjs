import { spawn } from 'node:child_process'
import { createServer } from 'node:http'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const checks = {
  'frontend-tests': { timeout: 120_000 },
  typescript: { timeout: 120_000 },
  'frontend-build': { timeout: 180_000 },
}
const enabled = process.env.QUALITY_RUNNER_ENABLED === 'true'
let busy = false

function send(response, code, body) {
  response.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' })
  response.end(JSON.stringify(body))
}

function runNode(args, timeout) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, {
      cwd: '/site',
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        PATH: process.env.PATH || '',
        HOME: '/tmp',
        TMPDIR: '/tmp',
        CI: 'true',
        NO_COLOR: '1',
      },
    })
    let output = ''
    let timedOut = false
    const collect = chunk => { output = (output + chunk.toString('utf8')).slice(0, 12_000) }
    child.stdout.on('data', collect)
    child.stderr.on('data', collect)
    const timer = setTimeout(() => {
      timedOut = true
      try { process.kill(-child.pid, 'SIGKILL') } catch { /* already exited */ }
    }, timeout)
    child.once('error', error => { clearTimeout(timer); reject(error) })
    child.once('close', code => { clearTimeout(timer); resolve({ exit_code: code, output, timeout: timedOut }) })
  })
}

async function execute(checkId) {
  const directory = await mkdtemp(join(tmpdir(), 'frontend-check-'))
  try {
    if (checkId === 'frontend-tests') {
      const reportPath = join(directory, 'vitest.json')
      const result = await runNode([
        'node_modules/vitest/vitest.mjs', 'run', '--environment', 'jsdom',
        '--reporter=json', `--outputFile=${reportPath}`,
      ], checks[checkId].timeout)
      let report = null
      try { report = JSON.parse(await readFile(reportPath, 'utf8')) } catch { /* reported as missing by API */ }
      return { ...result, report }
    }
    const types = await runNode(['node_modules/typescript/bin/tsc', '-b', '--pretty', 'false'], checks[checkId].timeout)
    if (checkId === 'typescript' || types.exit_code !== 0 || types.timeout) return types
    const build = await runNode(['node_modules/vite/bin/vite.js', 'build'], checks[checkId].timeout)
    return { ...build, output: `${types.output}\n${build.output}`.slice(0, 12_000) }
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
}

createServer(async (request, response) => {
  if (!enabled) return send(response, 403, { error: 'forbidden' })
  if (request.method === 'GET' && request.url === '/health') return send(response, 200, { status: 'ok' })
  const checkId = request.url?.startsWith('/run/') ? request.url.slice('/run/'.length) : ''
  if (request.method !== 'POST' || !Object.hasOwn(checks, checkId)) {
    return send(response, 404, { error: 'unknown check' })
  }
  if (busy) return send(response, 409, { error: 'busy' })
  busy = true
  try {
    send(response, 200, await execute(checkId))
  } catch {
    send(response, 500, { error: 'runner error' })
  } finally {
    busy = false
  }
}).listen(9090, '0.0.0.0')

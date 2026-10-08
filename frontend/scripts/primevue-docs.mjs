import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import { createRequire } from 'node:module'
import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { parse } from 'vue/compiler-sfc'
const require = createRequire(import.meta.url)
const server = spawn(process.execPath, [require.resolve('@primevue/mcp')], { stdio: ['pipe', 'pipe', 'inherit'], windowsHide: true })
const pending = new Map()
let nextId = 1
function failPending(error) {
  for (const callback of pending.values()) callback.reject(error)
  pending.clear()
}
server.on('error', failPending)
server.on('exit', code => failPending(new Error(`PrimeVue MCP exited (${code})`)))
createInterface({ input: server.stdout }).on('line', line => {
  let reply
  try { reply = JSON.parse(line) } catch { return }
  const callback = pending.get(reply.id)
  if (callback) { pending.delete(reply.id); reply.error ? callback.reject(reply.error) : callback.resolve(reply.result) }
})
function request(method, params) {
  const id = nextId++
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { pending.delete(id); reject(new Error(`MCP request timed out: ${method}`)) }, 30000)
    pending.set(id, {
      resolve: value => { clearTimeout(timeout); resolve(value) },
      reject: error => { clearTimeout(timeout); reject(error) },
    })
    server.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n')
  })
}
async function vueFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = await Promise.all(entries.map(entry => entry.isDirectory() ? vueFiles(join(directory, entry.name)) : entry.name.endsWith('.vue') ? [join(directory, entry.name)] : []))
  return files.flat()
}
function componentUsage(source, local, canonical) {
  const tags = []
  const camelize = name => name.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())
  function visit(node) {
    if (node.type === 1 && node.tag === local) {
      const isAnchor = canonical === 'Button' && node.props.some(prop => prop.type === 6 && prop.name === 'as' && prop.value?.content === 'a')
      // The MCP validator expects camelCase API names, while Vue accepts kebab-case.
      const attributes = node.props.map(prop => {
        // Button's source-backed Link example supports native anchor attributes,
        // but the MCP API metadata only includes ButtonHTMLAttributes.
        if (isAnchor && ['href', 'target', 'rel'].includes(prop.type === 6 ? prop.name : prop.arg?.content)) return ''
        if (prop.type === 6) return `${/^(aria|data)-/.test(prop.name) ? prop.name : camelize(prop.name)}="${prop.value?.content ?? ''}"`
        if (prop.name === 'bind' && prop.arg?.isStatic) return `:${/^(aria|data)-/.test(prop.arg.content) ? prop.arg.content : camelize(prop.arg.content)}="value"`
        if (prop.name === 'model') return `v-model${prop.arg ? ':' + camelize(prop.arg.content) : ''}="value"`
        if (prop.name === 'on' && prop.arg?.isStatic) return `@${prop.arg.content}="handler"`
        return ''
      })
      tags.push(`<${canonical} ${attributes.join(' ')} />`)
    }
    for (const child of node.children ?? []) visit(child)
  }
  const ast = parse(source).descriptor.template?.ast
  if (ast) visit(ast)
  return tags.join('\n')
}
try {
  await request('initialize', { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'application-tracker', version: '1.0' } })
  server.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n')
  if (process.argv[2] === 'list') console.log(JSON.stringify(await request('tools/list', {}), null, 2))
  else if (process.argv[2] === 'validate-project') {
    let checked = 0
    let failed = 0
    let columns = 0
    let stepParts = 0
    for (const file of await vueFiles(process.argv[3] || 'src')) {
      const source = await readFile(file, 'utf8')
      for (const match of source.matchAll(/import\s+(\w+)\s+from\s+['"]primevue\/([^'"]+)['"]/g)) {
        const [, local, component] = match
        if (!new RegExp(`<${local}\\b`).test(source)) continue
        // Column is documented inside DataTable, without its own MCP API entry.
        // vue-tsc validates its props; the source-backed example documents usage.
        if (component === 'column') { columns++; continue }
        // Stepper's Linear example documents these children; the MCP has no
        // separate metadata entry for them. vue-tsc checks their public props.
        if (['step', 'steplist', 'steppanels', 'steppanel'].includes(component)) { stepParts++; continue }
        // Documentation uses canonical component names; wrappers may alias imports.
        const canonical = local === 'PrimeDatePicker' ? 'DatePicker' : local
        const code = componentUsage(source, local, canonical)
        const reply = await request('tools/call', { name: 'validate_usage', arguments: { component, code } })
        const result = reply.structuredContent
        checked++
        if (reply.isError || !result?.valid) { failed++; console.log(JSON.stringify({ file, component, issues: result?.issues?.map(({ kind, name, message }) => ({ kind, name, message })) ?? reply })) }
      }
    }
    console.log(`PrimeVue MCP: ${checked} component usages checked; ${failed} need review.`)
    if (columns) console.log(`${columns} Column import validated by vue-tsc; MCP has no standalone Column metadata. Anchor Button attributes follow the MCP Link example.`)
    if (stepParts) console.log(`${stepParts} Stepper child imports checked by vue-tsc and the MCP Linear example; no standalone child metadata is available.`)
    if (failed) process.exitCode = 1
  } else {
    const reply = await request('tools/call', { name: process.argv[2] || 'get_setup', arguments: process.argv[3] ? JSON.parse(process.argv[3]) : {} })
    console.log(JSON.stringify(reply.structuredContent ?? reply, null, 2))
    if (reply.isError) process.exitCode = 1
  }
} catch (error) {
  console.error(error)
  process.exitCode = 1
} finally { server.kill() }

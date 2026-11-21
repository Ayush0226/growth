import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const pages = JSON.parse(await readFile(path.join(root, 'src/legalContent.json'), 'utf8'))
const escape = value => value.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))
const destination = path.join(root, 'dist/legal')
await mkdir(destination, { recursive: true })
for (const [slug, page] of Object.entries(pages)) {
  const nav = Object.entries(pages).map(([key, value]) => `<a href="/legal/${key}.html">${escape(value.title)}</a>`).join(' · ')
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(page.title)} | Growthboard by AS Techzone</title><style>body{margin:0;background:#f6f8fb;color:#172235;font:17px/1.7 system-ui,sans-serif}main{max-width:800px;margin:auto;padding:48px 24px}a{color:#155ab6}nav{font-size:14px}h1{line-height:1.15}small{color:#536175}p{margin:24px 0}</style></head><body><main><a href="/">Growthboard · AS Techzone</a><h1>${escape(page.title)}</h1><small>Last updated November 12, 2026</small>${page.body.map(p => `<p>${escape(p)}</p>`).join('')}<p><a href="mailto:ayushsony126@gmail.com">ayushsony126@gmail.com</a></p><nav>${nav}</nav></main></body></html>`
  await writeFile(path.join(destination, `${slug}.html`), html, 'utf8')
}
console.log(`Exported ${Object.keys(pages).length} public legal pages with readable HTML.`)

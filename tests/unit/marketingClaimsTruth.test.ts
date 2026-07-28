import fs from 'fs'
import path from 'path'

const marketingFiles = [
  'components/site/marketing/operationalStories.ts',
  'components/site/marketing/RebrandHomePage.tsx',
  'components/site/marketing/OperationalLedgerPage.tsx',
] as const

const statusFiles = [
  'docs/project-status.md',
  'docs/roadmap.md',
  'docs/surfaces.md',
  'docs/surface-matrix.md',
  'docs/app-dashboard.md',
  'docs/policy-guard-design.md',
] as const

function readFiles(files: readonly string[]) {
  return files.map((file) => ({
    file,
    source: fs.readFileSync(path.join(process.cwd(), file), 'utf-8'),
  }))
}

describe('public capability claim truth', () => {
  it('rejects the known high-risk unsupported claims without banning ordinary prose', () => {
    const forbiddenClaims = [
      /complete trace history for every agent decision/i,
      /attributes spend in real time/i,
      /enforces budgets at the control plane/i,
      /every agent action is evaluated/i,
      /routes around failures/i,
      /no human intervention required/i,
      /first-party signed and notarized macOS release handoff/i,
      /current signed GitHub release assets/i,
      /some backend capabilities remain placeholder-backed, especially scheduler/i,
      /the system never fails open/i,
      /defaults to PERMIT with a logged warning/i,
      /RBAC enforcement on all routes/i,
      /deployment completed/i,
    ]

    for (const { file, source } of readFiles([...marketingFiles, ...statusFiles])) {
      for (const claim of forbiddenClaims) {
        if (claim.test(source)) {
          throw new Error(`${file} reintroduced unsupported capability claim ${claim}`)
        }
      }
    }
  })

  it('keeps scope boundaries where operators make product decisions', () => {
    const marketing = readFiles(marketingFiles)
      .map(({ source }) => source)
      .join('\n')
    const status = readFiles(statusFiles)
      .map(({ source }) => source)
      .join('\n')

    expect(marketing).toMatch(/calls routed through its governed runtime handler/i)
    expect(marketing).toMatch(/instrumentation determines coverage/i)
    expect(marketing).toMatch(/runtime budget cutoffs remain an integration concern/i)
    expect(marketing).toMatch(/provider rollout remains operator-owned/i)
    expect(marketing).toMatch(/check Mac availability/i)

    expect(status).toMatch(/process-local/i)
    expect(status).toMatch(/RAG is optional and disabled by default/i)
    expect(status).toMatch(/operator-managed local daemon/i)
    expect(status).toMatch(/do not prove a Railway rollout/i)
    expect(status).toMatch(/does not, by itself, prove that a public domain is reachable/i)
    expect(status).toMatch(/complete remote artifact set/i)
  })
})

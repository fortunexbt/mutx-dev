import { readFileSync, readdirSync } from 'node:fs'
import { extname, join, relative } from 'node:path'

const ROOTS = [
  'app/control',
  'app/dashboard',
  'components/app',
  'components/dashboard',
]

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    return ['.ts', '.tsx', '.css'].includes(extname(entry.name)) ? [path] : []
  })
}

describe('dashboard reduced-motion contract', () => {
  it('guards every continuous dashboard animation with a reduced-motion variant', () => {
    const violations: string[] = []

    for (const file of ROOTS.flatMap(sourceFiles)) {
      readFileSync(file, 'utf8')
        .split('\n')
        .forEach((line, index) => {
          if (!/animate-(?:spin|pulse|ping|bounce)/.test(line)) return
          if (/motion-(?:safe|reduce):/.test(line)) return
          violations.push(`${relative(process.cwd(), file)}:${index + 1}`)
        })
    }

    expect(violations).toEqual([])
  })
})

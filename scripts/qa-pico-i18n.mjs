import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'

const repoRoot = process.cwd()
const messagesDir = path.join(repoRoot, 'messages')
const baseLocale = 'en'
const picoKey = 'pico'
const requiredPicoBranches = [
  'supportPage',
  'autopilotPage',
  'pricingPage',
  'sessionBanner',
  'shell',
  'platformSurface',
  'onboardingPage',
  'tutorPage',
  'academyPage',
  'lessonPage',
  'welcomeTour',
  'signalDiagram',
  'surfaceCompass',
  'routeStates',
  'auth',
  'authRecovery',
  'content',
]
const arabicPattern = /\p{Script=Arabic}/u
const latinPattern = /[A-Za-z]/
const hanPattern = /\p{Script=Han}/u
const exactEnglishLocales = new Set(['ko', 'zh', 'ar'])
const allowedArabicTechnicalTermsPattern =
  /\b(?:API|BYOK|SSO|SLA|SSH|OpenAI|Hermes|OpenClaw|NanoClaw|PicoClaw|Tailscale|Autopilot|Tutor|Academy|Coach|runtime|webhooks?|gateway|URL|Pico|PicoMUTX|MUTX|GitHub|Markdown|slug)\b/giu

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'))
}

function flatten(value, prefix = '', output = new Map()) {
  if (typeof value === 'string') {
    output.set(prefix, value)
    return output
  }

  if (Array.isArray(value)) {
    value.forEach((item, index) => flatten(item, prefix ? `${prefix}.${index}` : String(index), output))
    return output
  }

  if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      flatten(child, prefix ? `${prefix}.${key}` : key, output)
    }
  }

  return output
}

function valueKind(value) {
  if (Array.isArray(value)) return 'array'
  if (value === null) return 'null'
  return typeof value
}

function isMessageObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function mergeMessages(base, override) {
  if (!isMessageObject(override)) {
    return structuredClone(base)
  }

  const merged = structuredClone(base)
  for (const [key, value] of Object.entries(override)) {
    if (!Object.hasOwn(base, key)) {
      merged[key] = structuredClone(value)
      continue
    }

    if (Array.isArray(value) && Array.isArray(base[key])) {
      merged[key] = Array.from(
        { length: Math.max(base[key].length, value.length) },
        (_, index) => {
        const baseItem = base[key][index]
        const overrideItem = value[index]
        if (overrideItem === undefined) return structuredClone(baseItem)
        if (baseItem === undefined) return structuredClone(overrideItem)
        if (isMessageObject(baseItem) && isMessageObject(overrideItem)) {
          return mergeMessages(baseItem, overrideItem)
        }
        return structuredClone(overrideItem)
        },
      )
      continue
    }

    if (isMessageObject(value) && isMessageObject(base[key])) {
      merged[key] = mergeMessages(base[key], value)
      continue
    }

    merged[key] = value
  }
  return merged
}

function loadEffectiveEnglishDefaults() {
  const require = createRequire(import.meta.url)
  const TypeScript = require('typescript')
  const Module = require('node:module')
  const originalResolveFilename = Module._resolveFilename
  const originalTypeScriptLoader = require.extensions['.ts']

  Module._resolveFilename = function resolveFilename(request, parent, isMain, options) {
    const resolvedRequest = request.startsWith('@/')
      ? path.join(repoRoot, request.slice(2))
      : request
    return originalResolveFilename.call(this, resolvedRequest, parent, isMain, options)
  }
  require.extensions['.ts'] = (module, filename) => {
    const source = fs.readFileSync(filename, 'utf8')
    const compiled = TypeScript.transpileModule(source, {
      compilerOptions: {
        esModuleInterop: true,
        module: TypeScript.ModuleKind.CommonJS,
        target: TypeScript.ScriptTarget.ES2022,
      },
      fileName: filename,
    }).outputText
    module._compile(compiled, filename)
  }

  try {
    const defaultsModule = require(path.join(repoRoot, 'lib/pico/defaultMessages.ts'))
    return defaultsModule.getPicoDefaultMessages()[picoKey]
  } finally {
    Module._resolveFilename = originalResolveFilename
    if (originalTypeScriptLoader) {
      require.extensions['.ts'] = originalTypeScriptLoader
    } else {
      delete require.extensions['.ts']
    }
  }
}

function compareCanonicalShape(source, localized, locale, prefix, issues) {
  const expectedKind = valueKind(source)
  const localizedKind = valueKind(localized)
  if (expectedKind !== localizedKind) {
    issues.push(`${locale}:${prefix}: expected ${expectedKind}, received ${localizedKind}`)
    return
  }

  if (Array.isArray(source)) {
    source.forEach((child, index) => {
      const key = `${prefix}.${index}`
      if (index >= localized.length) {
        issues.push(`${locale}:${key}: missing canonical message`)
        return
      }
      compareCanonicalShape(child, localized[index], locale, key, issues)
    })
    return
  }

  if (source && typeof source === 'object') {
    for (const [key, child] of Object.entries(source)) {
      const childPath = prefix ? `${prefix}.${key}` : key
      if (!Object.hasOwn(localized, key)) {
        issues.push(`${locale}:${childPath}: missing canonical message`)
        continue
      }
      compareCanonicalShape(child, localized[key], locale, childPath, issues)
    }

  }
}

function icuArguments(value) {
  if (typeof value !== 'string') return []
  return [...new Set([...value.matchAll(/\{([A-Za-z_][A-Za-z0-9_.-]*)\b/g)].map((match) => match[1]))].sort()
}

function shouldIgnoreMixedScript(key, value) {
  const normalized = value
    .replace(allowedArabicTechnicalTermsPattern, '')
    .replace(/`[^`]+`/g, '')
    .replace(/\{[^}]+\}/g, '')
    .replace(/sk-[\p{L}\p{N}._-]+/gu, '')

  return (
    key.includes('.command') ||
    value.includes('PicoMUTX') ||
    value.includes('MUTX') ||
    value.includes('GitHub') ||
    value.includes('SaaS') ||
    value.includes('@') ||
    /\b(?:API|BYOK|SSO|SLA|OpenAI|Hermes)\b/.test(value) ||
    /\b\d+K\+?\b/.test(value) ||
    !latinPattern.test(normalized)
  )
}

function shouldIgnoreExactEnglish(_locale, key, value) {
  return (
    key.includes('.command') ||
    key === 'nav.brand' ||
    key === 'nav.brandTag' ||
    key.endsWith('footer.links.github') ||
    key.endsWith('footer.links.docs') ||
    key.endsWith('.price') ||
    (key.startsWith('pages.') && key.endsWith('.meta.title')) ||
    key === 'contactForm.companyPlaceholder' ||
    key.endsWith('.id') ||
    key.toLowerCase().includes('placeholder') ||
    key === 'surfaceCompass.forwardSymbol' ||
    key === 'academyPage.shell.title' ||
    key.endsWith('.telemetryDetail') ||
    value.startsWith('[Unit]\n') ||
    /^\{[^}]+\}(?:\s+\{[^}]+\})*$/.test(value) ||
    /^(?:Autopilot|Tutor|Academy|Runtime|OpenAI|Pico|PicoMUTX|MUTX|Pico Coach|Hermes|OpenClaw|NanoClaw|PicoClaw|Tailscale|SSH)$/.test(value) ||
    /^\d+\s+(?:Autopilot|Tutor|Academy|Runtime|OpenAI|Pico|PicoMUTX|MUTX)$/.test(value) ||
    key.endsWith('ctaHref') ||
    (value.includes('@') && key.endsWith('emailPlaceholder'))
  )
}

const englishRawPico = readJson(path.join(messagesDir, `${baseLocale}.json`))[picoKey]
const englishPico = mergeMessages(loadEffectiveEnglishDefaults(), englishRawPico)
const english = flatten(englishPico)
const localeFiles = fs.readdirSync(messagesDir).filter((file) => file.endsWith('.json') && file !== `${baseLocale}.json`)
const issues = []

for (const file of localeFiles) {
  const locale = path.basename(file, '.json')
  const picoMessages = readJson(path.join(messagesDir, file))[picoKey]
  if (!picoMessages || typeof picoMessages !== 'object' || Array.isArray(picoMessages)) {
    issues.push(`${locale}:${picoKey}: missing canonical message tree`)
    continue
  }

  compareCanonicalShape(englishPico, picoMessages, locale, picoKey, issues)
  const flattened = flatten(picoMessages)

  for (const branch of requiredPicoBranches) {
    if (!picoMessages?.[branch]) {
      issues.push(`${locale}:${branch}: missing locale branch`)
    }
  }

  for (const [key, value] of flattened.entries()) {
    const source = english.get(key)
    if (typeof value !== 'string') {
      continue
    }

    const normalized = value.trim()
    if (!normalized) {
      continue
    }

    if (typeof source === 'string') {
      const expectedArguments = icuArguments(source)
      const localizedArguments = icuArguments(value)
      if (expectedArguments.join('\0') !== localizedArguments.join('\0')) {
        issues.push(
          `${locale}:${key}: ICU arguments differ (expected ${expectedArguments.join(', ') || 'none'}; received ${localizedArguments.join(', ') || 'none'})`,
        )
      }
    }

    if (exactEnglishLocales.has(locale) && source && normalized === source.trim() && !shouldIgnoreExactEnglish(locale, key, normalized)) {
      issues.push(`${locale}:${key}: exact English fallback`)
    }

    if (locale === 'ar' && !shouldIgnoreMixedScript(key, normalized) && arabicPattern.test(normalized) && (latinPattern.test(normalized) || hanPattern.test(normalized))) {
      issues.push(`${locale}:${key}: mixed-script contamination`)
    }
  }
}

if (issues.length > 0) {
  console.error('Pico i18n QA failed:')
  for (const issue of issues) {
    console.error(`- ${issue}`)
  }
  process.exit(1)
}

console.log('Pico i18n QA passed.')

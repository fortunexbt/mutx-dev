#!/usr/bin/env node

import { promises as fs } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const REPO_PACK_DIR = path.join(ROOT, 'src/api/knowledge/pico-builder-pack')
const MANIFEST_PATH = path.join(ROOT, 'src/api/knowledge/pico_ops/manifest.json')
const LESSONS_PATH = path.join(ROOT, 'src/api/knowledge/pico_ops/pico_lessons.json')
const OUTPUT_PATH = path.join(ROOT, 'lib/pico/generatedContent.ts')

const STACKS = [
  { id: 'hermes', name: 'Hermes', filename: 'HERMES.md' },
  { id: 'openclaw', name: 'OpenClaw', filename: 'OPENCLAW.md' },
  { id: 'nanoclaw', name: 'NanoClaw', filename: 'NANOCLAW.md' },
  { id: 'picoclaw', name: 'PicoClaw', filename: 'PICOCLAW.md' },
]

const githubToken = process.env.GITHUB_TOKEN?.trim()
const GITHUB_HEADERS = {
  Accept: 'application/vnd.github+json',
  'User-Agent': 'mutx-pico-content-sync',
  ...(githubToken ? { Authorization: `Bearer ${githubToken}` } : {}),
}

function compactWhitespace(value) {
  return value.replace(/\s+/g, ' ').trim()
}

function displaySourcePath(sourcePath) {
  const relativePath = path.relative(ROOT, sourcePath)
  return relativePath && !relativePath.startsWith('..') ? relativePath : sourcePath
}

function formatDateLabel(value) {
  if (!value) return 'Unavailable'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'Unavailable'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(parsed)
}

function humanJoin(values) {
  if (values.length <= 1) return values[0] ?? ''
  if (values.length === 2) return `${values[0]} and ${values[1]}`
  return `${values.slice(0, -1).join(', ')}, and ${values.at(-1)}`
}

function parseArgs(argv) {
  const packs = []
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index]
    if (token === '--pack' && argv[index + 1]) {
      packs.push(argv[index + 1])
      index += 1
      continue
    }

    if (token.startsWith('--pack=')) {
      packs.push(token.slice('--pack='.length))
    }
  }
  return packs
}

async function pathExists(targetPath) {
  try {
    await fs.access(targetPath)
    return true
  } catch {
    return false
  }
}

async function resolvePackDirectories() {
  const cliPacks = parseArgs(process.argv.slice(2))
  const envPacks = (process.env.PICO_SOURCE_PACKS ?? '')
    .split(path.delimiter)
    .map((value) => value.trim())
    .filter(Boolean)

  const candidates = Array.from(
    new Set([REPO_PACK_DIR, ...envPacks, ...cliPacks].map((value) => path.resolve(value))),
  )

  const existing = []
  for (const candidate of candidates) {
    if (await pathExists(candidate)) {
      existing.push(candidate)
    }
  }

  return existing
}

async function buildPackFileMap(packDirectories) {
  const fileMap = new Map()

  for (const directory of packDirectories) {
    const entries = await fs.readdir(directory, { withFileTypes: true })
    for (const entry of entries) {
      if (!entry.isFile() || !entry.name.endsWith('.md')) {
        continue
      }
      fileMap.set(entry.name, path.join(directory, entry.name))
    }
  }

  return fileMap
}

function getMarkdownSection(markdown, heading) {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const target = `## ${heading}`
  const startIndex = lines.findIndex((line) => line.trim() === target)

  if (startIndex === -1) {
    return ''
  }

  let endIndex = lines.length
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    if (lines[index].startsWith('## ')) {
      endIndex = index
      break
    }
  }

  return lines.slice(startIndex + 1, endIndex).join('\n').trim()
}

function extractFirstParagraph(section) {
  const blocks = section
    .split(/\n{2,}/)
    .map((value) => value.trim())
    .filter(Boolean)

  for (const block of blocks) {
    if (
      block.startsWith('- ') ||
      block.startsWith('```') ||
      block.startsWith('### ') ||
      /^\d+\./.test(block)
    ) {
      continue
    }
    return compactWhitespace(block)
  }

  return ''
}

function extractBullets(section) {
  return section
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('- '))
    .map((line) => compactWhitespace(line.slice(2)))
}

function extractOrderedSteps(section) {
  return section
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => /^\d+\.\s/.test(line))
    .map((line) => compactWhitespace(line.replace(/^\d+\.\s*/, '')))
}

function extractFirstDate(value) {
  return value.match(/\b\d{4}-\d{2}-\d{2}\b/)?.[0] ?? null
}

function pickOfficialLink(urls, matcher) {
  return urls.find((url) => matcher.test(url)) ?? null
}

async function readJson(targetPath) {
  return JSON.parse(await fs.readFile(targetPath, 'utf8'))
}

async function readText(targetPath) {
  return fs.readFile(targetPath, 'utf8')
}

async function readExistingGeneratedContent() {
  if (!(await pathExists(OUTPUT_PATH))) {
    return null
  }

  try {
    const raw = await readText(OUTPUT_PATH)
    const match = raw.match(/export const PICO_GENERATED_CONTENT = ([\s\S]+) as const\s*$/)
    return match ? JSON.parse(match[1]) : null
  } catch (error) {
    console.warn(
      `[pico-content] failed to read existing generated content: ${error instanceof Error ? error.message : String(error)}`,
    )
    return null
  }
}

async function fetchGitHubJson(endpoint, allowNotFound = false) {
  try {
    const response = await fetch(`https://api.github.com${endpoint}`, {
      headers: GITHUB_HEADERS,
    })

    if (allowNotFound && response.status === 404) {
      return null
    }

    if (!response.ok) {
      throw new Error(`GitHub request failed (${response.status}) for ${endpoint}`)
    }

    return response.json()
  } catch (error) {
    console.warn(`[pico-content] ${error instanceof Error ? error.message : String(error)}`)
    return null
  }
}

async function fetchGitHubSnapshot(repoUrl) {
  const repoMatch = /github\.com\/([^/]+)\/([^/#?]+)/i.exec(repoUrl)
  if (!repoMatch) {
    return null
  }

  const owner = repoMatch[1]
  const repo = repoMatch[2].replace(/\.git$/, '')

  const [repoJson, releaseJson, tagsJson, commitsJson] = await Promise.all([
    fetchGitHubJson(`/repos/${owner}/${repo}`),
    fetchGitHubJson(`/repos/${owner}/${repo}/releases/latest`, true),
    fetchGitHubJson(`/repos/${owner}/${repo}/tags?per_page=1`, true),
    fetchGitHubJson(`/repos/${owner}/${repo}/commits?per_page=1`, true),
  ])

  if (!repoJson) {
    return null
  }

  const latestRef = releaseJson
    ? {
        kind: 'release',
        label: `Release ${releaseJson.tag_name}`,
        title: releaseJson.name || releaseJson.tag_name,
        publishedAt: releaseJson.published_at,
        url: releaseJson.html_url,
      }
    : Array.isArray(tagsJson) && tagsJson[0]
      ? {
          kind: 'tag',
          label: `Tag ${tagsJson[0].name}`,
          title: tagsJson[0].name,
          publishedAt: Array.isArray(commitsJson) && commitsJson[0]
            ? commitsJson[0].commit?.committer?.date ?? repoJson.pushed_at
            : repoJson.pushed_at,
          url: `${repoJson.html_url}/releases/tag/${tagsJson[0].name}`,
        }
      : Array.isArray(commitsJson) && commitsJson[0]
        ? {
            kind: 'commit',
            label: 'Latest commit',
            title: commitsJson[0].sha.slice(0, 7),
            publishedAt: commitsJson[0].commit?.committer?.date ?? repoJson.pushed_at,
            url: commitsJson[0].html_url,
          }
        : null

  return {
    stars: repoJson.stargazers_count,
    openIssues: repoJson.open_issues_count,
    pushedAt: repoJson.pushed_at,
    repoUrl: repoJson.html_url,
    latestRef,
  }
}

function buildStackSpotlight(stackProfile) {
  const highlight = stackProfile.strengths[0] ?? stackProfile.installRealities[0] ?? stackProfile.productProfile
  const latestSignal = stackProfile.live?.latestRef
    ? `${stackProfile.live.latestRef.label} · ${formatDateLabel(stackProfile.live.latestRef.publishedAt)}`
    : `Repo active ${formatDateLabel(stackProfile.live?.pushedAt)}`

  return {
    id: stackProfile.id,
    name: stackProfile.name,
    whyNow: highlight,
    latestSignal,
  }
}

function buildLandingContent({ packSnapshot, stackProfiles, lessonCount, totalLessonMinutes }) {
  const stackNames = stackProfiles.map((stack) => stack.name)
  const stackSentence = humanJoin(stackNames)

  return {
    meta: {
      title: 'PicoMUTX — Real Operator Guidance For Hermes, OpenClaw, NanoClaw, and PicoClaw',
      description:
        `PicoMUTX turns ${packSnapshot.visibleDocCount} builder-pack playbooks, ${lessonCount} guided lessons, and live repo signals across ${stackSentence} into one safer operator path.`,
    },
    nav: {
      brand: 'PicoMUTX',
      brandTag: ' by MUTX',
      cta: 'Pre-register',
    },
    hero: {
      badge: `Docs synced ${packSnapshot.refreshedAt ?? packSnapshot.generatedOn} · ${packSnapshot.visibleDocCount} live playbooks`,
      title: 'Build, deploy, and govern real ',
      titleAccent: `${stackSentence} stacks without stale guesswork.`,
      subtitle:
        `PicoMUTX is grounded in the official install, dashboard, security, and troubleshooting surfaces for ${stackSentence}. It gives founders and operators one guided path instead of another pile of tabs.`,
      cta: 'Pre-Register for Early Access',
      ctaSecondary: 'See pricing',
      meta: `${lessonCount} guided lessons · about ${totalLessonMinutes} minutes of sequenced work · Tailscale-first remote access defaults`,
    },
    trustItems: [
      `${packSnapshot.visibleDocCount} builder-pack docs mapped into one product surface`,
      `${stackProfiles.length} tracked stacks with live repo snapshots`,
      'Safer launch posture: approval-aware tutoring and private-first remote access',
    ],
    problem: {
      eyebrow: 'The Actual Friction',
      title: 'The hard part is not wanting an agent.',
      titleLine2: 'It is keeping up with the moving surface area after you pick a stack.',
      body:
        `Hermes, OpenClaw, NanoClaw, and PicoClaw each have different install paths, auth models, dashboards, and security traps. The product has to translate that moving reality into one sequence you can actually follow.`,
      scenarios: [
        {
          label: '"I do not know which stack fits my job."',
          body: 'Pico starts with fit signals, install realities, and tradeoffs instead of pretending every stack is interchangeable.',
        },
        {
          label: '"The guide I followed is already stale."',
          body: 'Repo releases, runtime floors, and auth paths move fast. The platform should track those changes instead of locking copy in amber.',
        },
        {
          label: '"My runtime works locally, but remote access feels risky."',
          body: 'Dashboards and launchers should not become public just because the first path was the fastest path.',
        },
        {
          label: '"I can install things, but I still do not have an operator loop."',
          body: 'A working agent needs lessons, tutoring, support, monitoring, and approval-aware controls that line up with each other.',
        },
      ],
      close: 'That is the product lane PicoMUTX is filling in.',
    },
    platform: {
      eyebrow: 'What The Platform Now Knows',
      title: 'One product surface fed by actual stack knowledge.',
      body:
        `The app is now being filled from ${packSnapshot.visibleDocCount} pack docs, ${lessonCount} structured lessons, and live repo signals. That means the landing, onboarding, tutor, and support surfaces can start telling the truth about what these stacks actually require.`,
      howItWorks: [
        {
          title: 'Compare stacks with current install and security realities',
          body: `Use live briefs for ${stackSentence} instead of generic “best stack” copy divorced from official docs.`,
        },
        {
          title: 'Move through a real sequence from local success to control',
          body: 'The Academy already encodes the path from install, to persistence, to skills, to monitoring, to approval gates.',
        },
        {
          title: 'Route blockers into evidence-first tutoring and support',
          body: 'Tutor prompts and support lanes now begin from real failure modes pulled from the pack instead of generic motivation copy.',
        },
        {
          title: 'Keep remote access private by default',
          body: 'Tailscale stays the default posture for dashboards, launchers, and API surfaces that should not be open to the public internet.',
        },
      ],
    },
    who: {
      eyebrow: 'Who This Fits',
      title: 'PicoMUTX is for operators who need current truth, not hype.',
      forYouTitle: 'This is for you if…',
      notForYouTitle: 'This is not for you if…',
      forYou: [
        'You need to choose between Hermes, OpenClaw, NanoClaw, or PicoClaw with less wasted motion',
        'You want a guided install-to-operations sequence instead of stitched-together docs',
        'You care about safer remote access and approval-aware control surfaces',
        'You want tutoring and human help tied to the same underlying stack truth',
        'You are willing to produce proof artifacts instead of collecting vague setup feelings',
      ],
      notForYou: [
        'You want broad AI-agent marketing without touching the real install details',
        'You plan to expose dashboards or launchers publicly before you understand the risk boundary',
        'You already have a mature internal control plane and only need custom enterprise governance',
        'You want a toy demo more than a runtime that survives operations',
        'You expect one frozen tutorial to stay accurate while the repos keep shipping',
      ],
    },
    beforeAfter: {
      eyebrow: 'What Changes',
      title: 'What changes when the UI is grounded in live stack facts',
      beforeLabel: 'Before',
      afterLabel: 'After',
      items: [
        {
          before: 'Marketing copy talks about “AI agents” in the abstract',
          after: `The product names ${stackSentence} explicitly and shows why each one exists`,
        },
        {
          before: 'Onboarding is generic even when the lessons are specific',
          after: 'The first moves mirror the actual lesson objectives and proof requirements',
        },
        {
          before: 'Tutor examples are detached from current stack failure modes',
          after: 'Tutor prompts start from real install, dashboard, and launcher breakpoints',
        },
        {
          before: 'A WIP route apologizes for being empty',
          after: 'The route becomes a live build ledger with tracked repos, docs, and remote-access defaults',
        },
      ],
      close: 'The point is not prettier filler. The point is a UI that stays attached to the stack reality underneath it.',
    },
    earlyAccess: {
      eyebrow: 'Current Build State',
      title: 'PicoMUTX is still opening in stages, but the content path is now live.',
      body:
        'Pre-registering now gets you into the release loop while the platform is being filled from the builder pack, Academy data, and current repo surfaces rather than placeholder text.',
      benefits: [
        'Early access to the guided stack map and tutorial flow',
        'Faster feedback loops while the tutor and support surfaces are still sharpening',
        'Visibility into how Hermes, OpenClaw, NanoClaw, and PicoClaw are evolving',
        'A closer line to the product while the content system is still being shaped',
        'First notice when additional surfaces move from placeholder to source-backed',
      ],
    },
    faq: {
      eyebrow: 'Questions',
      title: 'Questions worth answering honestly',
      items: [
        {
          q: 'Do I need to code to use PicoMUTX?',
          a: 'You still need to run real commands and verify real runtime state, but Pico is designed to turn that work into a guided operator path instead of an engineer-only maze.',
        },
        {
          q: 'How does Pico decide between Hermes, OpenClaw, NanoClaw, and PicoClaw?',
          a: 'It uses fit signals, install realities, troubleshooting themes, and live repo status pulled from the builder pack and current official sources.',
        },
        {
          q: 'Does Pico replace the official docs?',
          a: 'No. It compresses them into a product path and keeps links back to the official sources so the stack truth stays inspectable.',
        },
        {
          q: 'Why does Tailscale keep showing up across the product?',
          a: 'Because private tailnet access is usually the safer default for dashboards, launchers, and admin surfaces than exposing them directly to the public internet.',
        },
        {
          q: 'Will this content keep updating as the repos move?',
          a: 'Yes. The new sync path reads the local pack, optional updated packs, and live repo metadata so the content can be regenerated instead of rewritten by hand.',
        },
      ],
    },
    finalCta: {
      eyebrow: 'Early Access · Live Build',
      title: 'Stop treating stack selection and setup drift like a side quest.',
      body:
        'PicoMUTX is being turned into a product surface that names the stacks, tracks the repos, and keeps the operator route visible from first install to safer runtime control.',
      formHeadline: 'Pre-register for PicoMUTX',
      formSubline: 'Join the list while the source-backed build fills in.',
      ctaButton: 'Pre-Register Now',
      formCtaMeta: 'Free to pre-register · No credit card required · Product updates arrive as the live build sharpens',
    },
  }
}

function buildPricingContent({ packSnapshot, stackProfiles, lessonCount }) {
  return {
    pageTitle: 'Choose the product depth you actually need',
    pageSubtitle:
      `The plans map to real product surfaces: ${lessonCount} lessons, grounded tutoring, monitored runtime context, and live stack briefs across ${humanJoin(stackProfiles.map((stack) => stack.name))}.`,
    pageFooter:
      `Current content sync tracks ${packSnapshot.visibleDocCount} pack docs and ${stackProfiles.length} live repos. Enterprise is for teams that need deeper rollout help, identity controls, and direct support.`,
    planDescriptions: {
      free: 'Inspect the stack map, lesson flow, and product truth before you spend.',
      starter: 'Run one serious build lane with full academy access and grounded tutoring.',
      pro: 'Operate multiple live lanes with BYOK, stronger runtime visibility, and faster escalation.',
      enterprise: 'Roll out across a team with SSO, SLA expectations, and direct operator support.',
    },
    truthStrip: [
      `${lessonCount} sequenced Academy lessons`,
      `${packSnapshot.visibleDocCount} visible builder-pack docs`,
      `${stackProfiles.length} tracked stack briefings`,
      'Private-first remote access defaults',
    ],
  }
}

function buildOnboardingContent({ lessons, stackProfiles }) {
  const installLesson = lessons.find((lesson) => lesson.slug === 'install-hermes-locally') ?? lessons[0]
  const firstRunLesson = lessons.find((lesson) => lesson.slug === 'run-your-first-agent') ?? lessons[1] ?? lessons[0]

  return {
    activationChecklist: [
      {
        chapter: '01',
        title: (installLesson?.title ?? 'Install Hermes locally').replace(/\s+locally$/i, ''),
        body: installLesson?.objective ?? installLesson?.summary ?? 'Get the runtime working from a fresh shell.',
      },
      {
        chapter: '02',
        title: firstRunLesson?.title ?? 'Run your first agent',
        body: firstRunLesson?.objective ?? firstRunLesson?.summary ?? 'Run one bounded prompt with a visible answer.',
      },
      {
        chapter: '03',
        title: 'Keep proof',
        body:
          firstRunLesson?.expectedResult ??
          'Save one prompt-and-answer artifact so the first win survives after the terminal closes.',
      },
    ],
    stackSpotlights: stackProfiles.map(buildStackSpotlight),
  }
}

function buildTutorContent() {
  return {
    questionProtocol: [
      'Name the exact step, command, or dashboard action you were on.',
      'Paste the evidence: output, error, transcript, or runtime state.',
      'Ask for the one next move that proves the route is live again.',
    ],
    examplePrompts: [
      'Hermes opens locally but the VPS run fails. What should I verify before changing anything?',
      'OpenClaw onboard completed, but the Control UI still does not load. What is the clean verification path?',
      'NanoClaw v2 `nanoclaw.sh` ran, but the container path still feels broken. What should I isolate first?',
      'PicoClaw launcher works on localhost only. Should I change the bind address or keep it private with Tailscale?',
    ],
  }
}

function buildSupportContent() {
  return {
    lanes: [
      {
        id: 'fixing-existing',
        title: 'Stack or runtime blocker',
        body: 'Use this when a real install, lesson, dashboard, launcher, or approval step stopped in a way the product cannot close alone.',
      },
      {
        id: 'other',
        title: 'Operator walkthrough',
        body: 'Use this when you need a guided session across multiple surfaces instead of one isolated fix.',
      },
    ],
    escalationStandards: [
      {
        label: '01 • Route',
        title: 'Name the stack and surface',
        body: 'Say whether the problem belongs to Hermes, OpenClaw, NanoClaw, PicoClaw, Tutor, Academy, Autopilot, or the hosted account lane.',
      },
      {
        label: '02 • Evidence',
        title: 'Attach the proof packet',
        body: 'Bring the command, dashboard state, launcher state, or approval signal that shows exactly where the path stopped.',
      },
      {
        label: '03 • Return',
        title: 'Ask for the path back into motion',
        body: 'A good escalation should end with the shortest route back into a lesson, tutor answer, or live control action.',
      },
    ],
  }
}

function buildWipContent({ packSnapshot }) {
  return {
    meta: {
      title: 'Live Build Ledger — PicoMUTX',
      description:
        `Inspect the ${packSnapshot.visibleDocCount} builder-pack docs, tracked repo snapshots, and remote-access defaults now feeding the PicoMUTX experience.`,
    },
    title: 'Live build ledger',
    subtitle:
      'This route no longer exists to apologize for being unfinished. It now shows the source material actively feeding Pico: pack docs, Academy lessons, tracked repos, and the remote-access posture they imply.',
    overviewTitle: 'What is already wired in',
    overviewBody:
      'The content path now reads the local builder pack, optional updated pack drops, structured Academy lessons, and live GitHub metadata. This page is the honest place to inspect that feed.',
  }
}

async function buildContent() {
  const packDirectories = await resolvePackDirectories()
  if (!packDirectories.length) {
    throw new Error('No Pico pack directories were found.')
  }

  const existingContent = await readExistingGeneratedContent()
  const fileMap = await buildPackFileMap(packDirectories)
  const manifest = await readJson(MANIFEST_PATH)
  const lessons = await readJson(LESSONS_PATH)
  const readPackFile = async (filename) => {
    const filePath = fileMap.get(filename)
    if (!filePath) {
      throw new Error(`Missing required pack file: ${filename}`)
    }
    return readText(filePath)
  }

  const [readme, updateNotes, tailscaleMarkdown] = await Promise.all([
    readPackFile('README.md'),
    fileMap.get('UPDATE_NOTES.md') ? readPackFile('UPDATE_NOTES.md') : Promise.resolve(''),
    readPackFile('TAILSCALE_PLAYBOOK.md'),
  ])

  const totalLessonMinutes = lessons.reduce(
    (sum, lesson) => sum + (typeof lesson.estimatedMinutes === 'number' ? lesson.estimatedMinutes : 0),
    0,
  )
  const refreshedAt =
    extractFirstDate(updateNotes) ??
    extractFirstDate(readme) ??
    new Date().toISOString().slice(0, 10)

  const packSnapshot = {
    generatedAt: new Date().toISOString(),
    generatedOn: new Date().toISOString().slice(0, 10),
    refreshedAt,
    docCount: manifest.docs.length,
    visibleDocCount: manifest.docs.filter((doc) => doc.visible).length,
    lessonCount: lessons.length,
    totalLessonMinutes,
    sourcePaths: packDirectories.map(displaySourcePath),
    currentProductNotes: extractBullets(getMarkdownSection(readme, 'Current product notes worth knowing')),
  }

  const stackProfiles = []
  for (const stack of STACKS) {
    const markdown = await readPackFile(stack.filename)
    const officialSources = extractBullets(getMarkdownSection(markdown, 'Official sources'))
    const repoUrl = pickOfficialLink(officialSources, /^https:\/\/github\.com\/[^/]+\/[^/]+$/i)
    const docsUrl =
      pickOfficialLink(officialSources, /^https:\/\/(docs\.|[^/]+\/docs)/i) ??
      pickOfficialLink(officialSources, /^https:\/\/[^/]*\/getting-started/i)
    const live = repoUrl ? await fetchGitHubSnapshot(repoUrl) : null
    const cachedStack = existingContent?.stacks?.find((item) => item.id === stack.id)

    const troubleshootingSection =
      getMarkdownSection(markdown, `Common ${stack.name} troubleshooting themes`) ||
      getMarkdownSection(markdown, 'Common troubleshooting themes')

    stackProfiles.push({
      id: stack.id,
      name: stack.name,
      productProfile: extractFirstParagraph(getMarkdownSection(markdown, 'Product profile')),
      strengths: extractBullets(getMarkdownSection(markdown, 'High-level strengths')),
      fitSignals: extractBullets(getMarkdownSection(markdown, 'Fit signals')),
      installRealities: extractBullets(getMarkdownSection(markdown, 'Current install realities')),
      troubleshootingThemes: extractBullets(troubleshootingSection),
      officialSources,
      repoUrl,
      docsUrl,
      live: live ?? cachedStack?.live ?? null,
    })
  }

  const tailscaleSources = extractBullets(getMarkdownSection(tailscaleMarkdown, 'Official sources'))
  const tailscaleDecisionDefaults = extractOrderedSteps(
    getMarkdownSection(tailscaleMarkdown, 'Decision defaults'),
  )
  const remoteAccess = {
    title: 'Private-first remote access',
    why: extractFirstParagraph(
      getMarkdownSection(
        tailscaleMarkdown,
        'Why Tailscale is the default remote-access recommendation',
      ),
    ),
    decisionDefaults: tailscaleDecisionDefaults.length
      ? tailscaleDecisionDefaults
      : [
          'tailscale ssh for shell',
          'tailscale serve for private web surfaces',
          'tailscale funnel only for intentional public exposure',
        ],
    officialSources: tailscaleSources,
    docsUrl: tailscaleSources[0] ?? null,
  }

  return {
    generatedAt: new Date().toISOString(),
    packSnapshot,
    stacks: stackProfiles,
    remoteAccess,
    landing: buildLandingContent({
      packSnapshot,
      stackProfiles,
      lessonCount: lessons.length,
      totalLessonMinutes,
    }),
    pricing: buildPricingContent({
      packSnapshot,
      stackProfiles,
      lessonCount: lessons.length,
    }),
    onboarding: buildOnboardingContent({
      lessons,
      stackProfiles,
    }),
    tutor: buildTutorContent(),
    support: buildSupportContent(),
    wip: buildWipContent({ packSnapshot }),
  }
}

function renderGeneratedModule(content) {
  return `// Generated by scripts/build-pico-content.mjs. Do not edit by hand.\n\nexport const PICO_GENERATED_CONTENT = ${JSON.stringify(content, null, 2)} as const\n`
}

async function main() {
  const content = await buildContent()
  await fs.writeFile(OUTPUT_PATH, renderGeneratedModule(content))
  console.log(`[pico-content] wrote ${path.relative(ROOT, OUTPUT_PATH)}`)
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})

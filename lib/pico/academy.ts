import {
  createDefaultPicoPlatformPreferences,
  normalizeLessonWorkspace,
  normalizePersistedLessonWorkspace,
  normalizePicoPlatformPreferences,
  type PicoLessonWorkspaceState,
  type PicoPlatformPreferences,
} from '@/lib/pico/platformState'

export type PicoPlan = 'free' | 'starter' | 'pro'
export type PicoLessonDifficulty = 'setup' | 'operator' | 'builder'

export type PicoLessonStep = {
  title: string
  body: string
  command?: string
  note?: string
}

export type PicoLesson = {
  slug: string
  title: string
  summary: string
  level: number
  track: string
  estimatedMinutes: number
  difficulty: PicoLessonDifficulty
  objective: string
  prerequisites: string[]
  outcome: string
  expectedResult: string
  validation: string
  xp: number
  steps: PicoLessonStep[]
  troubleshooting: string[]
  nextLesson?: string
  milestoneEvents?: string[]
}

export type PicoLevel = {
  id: number
  title: string
  objective: string
  projectOutcome: string
  completionState: string
  xpReward: number
  badge: string
  recommendedNextStep: string
}

export type PicoTrack = {
  slug: string
  title: string
  outcome: string
  intro: string
  lessons: string[]
  checklist: string[]
  nextTrack?: string
}

export type PicoPlanFeature =
  | 'academy'
  | 'tutor'
  | 'project_limit'
  | 'monitored_agents'
  | 'alerts'
  | 'approvals'
  | 'retention'

export type PicoProgressState = {
  version: number
  startedAt: string
  updatedAt: string
  selectedTrack: string | null
  startedLessons: string[]
  completedLessons: string[]
  milestoneEvents: string[]
  tutorQuestions: number
  supportRequests: number
  helpfulResponses: number
  sharedProjects: string[]
  lessonWorkspaces: Record<string, PicoLessonWorkspaceState>
  platform: PicoPlatformPreferences
  autopilot: {
    costThresholdPercent: number
    alertChannel: 'in_app' | 'email' | 'webhook'
    approvalGateEnabled: boolean
    approvalRequestIds: string[]
    lastThresholdBreachAt: string | null
  }
}

export type PicoCapabilityUnlock = {
  id: string
  title: string
  description: string
  href: string
  actionLabel: string
  unlockEvent: string
}

export type PicoRealAction = {
  id: string
  title: string
  description: string
  href: string
  actionLabel: string
}

export type PicoDerivedProgress = {
  xp: number
  currentLevel: number
  totalLessons: number
  completedLessonCount: number
  completedTrackSlugs: string[]
  badges: string[]
  unlockedLessonSlugs: string[]
  unlockedTrackSlugs: string[]
  unlockedCapabilities: PicoCapabilityUnlock[]
  nextCapability: PicoCapabilityUnlock | null
  nextLesson: PicoLesson | null
}

export const PICO_LESSON_EVIDENCE_MIN_LENGTH = 12

export type PicoLessonCompletionBlocker =
  | 'unknown_lesson'
  | 'prerequisite'
  | 'steps'
  | 'evidence'
  | 'persistence'

export type PicoLessonCompletionStatus = {
  canComplete: boolean
  isComplete: boolean
  blocker: PicoLessonCompletionBlocker | null
  message: string
  completedStepCount: number
  requiredStepCount: number
}

export const PICO_MILESTONE_XP: Record<string, number> = {
  account_created: 20,
  first_tutorial_started: 15,
  first_tutorial_completed: 25,
  first_agent_run: 40,
  successful_deployment: 60,
  first_skill_added: 50,
  first_workflow_built: 70,
  first_monitoring_event_seen: 45,
  first_alert_configured: 45,
  first_approval_workflow_exercised: 60,
  project_shared: 40,
  helpful_community_response: 35,
}

export const PICO_PLAN_MATRIX: Record<PicoPlan, Record<PicoPlanFeature, string>> = {
  free: {
    academy: 'Full academy access',
    tutor: 'Read-only Academy guidance',
    project_limit: '1 active project',
    monitored_agents: 'Read-only runtime overview',
    alerts: 'In-app threshold alerts',
    approvals: 'Approval workflow overview',
    retention: '7-day product memory',
  },
  starter: {
    academy: 'Full academy access',
    tutor: 'Priority tutor routing',
    project_limit: '3 active projects',
    monitored_agents: '1 monitored agent',
    alerts: 'In-app plus email-ready config',
    approvals: 'One approval gate',
    retention: '30-day run and alert history',
  },
  pro: {
    academy: 'Full academy access',
    tutor: 'Priority tutor routing',
    project_limit: 'Unlimited projects',
    monitored_agents: 'Multiple monitored agents',
    alerts: 'Stronger alert routing',
    approvals: 'Multiple approval gates',
    retention: '90-day run and alert history',
  },
}

export const PICO_LEVELS: PicoLevel[] = [
  {
    id: 0,
    title: 'Setup',
    objective: 'Get Hermes installed and prove the runtime answers a real prompt.',
    projectOutcome: 'A working local agent that responds on command.',
    completionState: 'Hermes runs locally and returns a sane answer.',
    xpReward: 120,
    badge: 'First Spark',
    recommendedNextStep: 'Deploy the same runtime somewhere persistent.',
  },
  {
    id: 1,
    title: 'Deployment',
    objective: 'Move the agent off the laptop and keep it alive.',
    projectOutcome: 'A persistent agent on a VPS or always-on box.',
    completionState: 'The agent survives shell exits and accepts remote traffic.',
    xpReward: 170,
    badge: 'Runtime Ranger',
    recommendedNextStep: 'Add one useful capability.',
  },
  {
    id: 2,
    title: 'Capability',
    objective: 'Teach the agent a concrete skill with a bounded job.',
    projectOutcome: 'A useful skill or tool call bound to a real task.',
    completionState: 'The agent completes one useful workflow step.',
    xpReward: 150,
    badge: 'Skillsmith',
    recommendedNextStep: 'Automate the cadence.',
  },
  {
    id: 3,
    title: 'Automation',
    objective: 'Run the agent on a repeatable schedule.',
    projectOutcome: 'A scheduled workflow that fires without babysitting.',
    completionState: 'The workflow runs on a clock and logs the result.',
    xpReward: 160,
    badge: 'Loop Builder',
    recommendedNextStep: 'Turn on visibility.',
  },
  {
    id: 4,
    title: 'Production',
    objective: 'See the run history and catch failure modes early.',
    projectOutcome: 'A user can inspect runs, failures, and runtime state.',
    completionState: 'Run activity appears in Autopilot.',
    xpReward: 170,
    badge: 'Signal Hunter',
    recommendedNextStep: 'Add cost and approval controls.',
  },
  {
    id: 5,
    title: 'Control',
    objective: 'Save a cost threshold and exercise the approval workflow with a real request.',
    projectOutcome: 'The operator can inspect spend and deliberately resolve a queued action.',
    completionState: 'A threshold is saved and one approval workflow has been exercised.',
    xpReward: 210,
    badge: 'Approval Reviewer',
    recommendedNextStep: 'Ship a deeper pattern.',
  },
  {
    id: 6,
    title: 'Systems',
    objective: 'Ship a reusable production pattern, not a toy demo.',
    projectOutcome: 'One serious workflow a founder could run in production.',
    completionState: 'A stronger pattern ships with a real saved output and review page.',
    xpReward: 240,
    badge: 'Pattern Builder',
    recommendedNextStep: 'Move from one agent to a governed fleet.',
  },
]

export const PICO_TRACKS: PicoTrack[] = [
  {
    slug: 'first-agent',
    title: 'Track A — First Agent',
    outcome: 'Hermes runs and answers real prompts.',
    intro: 'This is the fast path from zero to a working local runtime.',
    lessons: ['install-hermes-locally', 'run-your-first-agent'],
    checklist: [
      'Hermes installed',
      'Model/provider configured',
      'One successful response saved',
    ],
    nextTrack: 'deployed-agent',
  },
  {
    slug: 'deployed-agent',
    title: 'Track B — Deployed Agent',
    outcome: 'The runtime stays alive somewhere persistent.',
    intro: 'Move from laptop demo to a process that survives sleep and reboots.',
    lessons: [
      'deploy-hermes-on-a-vps',
      'keep-your-agent-alive',
      'connect-a-messaging-layer',
    ],
    checklist: [
      'VPS or persistent box online',
      'Service restarts cleanly',
      'Messaging ingress connected',
    ],
    nextTrack: 'useful-workflow',
  },
  {
    slug: 'useful-workflow',
    title: 'Track C — Useful Workflow',
    outcome: 'The agent performs a bounded job that matters.',
    intro: 'Now stop playing with prompts and build one useful capability.',
    lessons: ['add-your-first-skill', 'create-a-scheduled-workflow'],
    checklist: [
      'At least one custom skill installed',
      'One scheduled workflow configured',
      'One repeatable workflow completed without manual babysitting',
    ],
    nextTrack: 'controlled-agent',
  },
  {
    slug: 'controlled-agent',
    title: 'Track D — Controlled Agent',
    outcome: 'The runtime is visible and reviewable.',
    intro: 'This is where live runs, costs, and approvals become easy to review.',
    lessons: [
      'see-your-agent-activity',
      'set-a-cost-threshold',
      'add-an-approval-gate',
    ],
    checklist: [
      'Recent activity visible',
      'Cost threshold stored',
      'Approval request flow exercised',
    ],
    nextTrack: 'production-pattern',
  },
  {
    slug: 'production-pattern',
    title: 'Track E — Production Pattern',
    outcome: 'A stronger, reusable workflow is live.',
    intro: 'Take the foundations and ship a pattern someone would actually pay for.',
    lessons: ['build-a-lead-response-agent', 'build-a-document-processing-agent'],
    checklist: [
      'One business workflow accepts real structured input',
      'Structured input accepted',
      'Output validated',
      'Runs visible in Autopilot',
    ],
  },
]

export const PICO_RELEASE_NOTES = [
  {
    title: 'Pico shell lands inside MUTX',
    date: '2026-04-11',
    body: 'Academy, tutor, support, and Autopilot now live in one product area instead of a marketing-only landing page.',
  },
  {
    title: 'Progress persistence switched to user settings',
    date: '2026-04-11',
    body: 'Authenticated users sync progress to the backend while anonymous users keep a local fallback.',
  },
  {
    title: 'Autopilot now reads real MUTX data',
    date: '2026-04-11',
    body: 'Runs, alerts, budgets, and approvals are pulled from live MUTX routes.',
  },
] as const

export const PICO_SHOWCASE_PATTERNS = [
  {
    title: 'Lead-response workflow',
    lessonSlug: 'build-a-lead-response-agent',
    summary: 'Takes an inbound lead, drafts the first reply, and waits for approval before the risky send.',
  },
  {
    title: 'Document triage workflow',
    lessonSlug: 'build-a-document-processing-agent',
    summary: 'Ingests files, extracts the useful parts, tags the result, and shows runs for review.',
  },
  {
    title: 'Daily workflow loop',
    lessonSlug: 'create-a-scheduled-workflow',
    summary: 'Turns one useful prompt into a repeatable habit with logs and timing.',
  },
] as const

export const PICO_BADGE_RULES = [
  {
    id: 'first-spark',
    label: 'First Spark',
    test: (completedLessons: Set<string>) =>
      completedLessons.has('install-hermes-locally') && completedLessons.has('run-your-first-agent'),
  },
  {
    id: 'runtime-ranger',
    label: 'Runtime Ranger',
    test: (completedLessons: Set<string>) =>
      completedLessons.has('deploy-hermes-on-a-vps') && completedLessons.has('keep-your-agent-alive'),
  },
  {
    id: 'skillsmith',
    label: 'Skillsmith',
    test: (completedLessons: Set<string>) => completedLessons.has('add-your-first-skill'),
  },
  {
    id: 'loop-builder',
    label: 'Loop Builder',
    test: (completedLessons: Set<string>) => completedLessons.has('create-a-scheduled-workflow'),
  },
  {
    id: 'gatekeeper',
    label: 'Approval Reviewer',
    test: (completedLessons: Set<string>, milestoneEvents: Set<string>) =>
      completedLessons.has('set-a-cost-threshold') &&
      completedLessons.has('add-an-approval-gate') &&
      milestoneEvents.has('first_approval_workflow_exercised'),
  },
  {
    id: 'pattern-operator',
    label: 'Pattern Operator',
    test: (completedLessons: Set<string>) =>
      completedLessons.has('build-a-lead-response-agent') ||
      completedLessons.has('build-a-document-processing-agent'),
  },
] as const

export const PICO_CAPABILITY_UNLOCKS: PicoCapabilityUnlock[] = [
  {
    id: 'cap-deploy-runtime',
    title: 'Persistent runtime unlocked',
    description:
      'You proved the local loop. Next move: get the same agent onto a box that stays awake.',
    href: '/academy/deploy-hermes-on-a-vps',
    actionLabel: 'Deploy the runtime',
    unlockEvent: 'first_tutorial_completed',
  },
  {
    id: 'cap-live-runs',
    title: 'Live run visibility unlocked',
    description:
      'A real run exists now. Open Autopilot and inspect the result before you pretend the loop is stable.',
    href: '/autopilot',
    actionLabel: 'Inspect live activity',
    unlockEvent: 'first_agent_run',
  },
  {
    id: 'cap-ingress',
    title: 'Remote ingress unlocked',
    description:
      'The runtime lives somewhere persistent. Give it one real input path so it can do useful work.',
    href: '/academy/connect-a-messaging-layer',
    actionLabel: 'Connect a messaging layer',
    unlockEvent: 'successful_deployment',
  },
  {
    id: 'cap-scheduling',
    title: 'Scheduling unlocked',
    description:
      'One useful skill is in place. Now run it on a cadence so the product becomes a habit.',
    href: '/academy/create-a-scheduled-workflow',
    actionLabel: 'Schedule the workflow',
    unlockEvent: 'first_skill_added',
  },
  {
    id: 'cap-monitoring',
    title: 'Monitoring unlocked',
    description:
      'A workflow runs now. Time to watch the thing instead of hoping it behaves.',
    href: '/academy/see-your-agent-activity',
    actionLabel: 'See agent activity',
    unlockEvent: 'first_workflow_built',
  },
  {
    id: 'cap-cost-controls',
    title: 'Cost control unlocked',
    description:
      'You can see the run history. Set a spend guardrail before volume turns into regret.',
    href: '/academy/set-a-cost-threshold',
    actionLabel: 'Set a cost threshold',
    unlockEvent: 'first_monitoring_event_seen',
  },
  {
    id: 'cap-approvals',
    title: 'Approval workflow available',
    description:
      'A saved threshold is only a preference. Exercise one real approval request and verify the runtime behavior.',
    href: '/academy/add-an-approval-gate',
    actionLabel: 'Exercise the approval workflow',
    unlockEvent: 'first_alert_configured',
  },
  {
    id: 'cap-production-pattern',
    title: 'Production pattern unlocked',
    description:
      'The approval workflow was exercised. Ship a workflow that looks like a product, while treating enforcement as runtime-owned truth.',
    href: '/academy/build-a-document-processing-agent',
    actionLabel: 'Ship the production pattern',
    unlockEvent: 'first_approval_workflow_exercised',
  },
] as const

export const PICO_LESSONS: PicoLesson[] = [
  {
    slug: 'install-hermes-locally',
    title: 'Install Hermes locally',
    summary: 'Install Hermes, prove the command works from a fresh shell, and leave this lesson with one working local runtime.',
    level: 0,
    track: 'first-agent',
    estimatedMinutes: 8,
    difficulty: 'setup',
    objective: 'Get one clean local Hermes install working end to end.',
    prerequisites: [],
    outcome: 'A local Hermes CLI that opens cleanly from a fresh shell.',
    expectedResult: 'Running `command -v hermes && hermes` from a fresh shell succeeds.',
    validation: 'Open a brand-new shell and run `command -v hermes && hermes`. If the command is missing or the CLI errors immediately, this lesson is not done.',
    xp: 60,
    milestoneEvents: ['first_tutorial_started'],
    steps: [
      {
        title: 'Install Hermes',
        body: 'Run the install command exactly once. Do not compare package managers. Do not branch into extra tooling.',
        command: 'curl -fsSL https://hermes.nousresearch.com/install.sh | bash',
      },
      {
        title: 'Verify the binary from a fresh shell',
        body: 'Close the shell, open a new one, then prove the binary is actually on PATH.',
        command: 'command -v hermes',
      },
      {
        title: 'Open Hermes and finish one provider setup',
        body: 'Launch the CLI and complete exactly one provider path until the CLI is usable. Do not leave this lesson with two half-configured providers.',
        command: 'hermes',
      },
    ],
    troubleshooting: [
      'If `command -v hermes` returns nothing, restart the shell and check that the install path was added to PATH.',
      'If `hermes` opens and immediately errors on missing credentials, finish one provider setup before moving on.',
      'If the install script fails on a locked-down machine, switch to a user-local install path and rerun the verification step.',
    ],
    nextLesson: 'run-your-first-agent',
  },
  {
    slug: 'run-your-first-agent',
    title: 'Run your first agent',
    summary: 'Run one real prompt, get one visible answer, and save the transcript.',
    level: 0,
    track: 'first-agent',
    estimatedMinutes: 6,
    difficulty: 'setup',
    objective: 'Prove the runtime can answer one bounded prompt with the provider you just configured.',
    prerequisites: ['install-hermes-locally'],
    outcome: 'One saved prompt-and-answer transcript.',
    expectedResult: 'Hermes answers one small prompt and the transcript is saved in a file you can reopen.',
    validation: 'Run one bounded prompt and save both the prompt and answer in a file such as `~/pico-first-run.txt`.',
    xp: 60,
    milestoneEvents: ['first_tutorial_completed', 'first_agent_run'],
    steps: [
      {
        title: 'Start Hermes from a clean shell',
        body: 'Launch the runtime from a new shell so you know you are testing the real install.',
        command: 'hermes',
      },
      {
        title: 'Send one bounded prompt',
        body: 'Use a tiny prompt with an obvious answer. Do not test creativity. Test that the runtime works.',
        command: 'Prompt: Give me exactly 3 next steps to test this runtime locally.',
      },
      {
        title: 'Save the transcript',
        body: 'Write the prompt and the answer into one file so the artifact survives after the terminal closes.',
        command: 'printf "Prompt: Give me exactly 3 next steps to test this runtime locally.\nAnswer: <paste the actual answer here>\n" > ~/pico-first-run.txt',
      },
    ],
    troubleshooting: [
      'If the answer times out, switch to a faster model first and rerun the same bounded prompt.',
      'If the answer is nonsense, confirm which provider and model Hermes is actually using before changing the prompt.',
      'If the CLI will not start, go back to the install lesson. This lesson depends on a working binary.',
    ],
    nextLesson: 'deploy-hermes-on-a-vps',
  },
  {
    slug: 'deploy-hermes-on-a-vps',
    title: 'Deploy Hermes on a VPS',
    summary: 'Put Hermes on an always-on host and prove the remote runtime opens there too.',
    level: 1,
    track: 'deployed-agent',
    estimatedMinutes: 30,
    difficulty: 'operator',
    objective: 'Move the runtime from your laptop to one persistent machine you control.',
    prerequisites: ['run-your-first-agent'],
    outcome: 'A remote box where Hermes opens cleanly over SSH.',
    expectedResult: 'SSH into the host and run `hermes` successfully.',
    validation: 'From your machine SSH into the host and run `command -v hermes && hermes`. If that fails, the deployment is not done.',
    xp: 60,
    milestoneEvents: ['successful_deployment'],
    steps: [
      {
        title: 'Reach the host over SSH',
        body: 'Use one box you control and prove SSH works before you touch Hermes.',
        command: 'ssh user@your-box',
      },
      {
        title: 'Install Hermes on the host',
        body: 'Run the same install path on the remote box. Keep the environment boring.',
        command: 'curl -fsSL https://hermes.nousresearch.com/install.sh | bash',
      },
      {
        title: 'Verify the remote runtime',
        body: 'From the SSH session prove the binary exists and the CLI opens.',
        command: 'command -v hermes && hermes',
      },
    ],
    troubleshooting: [
      'If SSH is unstable, fix the host first. Hermes is not the problem yet.',
      'If the install works locally but not remotely, compare PATH and environment variables before changing commands.',
      'If the remote host is missing provider credentials, add only the minimum config needed for the same provider you already proved locally.',
    ],
    nextLesson: 'keep-your-agent-alive',
  },
  {
    slug: 'keep-your-agent-alive',
    title: 'Keep your agent alive between sessions',
    summary: 'Create one real service definition so logout does not kill the runtime.',
    level: 1,
    track: 'deployed-agent',
    estimatedMinutes: 25,
    difficulty: 'operator',
    objective: 'Turn the remote runtime into a process that survives disconnects and reboots.',
    prerequisites: ['deploy-hermes-on-a-vps'],
    outcome: 'A saved service definition or tmux command that keeps Hermes alive.',
    expectedResult: 'You can disconnect, reconnect, and find the runtime still running.',
    validation: 'Start the service, disconnect, reconnect, and verify the Hermes process still exists.',
    xp: 55,
    steps: [
      {
        title: 'Write the systemd unit file',
        body: 'Create the service file now. If no file exists at the end of the lesson, you shipped nothing.',
        command: 'sudo nano /etc/systemd/system/hermes.service',
        note: '[Unit]\nDescription=Hermes Runtime\nAfter=network.target\n\n[Service]\nUser=<your-user>\nWorkingDirectory=/home/<your-user>\nExecStart=/home/<your-user>/.local/bin/hermes\nRestart=always\nRestartSec=5\n\n[Install]\nWantedBy=multi-user.target',
      },
      {
        title: 'Enable and start the service',
        body: 'Reload systemd, enable the unit, and start it once.',
        command: 'sudo systemctl daemon-reload && sudo systemctl enable --now hermes',
      },
      {
        title: 'Prove it survives without your shell',
        body: 'Check status, disconnect, reconnect, then check again.',
        command: 'sudo systemctl status hermes --no-pager',
      },
    ],
    troubleshooting: [
      'If the unit fails under systemd but works manually, compare PATH, WorkingDirectory, and provider env vars.',
      'If the service restarts forever, fix the Hermes command first instead of increasing restart counts.',
      'If you cannot use systemd, use one named tmux session and document the exact session name before moving on.',
    ],
    nextLesson: 'connect-a-messaging-layer',
  },
  {
    slug: 'connect-a-messaging-layer',
    title: 'Connect a messaging layer',
    summary: 'Give the runtime one real ingress path so you can reach it without SSH.',
    level: 1,
    track: 'deployed-agent',
    estimatedMinutes: 30,
    difficulty: 'operator',
    objective: 'Attach one real inbound channel to the running agent.',
    prerequisites: ['keep-your-agent-alive'],
    outcome: 'One tested ingress path into the runtime.',
    expectedResult: 'A real input reaches the runtime from the chosen channel and produces one visible reply.',
    validation: 'Send one real test input through the chosen ingress and record the exact reply.',
    xp: 55,
    steps: [
      {
        title: 'Pick the one channel you already have credentials for',
        body: 'Use one ingress only. The goal is a working input path, not channel coverage.',
        command: 'Example channels: Telegram bot token, Discord bot token, Slack app token, or one webhook endpoint.',
      },
      {
        title: 'Store the minimum credentials on the runtime host',
        body: 'Put only the required secrets on the box and keep them out of chat logs.',
        command: 'export CHANNEL_TOKEN=<your-token>',
      },
      {
        title: 'Send one real inbound test',
        body: 'Trigger the ingress once and verify the runtime replies exactly once in the expected place.',
        command: 'Send one short real message through the selected channel, then record the reply text.',
      },
    ],
    troubleshooting: [
      'If the channel is silent, verify token validity and webhook reachability before changing agent logic.',
      'If you get duplicate replies, stop the duplicate runtime or duplicate webhook before continuing.',
      'If the channel reaches the runtime but no reply returns, inspect the running service logs first.',
    ],
    nextLesson: 'add-your-first-skill',
  },
  {
    slug: 'add-your-first-skill',
    title: 'Add your first skill/tool',
    summary: 'Install one narrow capability the agent can reuse without human hand-holding.',
    level: 2,
    track: 'useful-workflow',
    estimatedMinutes: 25,
    difficulty: 'builder',
    objective: 'Teach Hermes one bounded task it can perform on demand.',
    prerequisites: ['connect-a-messaging-layer'],
    outcome: 'One working skill or tool the agent can call repeatedly.',
    expectedResult: 'The agent uses the skill once on real input and returns a useful result.',
    validation: 'Trigger the skill once and save the exact input and output it produced.',
    xp: 70,
    milestoneEvents: ['first_skill_added'],
    steps: [
      {
        title: 'Pick one narrow job',
        body: 'Choose one repeated task that is low-risk and obvious when it works.',
        command: 'Example jobs: summarize one note, classify one lead, extract one field set, or rewrite one reply.',
      },
      {
        title: 'Install or create the skill',
        body: 'Use the existing Hermes skill flow and keep the scope brutally small.',
        command: 'Use the single Hermes skill path you already trust. Do not bundle multiple skills into this lesson.',
      },
      {
        title: 'Run the skill on real-shaped input',
        body: 'Call the skill with input that looks like production, then save the result.',
        command: 'Run the skill once and write the resulting artifact to ~/pico-first-skill.txt',
      },
    ],
    troubleshooting: [
      'If the skill fails, test the underlying command or API outside Hermes first.',
      'If the output is noisy, cut scope from the skill instead of adding more prompt text.',
      'If the task can send or mutate something risky, keep the skill read-only until the approval lesson.',
    ],
    nextLesson: 'create-a-scheduled-workflow',
  },
  {
    slug: 'create-a-scheduled-workflow',
    title: 'Create a scheduled workflow',
    summary: 'Put the useful job on a clock and prove one scheduled execution leaves a visible trace.',
    level: 3,
    track: 'useful-workflow',
    estimatedMinutes: 20,
    difficulty: 'builder',
    objective: 'Turn the working skill into one repeatable scheduled job.',
    prerequisites: ['add-your-first-skill'],
    outcome: 'One saved schedule that runs the job without manual kickoff.',
    expectedResult: 'A scheduled execution fires and leaves a visible result you can point to later.',
    validation: 'Trigger one schedule tick and capture the resulting log, output file, or run record.',
    xp: 75,
    milestoneEvents: ['first_workflow_built'],
    steps: [
      {
        title: 'Pick one sane cadence',
        body: 'Choose a schedule that matches the job. Daily is enough unless you can defend something tighter.',
        command: 'Example cron: 0 9 * * *',
      },
      {
        title: 'Save the scheduled command',
        body: 'Create the exact cron or scheduler entry now. A schedule that only exists in your head is fake.',
        command: '(crontab -l 2>/dev/null; echo "0 9 * * * /home/<your-user>/.local/bin/hermes") | crontab -',
      },
      {
        title: 'Force one execution and capture the result',
        body: 'Do not wait all day. Trigger the workflow once and save the output location.',
        command: '/home/<your-user>/.local/bin/hermes',
      },
    ],
    troubleshooting: [
      'If the schedule never fires, verify timezone and crontab ownership before touching Hermes.',
      'If the job fires twice, remove the duplicate scheduler entry before continuing.',
      'If the scheduler cannot see secrets, export them in the execution environment explicitly.',
    ],
    nextLesson: 'see-your-agent-activity',
  },
  {
    slug: 'see-your-agent-activity',
    title: 'See your agent activity',
    summary: 'Open Autopilot, inspect one real run or empty state, and record the first runtime note.',
    level: 4,
    track: 'controlled-agent',
    estimatedMinutes: 20,
    difficulty: 'operator',
    objective: 'Leave Autopilot with one concrete runtime note you can name later.',
    prerequisites: ['create-a-scheduled-workflow'],
    outcome: 'One recorded runtime note: a run id, an alert type, or an empty-state fact.',
    expectedResult: 'You can point to a concrete runtime note instead of saying "it seems fine".',
    validation: 'Open Autopilot and write down one runtime note in a file such as `~/pico-runtime-checkpoint.txt`.',
    xp: 70,
    milestoneEvents: ['first_monitoring_event_seen'],
    steps: [
      {
        title: 'Open Autopilot',
        body: 'Go to Autopilot and start with runs. Do not browse the whole page yet.',
        command: 'Open /pico/autopilot',
      },
      {
        title: 'Inspect one runtime note',
        body: 'Capture one run id, alert type, or empty-state fact. One is enough for this lesson.',
        command: 'Example artifact line: run_id=<paste>, alert_type=<paste>, or empty_state=no_live_agent',
      },
      {
        title: 'Save the checkpoint',
        body: 'Store that note in a file so you can compare later states against something concrete.',
        command: 'printf "checkpoint=<paste your first runtime note here>\n" > ~/pico-runtime-checkpoint.txt',
      },
    ],
    troubleshooting: [
      'If no runs appear, verify the scheduled workflow really executed before blaming Autopilot.',
      'If auth blocks the view, sign in first. This lesson depends on live runtime data.',
      'If the page is empty, record the empty-state fact. Empty is still useful.',
    ],
    nextLesson: 'set-a-cost-threshold',
  },
  {
    slug: 'set-a-cost-threshold',
    title: 'Set a cost threshold',
    summary: 'Store one budget line in the sand and verify it survives reload.',
    level: 5,
    track: 'controlled-agent',
    estimatedMinutes: 15,
    difficulty: 'operator',
    objective: 'Define one cost threshold you are willing to tolerate before the runtime gets noisy.',
    prerequisites: ['see-your-agent-activity'],
    outcome: 'One saved threshold tied to Autopilot.',
    expectedResult: 'The saved threshold persists after reload and appears in the product state.',
    validation: 'Save a threshold, reload the page, and confirm the same value is still there.',
    xp: 65,
    milestoneEvents: ['first_alert_configured'],
    steps: [
      {
        title: 'Choose one threshold value',
        body: 'Pick one number you can defend right now. Use 75 if you do not have a better reason.',
        command: 'Threshold: 75',
      },
      {
        title: 'Save it in Autopilot',
        body: 'Enter the number and save it once. Do not keep tweaking it during the lesson.',
        command: 'Open /pico/autopilot and click Save threshold',
      },
      {
        title: 'Reload and verify persistence',
        body: 'Reload the page and confirm the same threshold still appears.',
        command: 'Reload /pico/autopilot and verify the threshold field still shows your saved value.',
      },
    ],
    troubleshooting: [
      'If the threshold disappears after reload, fix persistence before trusting any cost control.',
      'If no live budget exists yet, still save the threshold but treat cost awareness as incomplete.',
      'If you are guessing wildly, choose a lower threshold and move on.',
    ],
    nextLesson: 'add-an-approval-gate',
  },
  {
    slug: 'add-an-approval-gate',
    title: 'Exercise the approval workflow',
    summary: 'Create one real approval request and resolve it on purpose without inferring enforcement.',
    level: 5,
    track: 'controlled-agent',
    estimatedMinutes: 20,
    difficulty: 'operator',
    objective: 'Exercise the approval queue before trusting any consequential runtime behavior.',
    prerequisites: ['set-a-cost-threshold'],
    outcome: 'One working approval request and one deliberate resolution.',
    expectedResult: 'A pending approval exists and you can approve or reject it intentionally.',
    validation: 'Create one approval request and resolve it from the queue.',
    xp: 75,
    milestoneEvents: ['first_approval_workflow_exercised'],
    steps: [
      {
        title: 'Pick one risky action worth reviewing',
        body: 'Use one outbound send, publish, or state-changing action so the review request is meaningful.',
        command: 'Example reviewed action: outbound_message_send',
      },
      {
        title: 'Create the approval request',
        body: 'Create the request in the approval queue. This proves the workflow, not runtime enforcement.',
        command: 'Open /pico/autopilot and create one approval request for the risky action.',
      },
      {
        title: 'Resolve the request intentionally',
        body: 'Approve or reject the request once and record what the queue shows after the action.',
        command: 'Use the Approve or Reject action in /pico/autopilot and record the final status.',
      },
    ],
    troubleshooting: [
      'If approvals are unavailable, say so plainly. The runtime is not ready for unattended risky actions yet.',
      'If everybody can approve everything, the workflow exists but the policy is weak. Record that gap and keep going.',
      'If you review trivial noise, the queue becomes spam and people stop trusting it.',
    ],
    nextLesson: 'build-a-lead-response-agent',
  },
  {
    slug: 'build-a-lead-response-agent',
    title: 'Build a lead-response agent',
    summary: 'Turn one inbound lead into one draft reply and keep the send behind approval.',
    level: 6,
    track: 'production-pattern',
    estimatedMinutes: 35,
    difficulty: 'builder',
    objective: 'Ship one workflow a founder would actually use this week.',
    prerequisites: ['add-an-approval-gate'],
    outcome: 'A lead-response workflow with a gated outbound step.',
    expectedResult: 'Lead data becomes a draft reply or structured summary, and the risky send stays gated.',
    validation: 'Run one lead through the workflow end to end and save the drafted result.',
    xp: 90,
    steps: [
      {
        title: 'Create one lead payload',
        body: 'Use the smallest useful shape and keep it fixed for the whole lesson.',
        command: 'printf "name=Alex\nsource=website\nintent=book demo\nnext_step=send reply\n" > ~/pico-lead.txt',
      },
      {
        title: 'Generate one draft reply',
        body: 'Run the workflow on that lead payload and produce one draft reply or one structured summary.',
        command: 'Feed ~/pico-lead.txt into your Hermes lead workflow and save the result to ~/pico-lead-draft.txt',
      },
      {
        title: 'Put the outbound action behind approval',
        body: 'Do not send automatically. Force the workflow through the approval queue once.',
        command: 'Create one approval request for the outbound send using the drafted reply as payload.',
      },
    ],
    troubleshooting: [
      'If the draft is generic, tighten the lead payload before touching the prompt.',
      'If the workflow is slow, remove extra steps before you optimize models.',
      'If you do not need outbound send yet, stop at a gated draft and call that the artifact.',
    ],
    nextLesson: 'build-a-document-processing-agent',
  },
  {
    slug: 'build-a-document-processing-agent',
    title: 'Build a document-processing agent',
    summary: 'Ingest one document, extract the few fields that matter, and show one reviewed output.',
    level: 6,
    track: 'production-pattern',
    estimatedMinutes: 40,
    difficulty: 'builder',
    objective: 'Ship one stronger production pattern around unstructured input.',
    prerequisites: ['add-an-approval-gate'],
    outcome: 'One document-processing workflow with a saved structured output.',
    expectedResult: 'A real document becomes a structured summary, checklist, or tagged record you can inspect.',
    validation: 'Process one real document and save the extracted output artifact.',
    xp: 95,
    steps: [
      {
        title: 'Pick one document and freeze the schema',
        body: 'Use one real file type and decide the exact fields you need before extraction starts.',
        command: 'Example output schema: title, owner, due_date, summary, next_action',
      },
      {
        title: 'Run extraction once',
        body: 'Extract only the fields that matter downstream. Ignore every nice-to-have field.',
        command: 'Run the workflow on one real document and save the structured output to ~/pico-document-output.txt',
      },
      {
        title: 'Review the saved output',
        body: 'Read the output and confirm it is usable without more cleanup.',
        command: 'cat ~/pico-document-output.txt',
      },
    ],
    troubleshooting: [
      'If extraction quality is weak, reduce document variety before adding more prompting.',
      'If the output is hard to inspect, your schema is too wide. Cut fields.',
      'If you cannot tell whether the result is usable, the workflow is not ready to automate further.',
    ],
  },
]
const DEFAULT_AUTOPILOT_STATE: PicoProgressState['autopilot'] = {
  costThresholdPercent: 75,
  alertChannel: 'in_app',
  approvalGateEnabled: false,
  approvalRequestIds: [],
  lastThresholdBreachAt: null,
}

export function createDefaultPicoProgress(): PicoProgressState {
  const now = new Date().toISOString()
  return {
    version: 1,
    startedAt: now,
    updatedAt: now,
    selectedTrack: null,
    startedLessons: [],
    completedLessons: [],
    milestoneEvents: [],
    tutorQuestions: 0,
    supportRequests: 0,
    helpfulResponses: 0,
    sharedProjects: [],
    lessonWorkspaces: {},
    platform: createDefaultPicoPlatformPreferences(),
    autopilot: { ...DEFAULT_AUTOPILOT_STATE },
  }
}

function uniqueStrings(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return Array.from(new Set(value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)))
}

function normalizeLessonWorkspaceMap(value: unknown): Record<string, PicoLessonWorkspaceState> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }

  const entries = Object.entries(value as Record<string, unknown>)
  return Object.fromEntries(
    entries
      .filter(([key]) => typeof key === 'string' && key.trim().length > 0)
      .map(([key, workspace]) => [key, normalizePersistedLessonWorkspace(workspace)]),
  )
}

export function normalizePicoLessonEvidence(value: string) {
  return value.trim().replace(/\s+/g, ' ')
}

export function isPicoLessonEvidenceMeaningful(value: string) {
  return normalizePicoLessonEvidence(value).length >= PICO_LESSON_EVIDENCE_MIN_LENGTH
}

function hasPersistedWorkspaceTimestamp(value: string | null) {
  if (!value) return false
  return Number.isFinite(Date.parse(value))
}

function getWorkspaceCompletionBlocker(
  lesson: PicoLesson,
  workspaceInput: PicoLessonWorkspaceState | undefined,
): Pick<PicoLessonCompletionStatus, 'blocker' | 'message' | 'completedStepCount'> {
  const workspace = normalizeLessonWorkspace(workspaceInput, lesson.steps.length)
  const completedStepCount = workspace.completedStepIndexes.length

  if (completedStepCount < lesson.steps.length) {
    const remaining = lesson.steps.length - completedStepCount
    return {
      blocker: 'steps',
      message: `Complete all lesson steps before finishing (${remaining} remaining).`,
      completedStepCount,
    }
  }

  if (!isPicoLessonEvidenceMeaningful(workspace.evidence)) {
    return {
      blocker: 'evidence',
      message: `Save a real output, transcript, command result, or artifact path (at least ${PICO_LESSON_EVIDENCE_MIN_LENGTH} characters).`,
      completedStepCount,
    }
  }

  if (!hasPersistedWorkspaceTimestamp(workspace.updatedAt)) {
    return {
      blocker: 'persistence',
      message: 'Wait for the lesson workspace to save before finishing.',
      completedStepCount,
    }
  }

  return {
    blocker: null,
    message: 'Checkpoint evidence is saved and every lesson step is complete.',
    completedStepCount,
  }
}

function getEvidenceBackedCompletedLessonSlugs(
  completedLessonSlugs: string[],
  lessonWorkspaces: Record<string, PicoLessonWorkspaceState>,
) {
  const requestedCompletions = new Set(completedLessonSlugs)
  const verifiedCompletions = new Set<string>()

  for (const lesson of PICO_LESSONS) {
    if (!requestedCompletions.has(lesson.slug)) continue
    if (!lesson.prerequisites.every((slug) => verifiedCompletions.has(slug))) continue

    const workspaceStatus = getWorkspaceCompletionBlocker(
      lesson,
      lessonWorkspaces[lesson.slug],
    )
    if (!workspaceStatus.blocker) {
      verifiedCompletions.add(lesson.slug)
    }
  }

  return Array.from(verifiedCompletions)
}

const EVIDENCE_BACKED_MILESTONE_LESSONS: Partial<Record<string, string>> = {
  first_tutorial_completed: 'run-your-first-agent',
  first_agent_run: 'run-your-first-agent',
  successful_deployment: 'deploy-hermes-on-a-vps',
  first_skill_added: 'add-your-first-skill',
  first_workflow_built: 'create-a-scheduled-workflow',
}

function getEvidenceBackedMilestoneEvents(events: string[], completedLessons: string[]) {
  const completedLessonSet = new Set(completedLessons)
  return events.filter((eventId) => {
    const requiredLesson = EVIDENCE_BACKED_MILESTONE_LESSONS[eventId]
    return !requiredLesson || completedLessonSet.has(requiredLesson)
  })
}

function parseTimestamp(value: string | null | undefined) {
  if (!value) return 0
  const parsed = new Date(value).getTime()
  return Number.isNaN(parsed) ? 0 : parsed
}

function mergeLessonWorkspaceMaps(
  localMap: Record<string, PicoLessonWorkspaceState>,
  remoteMap: Record<string, PicoLessonWorkspaceState>,
) {
  const lessonSlugs = Array.from(new Set([...Object.keys(remoteMap), ...Object.keys(localMap)]))

  return Object.fromEntries(
    lessonSlugs.map((lessonSlug) => {
      const localWorkspace = localMap[lessonSlug]
      const remoteWorkspace = remoteMap[lessonSlug]

      if (!localWorkspace) {
        return [lessonSlug, remoteWorkspace]
      }

      if (!remoteWorkspace) {
        return [lessonSlug, localWorkspace]
      }

      const localTimestamp = parseTimestamp(localWorkspace.updatedAt)
      const remoteTimestamp = parseTimestamp(remoteWorkspace.updatedAt)

      if (remoteTimestamp > localTimestamp) {
        return [lessonSlug, remoteWorkspace]
      }

      if (localTimestamp > remoteTimestamp) {
        return [lessonSlug, localWorkspace]
      }

      return [
        lessonSlug,
        normalizePersistedLessonWorkspace({
          ...remoteWorkspace,
          ...localWorkspace,
          completedStepIndexes: Array.from(
            new Set([
              ...remoteWorkspace.completedStepIndexes,
              ...localWorkspace.completedStepIndexes,
            ]),
          ).sort((left, right) => left - right),
          notes: localWorkspace.notes || remoteWorkspace.notes,
          evidence: localWorkspace.evidence || remoteWorkspace.evidence,
          updatedAt: localWorkspace.updatedAt || remoteWorkspace.updatedAt,
        }),
      ]
    }),
  )
}

export function normalizePicoProgress(value: Partial<PicoProgressState> | null | undefined): PicoProgressState {
  const fallback = createDefaultPicoProgress()
  const candidate = value ?? {}
  const lessonWorkspaces = normalizeLessonWorkspaceMap(candidate.lessonWorkspaces)
  const completedLessons = getEvidenceBackedCompletedLessonSlugs(
    uniqueStrings(candidate.completedLessons),
    lessonWorkspaces,
  )
  const milestoneEvents = getEvidenceBackedMilestoneEvents(
    uniqueStrings(candidate.milestoneEvents),
    completedLessons,
  )

  return {
    version: typeof candidate.version === 'number' ? candidate.version : fallback.version,
    startedAt:
      typeof candidate.startedAt === 'string' && candidate.startedAt.length > 0
        ? candidate.startedAt
        : fallback.startedAt,
    updatedAt:
      typeof candidate.updatedAt === 'string' && candidate.updatedAt.length > 0
        ? candidate.updatedAt
        : fallback.updatedAt,
    selectedTrack: typeof candidate.selectedTrack === 'string' ? candidate.selectedTrack : null,
    startedLessons: uniqueStrings(candidate.startedLessons),
    completedLessons,
    milestoneEvents,
    tutorQuestions: typeof candidate.tutorQuestions === 'number' ? candidate.tutorQuestions : 0,
    supportRequests: typeof candidate.supportRequests === 'number' ? candidate.supportRequests : 0,
    helpfulResponses: typeof candidate.helpfulResponses === 'number' ? candidate.helpfulResponses : 0,
    sharedProjects: uniqueStrings(candidate.sharedProjects),
    lessonWorkspaces,
    platform: {
      ...createDefaultPicoPlatformPreferences(),
      ...normalizePicoPlatformPreferences(candidate.platform),
      updatedAt:
        typeof candidate.platform?.updatedAt === 'string'
          ? candidate.platform.updatedAt
          : fallback.platform.updatedAt,
    },
    autopilot: {
      costThresholdPercent:
        typeof candidate.autopilot?.costThresholdPercent === 'number'
          ? Math.max(1, Math.min(100, Math.round(candidate.autopilot.costThresholdPercent)))
          : DEFAULT_AUTOPILOT_STATE.costThresholdPercent,
      alertChannel:
        candidate.autopilot?.alertChannel === 'email' || candidate.autopilot?.alertChannel === 'webhook'
          ? candidate.autopilot.alertChannel
          : 'in_app',
      approvalGateEnabled: Boolean(candidate.autopilot?.approvalGateEnabled),
      approvalRequestIds: uniqueStrings(candidate.autopilot?.approvalRequestIds),
      lastThresholdBreachAt:
        typeof candidate.autopilot?.lastThresholdBreachAt === 'string'
          ? candidate.autopilot.lastThresholdBreachAt
          : null,
    },
  }
}

export function getLessonBySlug(slug: string) {
  return PICO_LESSONS.find((lesson) => lesson.slug === slug) ?? null
}

export function getPicoLessonCompletionStatus(
  progressInput: Partial<PicoProgressState> | null | undefined,
  lessonSlug: string,
): PicoLessonCompletionStatus {
  const lesson = getLessonBySlug(lessonSlug)
  if (!lesson) {
    return {
      canComplete: false,
      isComplete: false,
      blocker: 'unknown_lesson',
      message: 'This lesson is not part of the Academy curriculum.',
      completedStepCount: 0,
      requiredStepCount: 0,
    }
  }

  const lessonWorkspaces = normalizeLessonWorkspaceMap(progressInput?.lessonWorkspaces)
  const evidenceBackedCompletions = new Set(
    getEvidenceBackedCompletedLessonSlugs(
      uniqueStrings(progressInput?.completedLessons),
      lessonWorkspaces,
    ),
  )
  const missingPrerequisite = lesson.prerequisites.find(
    (slug) => !evidenceBackedCompletions.has(slug),
  )
  const workspaceStatus = getWorkspaceCompletionBlocker(
    lesson,
    lessonWorkspaces[lesson.slug],
  )

  if (missingPrerequisite) {
    const prerequisite = getLessonBySlug(missingPrerequisite)
    return {
      canComplete: false,
      isComplete: false,
      blocker: 'prerequisite',
      message: `Complete ${prerequisite?.title ?? missingPrerequisite} with evidence first.`,
      completedStepCount: workspaceStatus.completedStepCount,
      requiredStepCount: lesson.steps.length,
    }
  }

  return {
    canComplete: workspaceStatus.blocker === null,
    isComplete: evidenceBackedCompletions.has(lesson.slug),
    blocker: workspaceStatus.blocker,
    message: workspaceStatus.message,
    completedStepCount: workspaceStatus.completedStepCount,
    requiredStepCount: lesson.steps.length,
  }
}

export function getTrackBySlug(slug: string) {
  return PICO_TRACKS.find((track) => track.slug === slug) ?? null
}

export function getLessonsForTrack(trackSlug: string) {
  return PICO_LESSONS.filter((lesson) => lesson.track === trackSlug)
}

export function getLessonsForLevel(levelId: number) {
  return PICO_LESSONS.filter((lesson) => lesson.level === levelId)
}

export function derivePicoProgress(progressInput: Partial<PicoProgressState> | null | undefined): PicoDerivedProgress {
  const progress = normalizePicoProgress(progressInput)
  const completedLessons = new Set(progress.completedLessons)
  const milestoneEvents = new Set(progress.milestoneEvents)

  const unlockedLessonSlugs = PICO_LESSONS.filter((lesson) =>
    lesson.prerequisites.every((prerequisite) => completedLessons.has(prerequisite))
  ).map((lesson) => lesson.slug)

  const completedTrackSlugs = PICO_TRACKS.filter((track) =>
    track.lessons.every((lessonSlug) => completedLessons.has(lessonSlug))
  ).map((track) => track.slug)

  const unlockedTrackSlugs = PICO_TRACKS.filter((track, index) =>
    index === 0 || completedTrackSlugs.includes(PICO_TRACKS[index - 1]?.slug ?? '')
  ).map((track) => track.slug)

  const lessonXp = PICO_LESSONS.reduce(
    (total, lesson) => total + (completedLessons.has(lesson.slug) ? lesson.xp : 0),
    0
  )
  const milestoneXp = Array.from(milestoneEvents).reduce(
    (total, eventId) => total + (PICO_MILESTONE_XP[eventId] ?? 0),
    0
  )
  const trackXp = completedTrackSlugs.length * 30
  const xp = lessonXp + milestoneXp + trackXp

  const badges = PICO_BADGE_RULES.filter((rule) => rule.test(completedLessons, milestoneEvents)).map(
    (rule) => rule.label
  )

  const unlockedCapabilities = PICO_CAPABILITY_UNLOCKS.filter((capability) =>
    milestoneEvents.has(capability.unlockEvent)
  )
  const nextCapability =
    PICO_CAPABILITY_UNLOCKS.find((capability) => !milestoneEvents.has(capability.unlockEvent)) ?? null

  const currentLevel = PICO_LEVELS.reduce((level, item) => {
    const levelComplete = getLessonsForLevel(item.id).every((lesson) => completedLessons.has(lesson.slug))
    return levelComplete ? item.id : level
  }, 0)

  const selectedTrackLessons = progress.selectedTrack
    ? getLessonsForTrack(progress.selectedTrack).filter(
        (lesson) => !completedLessons.has(lesson.slug) && unlockedLessonSlugs.includes(lesson.slug)
      )
    : []

  const nextLesson =
    selectedTrackLessons[0] ??
    PICO_LESSONS.find((lesson) => !completedLessons.has(lesson.slug) && unlockedLessonSlugs.includes(lesson.slug)) ??
    null

  return {
    xp,
    currentLevel,
    totalLessons: PICO_LESSONS.length,
    completedLessonCount: completedLessons.size,
    completedTrackSlugs,
    badges,
    unlockedLessonSlugs,
    unlockedTrackSlugs,
    unlockedCapabilities,
    nextCapability,
    nextLesson,
  }
}

export function mergePicoProgress(localValue: Partial<PicoProgressState> | null | undefined, remoteValue: Partial<PicoProgressState> | null | undefined) {
  const local = normalizePicoProgress(localValue)
  const remote = normalizePicoProgress(remoteValue)
  const requestedCompletedLessons = Array.from(
    new Set([
      ...uniqueStrings(remoteValue?.completedLessons),
      ...uniqueStrings(localValue?.completedLessons),
    ]),
  )
  const requestedMilestoneEvents = Array.from(
    new Set([
      ...uniqueStrings(remoteValue?.milestoneEvents),
      ...uniqueStrings(localValue?.milestoneEvents),
    ]),
  )

  const remoteLooksEmpty =
    !remote.selectedTrack &&
    remote.startedLessons.length === 0 &&
    remote.completedLessons.length === 0 &&
    remote.milestoneEvents.length === 0 &&
    remote.sharedProjects.length === 0 &&
    Object.keys(remote.lessonWorkspaces).length === 0 &&
    remote.platform.activeSurface === null &&
    remote.platform.lastOpenedLessonSlug === null &&
    remote.platform.railCollapsed === false &&
    remote.platform.helpLaneOpen === false &&
    remote.tutorQuestions === 0 &&
    remote.supportRequests === 0 &&
    uniqueStrings(remoteValue?.completedLessons).length === 0 &&
    uniqueStrings(remoteValue?.milestoneEvents).length === 0

  if (remoteLooksEmpty) {
    return local
  }

  return normalizePicoProgress({
    ...remote,
    selectedTrack: local.selectedTrack || remote.selectedTrack,
    startedLessons: Array.from(new Set([...remote.startedLessons, ...local.startedLessons])),
    completedLessons: requestedCompletedLessons,
    milestoneEvents: requestedMilestoneEvents,
    sharedProjects: Array.from(new Set([...remote.sharedProjects, ...local.sharedProjects])),
    lessonWorkspaces: mergeLessonWorkspaceMaps(local.lessonWorkspaces, remote.lessonWorkspaces),
    platform: {
      ...remote.platform,
      activeSurface: local.platform.activeSurface ?? remote.platform.activeSurface,
      lastOpenedLessonSlug:
        local.platform.lastOpenedLessonSlug ?? remote.platform.lastOpenedLessonSlug,
      railCollapsed: local.platform.railCollapsed,
      helpLaneOpen: local.platform.helpLaneOpen,
      updatedAt:
        parseTimestamp(remote.platform.updatedAt ?? remote.updatedAt) >
        parseTimestamp(local.platform.updatedAt ?? local.updatedAt)
          ? remote.platform.updatedAt
          : local.platform.updatedAt,
    },
    tutorQuestions: Math.max(remote.tutorQuestions, local.tutorQuestions),
    supportRequests: Math.max(remote.supportRequests, local.supportRequests),
    helpfulResponses: Math.max(remote.helpfulResponses, local.helpfulResponses),
    autopilot: {
      ...remote.autopilot,
      ...local.autopilot,
      approvalRequestIds: Array.from(
        new Set([...remote.autopilot.approvalRequestIds, ...local.autopilot.approvalRequestIds])
      ),
      lastThresholdBreachAt:
        remote.autopilot.lastThresholdBreachAt || local.autopilot.lastThresholdBreachAt || null,
    },
    updatedAt:
      new Date(remote.updatedAt).getTime() > new Date(local.updatedAt).getTime()
        ? remote.updatedAt
        : local.updatedAt,
  })
}

export function applyLessonStarted(progressInput: Partial<PicoProgressState>, lessonSlug: string): PicoProgressState {
  const progress = normalizePicoProgress(progressInput)
  const next = normalizePicoProgress({
    ...progress,
    startedLessons: Array.from(new Set([...progress.startedLessons, lessonSlug])),
    milestoneEvents: Array.from(
      new Set([
        ...progress.milestoneEvents,
        ...(progress.startedLessons.length === 0 ? ['first_tutorial_started'] : []),
      ])
    ),
    updatedAt: new Date().toISOString(),
  })
  return next
}

export function applyLessonCompleted(progressInput: Partial<PicoProgressState>, lessonSlug: string): PicoProgressState {
  const progress = normalizePicoProgress(progressInput)
  const lesson = getLessonBySlug(lessonSlug)
  if (!lesson) {
    return progress
  }

  const completionStatus = getPicoLessonCompletionStatus(progress, lessonSlug)
  if (!completionStatus.canComplete) {
    return progress
  }

  const milestoneEvents = new Set(progress.milestoneEvents)
  for (const eventId of lesson.milestoneEvents ?? []) {
    milestoneEvents.add(eventId)
  }

  return normalizePicoProgress({
    ...progress,
    startedLessons: Array.from(new Set([...progress.startedLessons, lessonSlug])),
    completedLessons: Array.from(new Set([...progress.completedLessons, lessonSlug])),
    milestoneEvents: Array.from(milestoneEvents),
    updatedAt: new Date().toISOString(),
  })
}

export function applyMilestone(progressInput: Partial<PicoProgressState>, eventId: string): PicoProgressState {
  const progress = normalizePicoProgress(progressInput)
  return normalizePicoProgress({
    ...progress,
    milestoneEvents: Array.from(new Set([...progress.milestoneEvents, eventId])),
    updatedAt: new Date().toISOString(),
  })
}

export function updateAutopilotSettings(
  progressInput: Partial<PicoProgressState>,
  autopilotPatch: Partial<PicoProgressState['autopilot']>
): PicoProgressState {
  const progress = normalizePicoProgress(progressInput)
  return normalizePicoProgress({
    ...progress,
    autopilot: {
      ...progress.autopilot,
      ...autopilotPatch,
    },
    updatedAt: new Date().toISOString(),
  })
}

export function selectTrack(progressInput: Partial<PicoProgressState>, trackSlug: string): PicoProgressState {
  const progress = normalizePicoProgress(progressInput)
  return normalizePicoProgress({
    ...progress,
    selectedTrack: trackSlug,
    updatedAt: new Date().toISOString(),
  })
}

export function markTutorQuestion(progressInput: Partial<PicoProgressState>): PicoProgressState {
  const progress = normalizePicoProgress(progressInput)
  return normalizePicoProgress({
    ...progress,
    tutorQuestions: progress.tutorQuestions + 1,
    updatedAt: new Date().toISOString(),
  })
}

export function markSupportRequest(progressInput: Partial<PicoProgressState>): PicoProgressState {
  const progress = normalizePicoProgress(progressInput)
  return normalizePicoProgress({
    ...progress,
    supportRequests: progress.supportRequests + 1,
    updatedAt: new Date().toISOString(),
  })
}

export function markProjectShared(progressInput: Partial<PicoProgressState>, projectId: string): PicoProgressState {
  const progress = normalizePicoProgress(progressInput)
  const next = normalizePicoProgress({
    ...progress,
    sharedProjects: Array.from(new Set([...progress.sharedProjects, projectId])),
    milestoneEvents: Array.from(new Set([...progress.milestoneEvents, 'project_shared'])),
    updatedAt: new Date().toISOString(),
  })
  return next
}

export function updateLessonWorkspace(
  progressInput: Partial<PicoProgressState>,
  lessonSlug: string,
  workspace: PicoLessonWorkspaceState,
): PicoProgressState {
  const progress = normalizePicoProgress(progressInput)
  return normalizePicoProgress({
    ...progress,
    lessonWorkspaces: {
      ...progress.lessonWorkspaces,
      [lessonSlug]: normalizePersistedLessonWorkspace(workspace),
    },
    updatedAt: new Date().toISOString(),
  })
}

export function updatePlatformPreferences(
  progressInput: Partial<PicoProgressState>,
  patch: Partial<PicoPlatformPreferences>,
): PicoProgressState {
  const progress = normalizePicoProgress(progressInput)
  return normalizePicoProgress({
    ...progress,
    platform: {
      ...progress.platform,
      ...patch,
      updatedAt: new Date().toISOString(),
    },
    updatedAt: new Date().toISOString(),
  })
}

export function searchLessonCorpus(query: string) {
  const tokens = query
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length > 1)

  if (tokens.length === 0) {
    return PICO_LESSONS.slice(0, 3).map((lesson, index) => ({ lesson, score: 3 - index }))
  }

  return PICO_LESSONS.map((lesson) => {
    const haystack = [
      lesson.title,
      lesson.summary,
      lesson.objective,
      lesson.outcome,
      lesson.expectedResult,
      lesson.validation,
      ...lesson.troubleshooting,
      ...lesson.steps.map((step) => `${step.title} ${step.body} ${step.command ?? ''}`),
    ]
      .join(' ')
      .toLowerCase()

    let score = 0
    for (const token of tokens) {
      if (haystack.includes(token)) score += 2
      if (lesson.title.toLowerCase().includes(token)) score += 2
      if (lesson.slug.includes(token)) score += 1
    }
    return { lesson, score }
  })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 4)
}

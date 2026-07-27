import { test, expect, type Locator, type Page } from '@playwright/test';
import { createDefaultPicoProgress } from '../lib/pico/academy';

type PicoProductStubOptions = {
  authenticated?: boolean
  isEmailVerified?: boolean
  webhookCount?: number
}

async function expectRouteSurfaceSplit(page: Page) {
  const dark = page.locator('[data-route-surface="dark"]').first();
  const light = page.locator('[data-route-surface="light"]').first();

  await expect(dark).toBeVisible();
  await expect(light).toBeVisible();

  const metrics = await page.evaluate(() => {
    const darkSurface = document.querySelector('[data-route-surface="dark"]');
    const lightSurface = document.querySelector('[data-route-surface="light"]');
    const heading = document.querySelector('main h1');

    const darkRect = darkSurface?.getBoundingClientRect();
    const lightRect = lightSurface?.getBoundingClientRect();
    const headingRect = heading?.getBoundingClientRect();
    const seamY = lightRect?.top ?? 0;

    const crossingPanel = Array.from(
      document.querySelectorAll('[class*="panel"], [data-testid="contact-lead-form"]')
    ).some((node) => {
      const rect = node.getBoundingClientRect();
      return rect.top < seamY - 1 && rect.bottom > seamY + 1;
    });

    return {
      darkBottom: darkRect?.bottom ?? 0,
      lightTop: lightRect?.top ?? 0,
      headingInsideDark: Boolean(
        darkRect &&
          headingRect &&
          headingRect.top >= darkRect.top - 1 &&
          headingRect.bottom <= darkRect.bottom + 1
      ),
      crossingPanel,
    };
  });

  expect(metrics.lightTop).toBeGreaterThanOrEqual(metrics.darkBottom - 1);
  expect(metrics.headingInsideDark).toBe(true);
  expect(metrics.crossingPanel).toBe(false);
}

async function expectAuthLedger(page: Page, variant: 'access' | 'recovery') {
  await expect(page.getByTestId('public-auth-nav')).toBeVisible();
  await expect(page.locator(`main[data-auth-variant="${variant}"]`)).toBeVisible();
  await expect(page.getByText(/identity ledger/i)).toBeVisible();
}

async function getAverageRgb(locator: Locator) {
  return locator.first().evaluate((node) => {
    const color = getComputedStyle(node).color;
    const channels = color.match(/\d+(\.\d+)?/g)?.slice(0, 3).map(Number) ?? [];

    if (channels.length !== 3) {
      throw new Error(`Could not parse computed color: ${color}`);
    }

    return channels.reduce((sum, channel) => sum + channel, 0) / channels.length;
  });
}

async function stubPicoProductApis(
  page: Page,
  {
    authenticated = true,
    isEmailVerified = true,
    webhookCount = 2,
  }: PicoProductStubOptions = {},
) {
  const progress = createDefaultPicoProgress();
  const sessionUser = {
    email: 'operator@mutx.dev',
    name: 'Pico Operator',
    role: 'ADMIN',
    is_email_verified: isEmailVerified,
  };
  let openAIConnection = {
    provider: 'openai',
    status: 'disconnected',
    source: 'none',
    connected: false,
    model: 'gpt-5-mini',
    maskedKey: null as string | null,
    message: 'No OpenAI key is connected. Tutor will use platform access if available, or fall back to local synthesis.',
  };

  await page.route('**/api/auth/me', async (route) => {
    if (!authenticated) {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Unauthorized',
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(sessionUser),
    });
  });

  await page.route('**/api/pico/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        authenticated
          ? { authenticated: true, user: sessionUser }
          : { authenticated: false, user: null }
      ),
    });
  });

  await page.route('**/api/webhooks', async (route) => {
    if (!authenticated) {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Unauthorized',
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        webhooks: Array.from({ length: webhookCount }, (_, index) => ({
          id: `wh_${index + 1}`,
          name: `Webhook ${index + 1}`,
        })),
      }),
    });
  });

  await page.route('**/api/pico/progress', async (route) => {
    const body = route.request().postData() || JSON.stringify(progress);

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: route.request().method() === 'POST' ? body : JSON.stringify(progress),
    });
  });

  await page.route('**/api/pico/onboarding?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        provider: 'openclaw',
        status: 'in_progress',
        current_step: 'install',
        completed_steps: ['auth', 'provider'],
        failed_step: null,
        last_error: null,
        checklist_dismissed: false,
        assistant_name: 'Pico Starter',
        assistant_id: 'ast_123',
        workspace: 'founder-lab',
        gateway_url: 'http://localhost:4111',
        updated_at: '2026-04-12T10:15:00.000Z',
        steps: [
          { id: 'auth', title: 'Authenticate user', completed: true },
          { id: 'provider', title: 'Select provider', completed: true },
          { id: 'install', title: 'Install runtime', completed: false },
          { id: 'onboard', title: 'Onboard gateway', completed: false },
          { id: 'track', title: 'Track local runtime', completed: false },
          { id: 'bind', title: 'Bind assistant', completed: false },
          { id: 'governance', title: 'Configure governance', completed: false },
          { id: 'deploy', title: 'Deploy starter assistant', completed: false },
          { id: 'verify', title: 'Verify local health', completed: false },
        ],
      }),
    });
  });

  await page.route('**/api/pico/runtime/openclaw', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        provider: 'openclaw',
        label: 'OpenClaw',
        status: 'healthy',
        gateway_url: 'http://localhost:4111',
        version: '0.9.2',
        binary_path: '/Users/operator/.mutx/providers/openclaw/bin/openclaw',
        config_path: '/Users/operator/.mutx/providers/openclaw/config.json',
        state_dir: '/Users/operator/.mutx/providers/openclaw/state',
        last_seen_at: '2026-04-12T10:14:00.000Z',
        last_synced_at: '2026-04-12T10:15:00.000Z',
        stale: false,
        binding_count: 1,
        bindings: [
          {
            assistant_id: 'ast_123',
            assistant_name: 'Pico Starter',
            workspace: 'founder-lab',
            model: 'gpt-5.4-mini',
          },
        ],
      }),
    });
  });

  await page.route('**/api/pico/tutor', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        title: 'Run your first agent',
        summary: 'Install is done. Open the first prompt lesson and get one visible answer back.',
        answer: 'Install is done. Open the first prompt lesson and get one visible answer back.',
        confidence: 'high',
        nextActions: [
          'Open the first prompt lesson.',
          'Run one bounded prompt.',
          'Save the transcript as output.',
        ],
        lessons: [
          {
            id: 'run-your-first-agent',
            title: 'Run your first agent',
            href: '/pico/academy/run-your-first-agent',
          },
        ],
        docs: [
          {
            label: 'Support',
            href: '/pico/support',
            sourcePath: 'pico/support',
          },
        ],
        recommendedLessonIds: ['run-your-first-agent'],
        escalate: false,
        structured: {
          situation: 'Hermes is installed, and the current blocker is proving one real run with a visible transcript.',
          diagnosis: 'The user should move into the first prompt lesson instead of branching into more setup.',
          steps: [
            'Open the first prompt lesson.',
            'Run one bounded prompt.',
            'Save the transcript as output.',
          ],
          commands: [
            {
              label: 'Save the output',
              code: 'printf "Prompt: Give me exactly 3 next steps to test this runtime locally.\\nAnswer: <paste the actual answer here>\\n" > ~/pico-first-run.txt',
              language: 'bash',
            },
          ],
          verify: ['Hermes returns one sane answer and the transcript survives after the shell closes.'],
          ifThisFails: ['Paste the exact command output or timeout instead of asking another broad question.'],
          officialLinks: [
            {
              label: 'github.com',
              href: 'https://github.com/nousresearch/hermes-agent',
              sourcePath: 'github.com',
            },
          ],
          sources: [
            {
              kind: 'lesson',
              title: 'Run your first agent',
              sourcePath: 'pico/academy/run-your-first-agent',
              href: '/pico/academy/run-your-first-agent',
              excerpt: 'Run one real prompt, get one visible answer, and save the transcript as output.',
            },
            {
              kind: 'knowledge_pack',
              title: 'Hermes',
              sourcePath: 'knowledge/pico_ops/HERMES.md',
              excerpt: 'Hermes is the default recommendation when the user wants a persistent agent that improves over time.',
            },
          ],
          nextQuestion: null,
        },
        intent: 'install',
        skillLevel: 'intermediate',
        usedOfficialFallback: false,
      }),
    });
  });

  await page.route('**/api/pico/tutor/openai', async (route) => {
    if (!authenticated) {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Unauthorized',
        }),
      });
      return;
    }

    if (route.request().method() === 'PUT') {
      const payload = JSON.parse(route.request().postData() || '{}');
      const apiKey = typeof payload.apiKey === 'string' ? payload.apiKey : '';
      openAIConnection = {
        provider: 'openai',
        status: 'connected',
        source: 'user',
        connected: true,
        model: 'gpt-5-mini',
        maskedKey: apiKey ? `••••${apiKey.slice(-4)}` : '••••test',
        message: `Your OpenAI key ${apiKey ? `••••${apiKey.slice(-4)}` : '••••test'} is active for live tutor answers.`,
      };
    } else if (route.request().method() === 'DELETE') {
      openAIConnection = {
        provider: 'openai',
        status: 'disconnected',
        source: 'none',
        connected: false,
        model: 'gpt-5-mini',
        maskedKey: null,
        message: 'No OpenAI key is connected. Tutor will use platform access if available, or fall back to local synthesis.',
      };
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(openAIConnection),
    });
  });

  await page.route('**/api/dashboard/runs?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [],
      }),
    });
  });

  await page.route('**/api/dashboard/runs/**/traces?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [],
      }),
    });
  });

  await page.route('**/api/dashboard/budgets', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        plan: 'starter',
        credits_total: 1000,
        credits_used: 120,
        credits_remaining: 880,
        usage_percentage: 12,
        reset_date: '2026-05-01T00:00:00.000Z',
      }),
    });
  });

  await page.route('**/api/dashboard/budgets/usage?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        total_credits_used: 120,
        credits_remaining: 880,
        credits_total: 1000,
        period_start: '2026-04-01T00:00:00.000Z',
        period_end: '2026-04-30T23:59:59.000Z',
        usage_by_agent: [],
        usage_by_type: [],
      }),
    });
  });

  await page.route('**/api/dashboard/monitoring/alerts?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [],
      }),
    });
  });

  await page.route('**/api/pico/approvals?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });
}

test.describe('mutx.dev QA', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('https://challenges.cloudflare.com/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/javascript',
        body: 'window.turnstile={render:(el,opts)=>{setTimeout(()=>opts?.callback?.("ci-test-token"),0);return "widget-id";},reset:()=>{},remove:()=>{}};',
      });
    });

    await page.route('**/_next/image**', async (route) => {
      const url = new URL(route.request().url());
      const originalUrl = url.searchParams.get('url');

      if (!originalUrl || originalUrl.includes('/logo.png')) {
        await route.fulfill({
          status: 200,
          contentType: 'image/png',
          body: Buffer.from(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn8nWsAAAAASUVORK5CYII=',
            'base64'
          ),
        });
        return;
      }

      await route.fallback();
    });

    await page.route('**/api/newsletter', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ count: 612 }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          message: "You're on the list. Check your inbox.",
          emailSent: true,
        }),
      });
    });

    await page.route('https://calendly.com/assets/external/widget.css', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/css',
        body: '',
      });
    });

    await page.route('https://calendly.com/assets/external/widget.js', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/javascript',
        body: 'window.Calendly={initPopupWidget:()=>{},closePopupWidget:()=>{}};',
      });
    });
  });

  test('homepage opens directly into a concrete operational ledger', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await expect(page.getByTestId('marketing-loader')).toHaveCount(0);
    await expect(page.getByText(/^Loading\.\.\.$/i)).toHaveCount(0);
    await expect(
      page.getByRole('heading', { name: /see every move\. hold the line\./i })
    ).toBeVisible();
    await expect(
      page.getByText(/stops actions outside policy, and keeps a reviewable receipt/i)
    ).toBeVisible();
    await expect(page.getByRole('link', { name: /download for mac/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /open dashboard/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /^docs$/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /github/i }).first()).toBeVisible();

    const runRecord = page.getByLabel(/example mutx production deployment run/i);
    await expect(runRecord).toBeVisible();
    await expect(runRecord.getByText(/production boundary matched/i)).toBeVisible();
    await expect(runRecord.getByText(/approved by a\. rivera/i)).toBeVisible();
    await expect(runRecord.getByText(/rcpt_7f2a91/i)).toBeVisible();
  });

  test('homepage tells one complete story from intent to evidence', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    for (const heading of [
      /one line from intent to evidence/i,
      /signal first\. furniture last\./i,
      /helpful is not the same as permitted\./i,
      /from download to first record\./i,
      /run the agent\. keep the evidence\./i,
    ]) {
      await expect(page.getByRole('heading', { name: heading })).toBeVisible();
    }

    for (const label of ['Observe', 'Bound', 'Approve', 'Execute', 'Prove']) {
      await expect(page.getByRole('link', { name: new RegExp(label, 'i') }).first()).toBeVisible();
    }

    await expect(page.getByText(/no file moved\. scope and destination preserved/i)).toBeVisible();
    await expect(page.getByText(/source-available control plane/i).first()).toBeVisible();
  });

  test('homepage stays inside the mobile viewport and preserves the operating record', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await expect(
      page.getByRole('heading', { name: /see every move\. hold the line\./i })
    ).toBeVisible();
    await expect(page.getByLabel(/example mutx production deployment run/i)).toBeVisible();

    const metrics = await page.evaluate(() => {
      const heading = document.querySelector('h1');
      const headingRect = heading?.getBoundingClientRect();

      return {
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
        headingLeft: headingRect?.left ?? 0,
        headingRight: headingRect?.right ?? 0,
      };
    });

    expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewportWidth);
    expect(metrics.headingLeft).toBeGreaterThanOrEqual(-1);
    expect(metrics.headingRight).toBeLessThanOrEqual(metrics.viewportWidth + 1);
    await expect(page.getByRole('link', { name: /download/i }).first()).toBeVisible();
  });

  test('public mobile navigation behaves as a modal and releases state on resize', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    const opener = page.getByRole('button', { name: /open navigation/i });
    await opener.click();

    const dialog = page.getByRole('dialog', { name: /control plane navigation/i });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button', { name: /close navigation/i })).toBeFocused();
    expect(await page.evaluate(() => document.body.style.overflow)).toBe('hidden');
    expect(
      await page.evaluate(() =>
        Array.from(document.body.children).some(
          (element) => element instanceof HTMLElement && element.inert,
        ),
      ),
    ).toBe(true);

    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(opener).toBeFocused();
    expect(await page.evaluate(() => document.body.style.overflow)).not.toBe('hidden');

    await opener.click();
    await expect(dialog).toBeVisible();
    await page.setViewportSize({ width: 1100, height: 844 });
    await expect(dialog).toHaveCount(0);
    expect(await page.evaluate(() => document.body.style.overflow)).not.toBe('hidden');
  });

  test('homepage remains scrollable with motion enabled or reduced', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.documentElement.scrollHeight > window.innerHeight);

    const before = await page.evaluate(() => window.scrollY);
    await page.mouse.move(320, 320);
    await page.mouse.wheel(0, 1800);
    await page.waitForTimeout(250);
    const after = await page.evaluate(() => window.scrollY);

    expect(before).toBe(0);
    expect(after).toBeGreaterThan(0);
    await expect(page.getByRole('heading', { name: /one line from intent to evidence/i })).toBeVisible();
  });

  test('product artifacts clearly identify illustrative operational data', async ({ page }) => {
    await page.goto('/ai-agent-control-plane', { waitUntil: 'domcontentloaded' });

    const recorder = page.getByLabel(/illustrative flight recorder/i);
    await expect(recorder).toBeVisible();
    await expect(recorder.getByText(/product example/i)).toBeVisible();
    await expect(recorder.getByText(/sample \/ plane \/ healthy/i)).toBeVisible();
    await expect(recorder.getByText(/sha-256 \/ sample/i)).toBeVisible();
    await expect(recorder.getByText(/live record/i)).toHaveCount(0);
  });

  test('download page exposes the mac release notes and checksum path', async ({ page }) => {
    await page.goto('/download/macos', { waitUntil: 'domcontentloaded' });

    await expect(page.getByTestId('public-nav')).toBeVisible();
    await expect(page.getByRole('navigation', { name: /primary navigation/i })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: /download mutx for macos\./i })
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: /download for apple silicon/i })
    ).toBeVisible();
    await expect(page.getByRole('link', { name: /download for intel mac/i })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Release summary', exact: true }).first()).toBeVisible();
    await expect(
      page.getByText(
        /downloads, notes, and checksums stay in one place\./i
      )
    ).toBeVisible();
    await expect(page.getByRole('heading', { name: /^Release summary$/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /^Docs notes$/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /^Checksums$/i })).toBeVisible();
  });

  test('releases page exposes the current release summary and artifact links', async ({ page }) => {
    await page.goto('/releases', { waitUntil: 'domcontentloaded' });

    await expect(page.getByTestId('public-nav')).toBeVisible();
    await expect(
      page.getByRole('heading', { name: /signed desktop release\./i })
    ).toBeVisible();
    await expect(page.getByRole('link', { name: /open mac downloads/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /^Apple Silicon DMG$/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /^Intel Mac DMG$/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /^Checksums$/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /^Docs notes$/i })).toBeVisible();
    await expect(
      page.getByText(
        /current signed mac release, checksums, docs notes, and github tag\./i
      )
    ).toBeVisible();
  });

  test('docs routes keep the branded manual shell and expose a guided hub', async ({ page }) => {
    await page.goto('/docs', { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('link', { name: /mutx docs operator manual/i })).toBeVisible();
    await expect(
      page.getByRole('heading', {
        name: /know the system\./i,
      }),
    ).toBeVisible();
    await expect(page.getByRole('link', { name: /open mutx quickstart/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /read api reference/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /go by surface\./i })).toBeVisible();

    await page.goto('/docs/deployment/quickstart', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('link', { name: /mutx docs operator manual/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /quickstart/i }).first()).toBeVisible();
    await expect(page.locator('.docs-breadcrumbs')).toBeVisible();
  });

  test('contact, privacy, login, register, forgot-password, and reset-password routes keep working under the new shell', async ({
    page,
  }) => {
    await page.goto('/contact', { waitUntil: 'domcontentloaded' });
    await expectRouteSurfaceSplit(page);
    await expect(page.getByTestId('public-nav')).toBeVisible();
    await expect(page.getByRole('navigation', { name: /primary navigation/i })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: /talk to mutx\./i })
    ).toBeVisible();
    await expect(page.getByRole('button', { name: /book a call/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /email mutx/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /send inquiry/i })).toBeVisible();
    await expect(page.getByPlaceholder('you@company.com')).toBeVisible();
    await expect(page.getByTestId('contact-lead-form')).toBeVisible();
    await expect(page.getByText(/bring the real workflow/i)).toHaveCount(0);
    await expect(page.getByText(/send a structured inquiry/i)).toHaveCount(0);
    await expect(page.getByText(/what to include/i)).toHaveCount(0);
    await expect(page.getByText(/make the first message useful\./i)).toHaveCount(0);
    await expect(page.getByRole('heading', { name: /^Email$/i })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: /^Docs$/i })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: /^Quickstart$/i })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: /^GitHub$/i })).toHaveCount(0);
    await expect(page.getByText(/back to mutx\.dev/i)).toHaveCount(0);

    await page.goto('/privacy-policy', { waitUntil: 'domcontentloaded' });
    await expectRouteSurfaceSplit(page);
    await expect(page.getByRole('heading', { name: /privacy policy/i })).toBeVisible();
    await expect(page.getByText(/effective date: march 13, 2026/i)).toBeVisible();
    await expect(page.getByRole('heading', { name: /information we collect/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /^security$/i })).toBeVisible();
    expect(
      await getAverageRgb(
        page.getByText(/we may collect information you provide directly to us/i)
      )
    ).toBeLessThan(140);
    expect(await getAverageRgb(page.getByText(/^effective date$/i))).toBeLessThan(140);

    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    await expectAuthLedger(page, 'access');
    await expect(page.getByLabel(/email address/i)).toBeVisible();
    await expect(page.getByLabel(/^password$/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /continue with google/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /continue with github/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /continue with discord/i })).toBeVisible();

    await page.goto('/register', { waitUntil: 'domcontentloaded' });
    await expectAuthLedger(page, 'access');
    await expect(page.getByLabel(/email address/i)).toBeVisible();
    await expect(page.getByLabel(/^password$/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /sign up/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /continue with google/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /continue with github/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /continue with discord/i })).toBeVisible();

    await page.goto('/verify-email?email=operator%40mutx.dev&next=%2Fdashboard%2Fwebhooks', {
      waitUntil: 'domcontentloaded',
    });
    await expectAuthLedger(page, 'recovery');
    await expect(page.getByText(/we sent a verification link to operator@mutx\.dev\./i)).toBeVisible();
    await expect(page.getByRole('button', { name: /resend verification/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /back to sign in/i })).toHaveAttribute(
      'href',
      /\/login\?next=%2Fdashboard%2Fwebhooks&email=operator%40mutx\.dev/i,
    );

    await page.goto('/forgot-password', { waitUntil: 'domcontentloaded' });
    await expectAuthLedger(page, 'recovery');
    await expect(page.getByText(/send reset instructions/i)).toBeVisible();
    await expect(page.getByLabel(/email address/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /send reset link/i })).toBeVisible();

    await page.goto('/reset-password', { waitUntil: 'domcontentloaded' });
    await expectAuthLedger(page, 'recovery');
    await expect(page.getByText(/invalid reset link/i)).toBeVisible();

    await page.goto('/reset-password?token=test-token', { waitUntil: 'domcontentloaded' });
    await expectAuthLedger(page, 'recovery');
    await expect(page.getByText(/choose a new password/i)).toBeVisible();
    await expect(page.getByLabel(/new password/i)).toBeVisible();
    await expect(page.getByLabel(/confirm password/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /reset password/i })).toBeVisible();
  });

  test('pico root stays on the landing page with access-first CTAs only', async ({ page }) => {
    const contactPayload: { current?: Record<string, unknown> } = {};
    await page.route('**/api/contact', async (route) => {
      contactPayload.current = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, message: 'Request received', notified: false }),
      });
    });

    await page.goto('/pico', { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('dialog', { name: /mutx demo intro/i })).toHaveCount(0);
    await expect(page.getByTestId('pico-landing')).toBeVisible();
    await expect(page.locator('main h1').first()).toBeVisible();
    await expect(page.locator('main')).toContainText(/PicoMUTX/i);
    await expect(page.getByTestId('pico-footer')).toBeVisible();
    await expect(page.getByRole('heading', { name: /get to your first working agent fast/i })).toHaveCount(0);
    await expect(page.getByTestId('pico-surface-compass')).toHaveCount(0);
    await expect(page.locator('a[href*="/pico/onboarding"], a[href*="/onboarding"]')).toHaveCount(0);
    await expect(page.getByRole('link', { name: /see pricing/i })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /request access/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /see how it works/i }).first()).toBeVisible();
    await expect(page.locator('#pricing button')).toHaveCount(4);
    await expect(page.locator('#pricing')).toContainText(/request trial access/i);
    await expect(page.locator('#pricing')).toContainText(/request founding access/i);
    await expect(page.locator('#pricing')).toContainText(/request supported access/i);
    await expect(page.locator('#pricing')).toContainText(/book a planning call/i);
    await expect(page.locator('#pricing')).toContainText(/90%/i);
    await expect(page.locator('#pricing')).toContainText(/€290/i);
    await expect(page.locator('#pricing')).toContainText(/€790/i);
    await expect(page.locator('main')).toContainText(/founding access|waitlist-first|request access/i);
    await expect(page.locator('main')).not.toContainText(/pre-register/i);

    const agentGallery = page.getByRole('region', { name: /autonomous agent types/i });
    await expect(agentGallery).toHaveAttribute('data-interactive', 'false');
    await expect(agentGallery).toHaveAttribute('data-pause', 'false');
    await expect(agentGallery.getByRole('button')).toHaveCount(0);
    const agentGalleryInteraction = await agentGallery.evaluate((node) => {
      const primaryCard = node.querySelector('[data-agent-slider-card="primary"]');

      return {
        pointerEvents: getComputedStyle(node).pointerEvents,
        cardTouchAction: primaryCard ? getComputedStyle(primaryCard).touchAction : null,
      };
    });
    expect(agentGalleryInteraction.pointerEvents).toBe('auto');
    expect(agentGalleryInteraction.cardTouchAction).toContain('pan-x');
    const agentGalleryBox = await agentGallery.boundingBox();
    expect(agentGalleryBox).not.toBeNull();
    await page.mouse.click(
      agentGalleryBox!.x + agentGalleryBox!.width / 2,
      agentGalleryBox!.y + agentGalleryBox!.height / 2,
    );
    await expect(page.getByRole('dialog', { name: /contact form/i })).toHaveCount(0);

    await page.getByRole('button', { name: /request access/i }).first().click();
    const dialog = page.getByRole('dialog', { name: /contact form/i });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading', { name: /^request pico access$/i })).toBeVisible();
    await dialog.getByLabel(/work email/i).fill('operator@example.com');
    await dialog.getByLabel(/^name$/i).fill('Pico Operator');
    await dialog.getByLabel(/company/i).fill('MUTX Lab');
    await dialog.getByLabel(/anything we should know/i).fill('I need to recover a broken agent setup.');
    await dialog.getByRole('button', { name: /request access/i }).click();
    await expect(dialog.getByText(/request received/i)).toBeVisible();
    expect(contactPayload.current?.source).toBe('pico-waitlist');
    expect(new URL(page.url()).pathname).toBe('/pico');
  });

  test('pico WIP guard uses the mascot bubble and returns visitors to root', async ({ page }) => {
    await page.goto('/pico/wip', { waitUntil: 'domcontentloaded' });

    await expect(page.getByTestId('pico-host-guard')).toBeVisible();
    await expect(page.getByTestId('pico-wip-speech')).toContainText(/you're not supposed to be here/i);
    await expect(page.getByRole('link', { name: /back to waitlist/i })).toBeVisible();

    await page.waitForURL('**/', { timeout: 5000 });
    expect(new URL(page.url()).pathname).toBe('/');
  });

  test('pico pricing route keeps live plans and support together', async ({
    page,
  }) => {
    await page.goto('/pico/pricing', { waitUntil: 'domcontentloaded' });

    await expect(page.getByTestId('pico-pricing-route')).toBeVisible();
    await expect(
      page.getByRole('heading', { name: /choose a plan\./i }),
    ).toBeVisible();
    const livePlans = page.getByTestId('pico-pricing-live-plans');
    await expect(livePlans).toContainText(/\$0\/mo/i);
    await expect(livePlans).toContainText(/\$9\/mo/i);
    await expect(livePlans).toContainText(/\$29\/mo/i);
    await expect(livePlans.getByRole('heading', { name: /^enterprise$/i })).toBeVisible();
    await expect(livePlans.getByRole('link', { name: /book planning call/i })).toBeVisible();
    await expect(
      page.getByText(/start free\. upgrade when pico is doing enough work/i).last(),
    ).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/pricing');
  });

  test('pico pricing localizes navigation, plan state, and checkout actions', async ({
    page,
  }) => {
    await page.goto('/pico/pricing', { waitUntil: 'domcontentloaded' });

    await page.getByLabel(/interface language/i).selectOption('it');
    await expect(
      page.getByRole('heading', { name: /scegli il piano adatto alle tue esigenze/i }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: /richiedi accesso/i })).toBeVisible();

    const plans = page.getByTestId('pico-pricing-live-plans');
    await expect(plans).toContainText(/predefinito per operatori/i);
    await expect(plans.getByRole('button', { name: /scegli starter/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /torna alla landing/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /parla con il supporto/i })).toBeVisible();
  });

  test('pico support route keeps setup context, packet, and return step together', async ({
    page,
  }) => {
    await stubPicoProductApis(page)
    await page.goto('/pico/support', { waitUntil: 'domcontentloaded' })

    await expect(page.getByTestId('pico-support-hero-signal')).toBeVisible()
    await expect(
      page.getByRole('heading', { name: /send the setup context we need to help\./i }),
    ).toBeVisible()
    await expect(page.getByTestId('pico-support-escalation-standards')).toBeVisible()
    await expect(page.getByTestId('pico-support-return-map')).toBeVisible()
    await expect(
      page.getByText(/human help is for the parts most users do not want to handle alone/i),
    ).toBeVisible()
    expect(new URL(page.url()).pathname).toBe('/pico/support')
  })

  test('pico tutor route keeps the question packet and next move visible', async ({
    page,
  }) => {
    await stubPicoProductApis(page)
    await page.goto('/pico/tutor?lesson=install-hermes-locally', { waitUntil: 'domcontentloaded' })

    await expect(page.getByTestId('pico-tutor-hero-signal')).toBeVisible()
    await expect(
      page.getByRole('heading', { name: /attach the blocked lesson and narrow the answer to one move\./i }),
    ).toBeVisible()
    await expect(page.getByTestId('pico-tutor-crit-desk')).toBeVisible()
    await expect(page.getByText(/this is not general chat/i)).toBeVisible()
    expect(new URL(page.url()).pathname).toBe('/pico/tutor')
  })

  test('pico autopilot route keeps run, spend, and approvals together', async ({
    page,
  }) => {
    await stubPicoProductApis(page)
    await page.goto('/pico/autopilot', { waitUntil: 'domcontentloaded' })

    await expect(page.getByTestId('pico-autopilot-hero-signal')).toBeVisible()
    await expect(
      page.getByRole('heading', { name: /keep run state, spend, and approvals together\./i }),
    ).toBeVisible()
    await expect(page.getByTestId('pico-autopilot-operator-doctrine')).toBeVisible()
    await expect(page.getByTestId('pico-autopilot-control-protocol')).toBeVisible()
    await expect(page.getByText(/keep the last run, live spend, and risky actions visible/i)).toBeVisible()
    expect(new URL(page.url()).pathname).toBe('/pico/autopilot')
  })

  test('pico product routes render live surfaces and linked lesson flows stay inside /pico', async ({ page }) => {
    await stubPicoProductApis(page);

    const productRoutes = [
      { href: '/pico/onboarding', heading: /get to your first working agent fast/i },
      { href: '/pico/academy', heading: /install hermes locally/i },
      { href: '/pico/academy/install-hermes-locally', heading: /install hermes locally/i },
      { href: '/pico/tutor', heading: /ask for the exact next step/i },
      { href: '/pico/autopilot', heading: /run agents with review where it matters/i },
      { href: '/pico/support', heading: /get a human when setup needs guidance/i },
    ];

    for (const route of productRoutes) {
      await page.goto(route.href, { waitUntil: 'domcontentloaded' });
      if (route.href.startsWith('/pico/academy/') && route.href !== '/pico/academy') {
        await expect(page.getByRole('heading', { level: 1, name: route.heading })).toBeVisible();
      } else {
        await expect(page.getByRole('heading', { name: route.heading })).toBeVisible();
      }
      if (route.href === '/pico/academy') {
        await expect(page.getByTestId('pico-academy-mission-billboard')).toBeVisible();
        await expect(page.getByTestId('pico-academy-progress-strip')).toBeVisible();
        await expect(page.getByTestId('pico-academy-campaign-map')).toBeVisible();
        await expect(page.locator('main').getByRole('link', { name: /install hermes now/i }).first()).toBeVisible();
        await expect(page.getByTestId('pico-academy-workspace-summary')).toBeVisible();
        await expect(page.getByText(/surface count/i)).toHaveCount(0);
      } else {
        await expect(page.getByTestId('pico-surface-compass')).toBeVisible();
      }
      if (route.href === '/pico/academy/install-hermes-locally') {
        await expect(page.getByTestId('pico-lesson-workspace')).toBeVisible();
        await expect(page.getByTestId('pico-lesson-proof')).toBeVisible();
        await expect(page.getByTestId('pico-lesson-campaign-hero')).toBeVisible();
      }
      expect(new URL(page.url()).pathname).toBe(route.href);
    }

    await expect(page.getByText(/signed in as operator@mutx\.dev/i)).toBeVisible();
    await expect(page.getByText(/email verified/i)).toBeVisible();
    await expect(page.getByText(/2 webhooks/i)).toBeVisible();

    await page.goto('/pico/onboarding', { waitUntil: 'domcontentloaded' });
    await page.getByRole('link', { name: /go to next chapter: lessons/i }).first().click();
    await expect(page.getByRole('heading', { name: /install hermes locally/i })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/academy');

    await page.goto('/pico/academy/install-hermes-locally', { waitUntil: 'domcontentloaded' });
    await page.getByRole('link', { name: /ask the tutor about this lesson/i }).click();
    await expect(page.getByText(/you are asking about install hermes locally/i)).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/tutor');
    expect(new URL(page.url()).searchParams.get('lesson')).toBe('install-hermes-locally');

    await page.goto('/pico/academy/run-your-first-agent', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { level: 1, name: /run your first agent/i })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/academy/run-your-first-agent');

    await page.goto('/pico/academy', { waitUntil: 'domcontentloaded' });
    await page.locator('summary').filter({ hasText: /platform settings/i }).click();
    await expect(page.getByTestId('pico-platform-surface')).toBeVisible();
    await expect(page.getByTestId('pico-platform-active-surface')).toContainText(/academy/i);
    await expect(page.getByTestId('pico-platform-surface-memory')).toBeVisible();
  });

  test('pico mobile route flow stays usable across onboarding, lessons, tutor, support, and autopilot', async ({ page }) => {
    await stubPicoProductApis(page);
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto('/pico/onboarding', { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('pico-mobile-product-nav')).toBeVisible();
    await expect(page.getByRole('heading', { name: /get to your first working agent fast/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /go to next chapter: lessons/i }).first()).toBeVisible();

    await page.getByRole('link', { name: /go to next chapter: lessons/i }).first().click();
    await expect(page.getByTestId('pico-mobile-product-nav')).toBeVisible();
    await expect(page.getByTestId('pico-mobile-product-nav').getByRole('button', { name: /help/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /install hermes locally/i })).toBeVisible();
    await expect(page.getByTestId('pico-academy-mission-billboard')).toBeVisible();
    await expect(page.getByTestId('pico-academy-progress-strip')).toBeVisible();
    await expect(page.locator('main').getByRole('link', { name: /install hermes now/i }).first()).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/academy');

    await page.goto('/pico/academy/install-hermes-locally', { waitUntil: 'domcontentloaded' });
    await page.getByRole('link', { name: /ask the tutor about this lesson/i }).click();
    await expect(page.getByText(/you are asking about install hermes locally/i)).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/tutor');

    await page.getByRole('link', { name: /get human help|get setup help/i }).first().click();
    await expect(page.getByRole('heading', { name: /get a human when setup needs guidance/i })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/support');

    await page.getByRole('link', { name: /open autopilot/i }).first().click();
    await expect(page.getByRole('heading', { name: /run agents with review where it matters/i })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/autopilot');
  });

  test('pico onboarding hides the blocked first-prompt shortcut until install is complete', async ({ page }) => {
    await stubPicoProductApis(page);

    await page.goto('/pico/onboarding', { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('link', { name: /already installed\? go to first prompt/i })).toHaveCount(0);
    await page.getByRole('link', { name: /install hermes now/i }).first().click();
    await expect(page.getByRole('heading', { level: 1, name: /install hermes locally/i })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/academy/install-hermes-locally');
  });

  test('pico support CTA opens a real escalation intake instead of prereg copy', async ({ page }) => {
    await stubPicoProductApis(page, { authenticated: false });

    await page.goto('/pico/support', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: /^book guidance$/i }).first().click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading', { name: /tell us where setup is blocked/i })).toBeVisible();
    await expect(dialog.getByRole('button', { name: /send support request/i })).toBeVisible();
    await expect(dialog.getByText(/pre-register|early access|preregistrati|accesso anticipato/i)).toHaveCount(0);
  });

  test('pico academy shell toggles keep atlas and recovery inside the product', async ({ page }) => {
    await stubPicoProductApis(page);

    await page.goto('/pico/academy', { waitUntil: 'domcontentloaded' });
    await page.locator('header').getByRole('button', { name: 'Map', exact: true }).click();
    await expect(page.getByText(/focus mode is active/i)).toBeVisible();

    await page.locator('header').getByRole('button', { name: 'Help', exact: true }).click();
    await expect(page.getByTestId('pico-help-lane-panel')).toBeVisible();

    await page.getByTestId('pico-help-lane-panel').getByRole('link', { name: /open support lane/i }).click();
    await expect(page.getByRole('heading', { name: /get a human when setup needs guidance/i })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/support');
  });

  test('pico quick tour can be dismissed and reopened without owning the flow', async ({ page }) => {
    await stubPicoProductApis(page);

    await page.goto('/pico/academy', { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('pico-welcome-tour')).toHaveCount(0);
    await page.getByTestId('pico-open-tour').click();
    await expect(page.getByTestId('pico-welcome-tour')).toBeVisible();
    await expect(page.getByTestId('pico-welcome-tour')).toContainText(/learn the flow once, then close it\./i);
    await page.getByRole('button', { name: /^next$/i }).click();
    await expect(page.getByTestId('pico-welcome-tour')).toContainText(/work on one setup step at a time\./i);

    await page.getByRole('button', { name: /close quick tour/i }).click();
    await expect(page.getByTestId('pico-welcome-tour')).toHaveCount(0);

    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('pico-welcome-tour')).toHaveCount(0);

    await page.getByTestId('pico-open-tour').click();
    await expect(page.getByTestId('pico-welcome-tour')).toBeVisible();
  });

  test('pico route correction panels keep operators inside the product', async ({ page }) => {
    await stubPicoProductApis(page);

    await page.goto('/pico/tutor?lesson=install-hermes-locally', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(/you are asking about install hermes locally/i)).toBeVisible();
    await Promise.all([
      page.waitForURL('**/pico/academy/install-hermes-locally', { waitUntil: 'domcontentloaded' }),
      page.getByRole('link', { name: 'Return to blocked lesson', exact: true }).click(),
    ]);
    await expect(page.getByRole('heading', { level: 1, name: /install hermes locally/i })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/academy/install-hermes-locally');

    await page.goto('/pico/autopilot', { waitUntil: 'domcontentloaded' });
    await page.getByRole('link', { name: 'Ask tutor about the next move', exact: true }).click();
    await expect(page.getByRole('heading', { name: /ask for the exact next step/i })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/tutor');
    expect(new URL(page.url()).searchParams.get('lesson')).toBe('install-hermes-locally');

    await page.goto('/pico/support', { waitUntil: 'domcontentloaded' });
    await page.getByRole('link', { name: /open autopilot/i }).first().click();
    await expect(page.getByRole('heading', { name: /run agents with review where it matters/i })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/pico/autopilot');
  });

  test('pico tutor renders structured guidance and evidence for a blocked lesson', async ({ page }) => {
    await stubPicoProductApis(page);

    await page.goto('/pico/tutor?lesson=run-your-first-agent', { waitUntil: 'domcontentloaded' });
    await page.getByPlaceholder(/describe the blocker/i).fill('Hermes installed but I need the exact next move.');
    await page.getByRole('button', { name: /get next step/i }).click();

    await expect(page.getByText(/^Situation$/i)).toBeVisible();
    await expect(page.getByText(/^Diagnosis$/i)).toBeVisible();
    await expect(page.getByText(/^Commands$/i)).toBeVisible();
    await expect(page.getByText(/^Official links$/i)).toBeVisible();
    await expect(page.getByText(/move into the first prompt lesson/i)).toBeVisible();
    await expect(page.getByRole('link', { name: 'github.com' })).toHaveAttribute(
      'href',
      'https://github.com/nousresearch/hermes-agent',
    );
  });

  test('pico tutor lets an authenticated operator connect and disconnect an OpenAI key without leaving the flow', async ({ page }) => {
    await stubPicoProductApis(page);
    await page.goto('/pico/tutor?lesson=install-hermes-locally');

    await expect(page.getByTestId('pico-openai-connect-panel')).toBeVisible();
    await expect(page.getByTestId('pico-openai-connect-status')).toContainText(/no openai key is connected/i);

    await page.getByPlaceholder('sk-proj-...').fill('sk-proj-test-openai-connection-1234');
    await page.getByRole('button', { name: /connect openai/i }).click();

    await expect(page.getByTestId('pico-openai-connect-status')).toContainText(/active for live tutor answers/i);
    await expect(page.getByText(/connected as ••••1234/i)).toBeVisible();

    await page.getByRole('button', { name: /disconnect openai/i }).click();
    await expect(page.getByTestId('pico-openai-connect-status')).toContainText(/no openai key is connected/i);
  });

  test('pico lesson workspace persists execution context back into the academy', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (error) => {
      pageErrors.push(error.message);
    });

    await stubPicoProductApis(page);

    await page.goto('/pico/academy/install-hermes-locally', { waitUntil: 'domcontentloaded' });
    await page.getByTestId('pico-step-toggle-first').click();
    await page.getByTestId('pico-lesson-proof').fill('Hermes opened from a fresh shell and returned version output.');

    await page.goto('/pico/academy', { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('pico-academy-workspace-summary')).toBeVisible();
    await expect(page.getByTestId('pico-academy-workspace-summary').getByText(/1\/3 steps/i)).toBeVisible();
    await expect(page.getByTestId('pico-academy-workspace-summary').getByText(/^saved$/i)).toBeVisible();

    await page.goto('/pico/onboarding', { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('pico-onboarding-mission-board')).toBeVisible();
    await expect(page.getByTestId('pico-onboarding-install-mission').getByText(/1\/3 steps/i)).toBeVisible();
    await expect(page.getByTestId('pico-onboarding-install-mission').getByText(/^saved$/i)).toBeVisible();

    await page.goto('/pico/autopilot', { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('pico-autopilot-academy-context')).toBeVisible();
    await expect(page.getByTestId('pico-autopilot-academy-context').getByText(/1\/3/i)).toBeVisible();
    await expect(page.getByTestId('pico-autopilot-academy-context').getByText(/^saved$/i)).toBeVisible();
    expect(
      pageErrors.filter((error) => /hydration failed|server rendered text didn't match/i.test(error))
    ).toHaveLength(0);
  });

  test('pico product routes expose hosted provider auth when no session is attached', async ({ page }) => {
    await stubPicoProductApis(page, { authenticated: false });

    await page.goto('/pico/onboarding', { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', { name: /get to your first working agent fast/i })).toBeVisible();
    await expect(page.getByText(/hosted session required/i)).toBeVisible();
    await expect(page.getByRole('link', { name: /^sign in$/i })).toHaveAttribute(
      'href',
      /\/login\?next=%2Fpico%2Fonboarding/i,
    );
    await expect(page.getByRole('link', { name: /^create account$/i })).toHaveAttribute(
      'href',
      /\/register\?next=%2Fpico%2Fonboarding/i,
    );
    await expect(page.getByRole('link', { name: /continue with google/i })).toHaveAttribute(
      'href',
      /\/api\/auth\/oauth\/google\/start\?intent=login&next=%2Fpico%2Fonboarding/i,
    );
    await expect(page.getByRole('link', { name: /continue with github/i })).toHaveAttribute(
      'href',
      /\/api\/auth\/oauth\/github\/start\?intent=login&next=%2Fpico%2Fonboarding/i,
    );
    await expect(page.getByRole('link', { name: /continue with discord/i })).toHaveAttribute(
      'href',
      /\/api\/auth\/oauth\/discord\/start\?intent=login&next=%2Fpico%2Fonboarding/i,
    );
  });

  test('no console errors or remote Guild asset requests', async ({ page }) => {
    const errors: string[] = [];
    const requestUrls: string[] = [];
    const ignoredErrorPatterns = [
      /favicon\.ico/i,
      /favicon/i,
      /Failed to load resource: the server responded with a status of 503 \(Service Unavailable\)/i,
      /Image corrupt or truncated/i,
      /downloadable font: STAT: Invalid nameID: 17 .*Doto/i,
      /downloadable font: Table discarded .*Doto/i,
    ];

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    page.on('pageerror', (error) => {
      errors.push(error.message);
    });

    page.on('request', (request) => {
      requestUrls.push(request.url());
    });

    page.on('response', (response) => {
      if (response.status() >= 400 && !response.url().includes('/api/turnstile/site-key')) {
        console.log('HTTP_ERROR', response.status(), response.url());
      }
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);

    const criticalErrors = errors.filter(
      (error) => !ignoredErrorPatterns.some((pattern) => pattern.test(error))
    );

    expect(criticalErrors, 'Console errors: ' + criticalErrors.join('; ')).toHaveLength(0);
    expect(
      requestUrls.filter((url) => /guild\.ai|cdn\.prod\.website-files\.com/i.test(url)),
      'Unexpected remote Guild asset requests'
    ).toHaveLength(0);
    expect(
      requestUrls.filter((url) => /marketing\/loader\/mutx-logo-loader-fast\.webm/i.test(url)),
      'Unexpected stale loader asset requests'
    ).toHaveLength(0);
  });
});

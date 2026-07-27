"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, CheckCircle2, Loader2 } from "lucide-react";

import { extractApiErrorMessage } from "@/components/app/http";
import { PicoAuthPreviewIntro } from "@/components/auth/PicoAuthPreviewIntro";
import { AuthSurface } from "@/components/site/AuthSurface";
import styles from "@/components/site/marketing/MarketingCore.module.css";
import { buildOAuthStartHref, oauthProviders } from "@/lib/auth/oauth";
import { resolveRedirectPath } from "@/lib/auth/redirects";

type AuthMode = "login" | "register";
type AuthPageHostVariant = "default" | "pico";

type AuthPageProps = {
  mode: AuthMode;
  nextPath?: string | null;
  fallbackPath?: string;
  hostVariant?: AuthPageHostVariant;
  initialError?: string | null;
  initialEmail?: string | null;
};

const authContent = {
  default: {
    login: {
      eyebrow: "Sign in",
      title: "Pick up where you left off.",
      description:
        "Open the workspace, runs, and controls tied to your MUTX account.",
      asideEyebrow: "After sign-in",
      asideTitle: "Your workspace, ready when you are.",
      asideBody:
        "Your team, permissions, deployment state, and run history load from the same account.",
      highlights: [
        "One account for hosted work and desktop control.",
        "Your permissions load with the workspace.",
        "Failed sign-ins explain what went wrong.",
      ],
      heading: "Welcome back",
      subheading:
        "Use a provider or password and continue into the dashboard.",
      submitLabel: "Sign in",
      loadingLabel: "Signing in",
    },
    register: {
      eyebrow: "Create account",
      title: "Set up your MUTX workspace.",
      description:
        "Create one account for the dashboard, desktop app, and the work your agents run.",
      asideEyebrow: "What you get",
      asideTitle: "A workspace that belongs to your team.",
      asideBody:
        "Your identity, permissions, run history, and deployment records stay together from the first session.",
      highlights: [
        "Sign up with email or a provider.",
        "Verification returns you to the right workspace.",
        "Account errors stay visible and actionable.",
      ],
      heading: "Create your account",
      subheading:
        "Choose the fastest path into your hosted dashboard.",
      submitLabel: "Sign up",
      loadingLabel: "Creating account",
    },
  },
  pico: {
    login: {
      eyebrow: "Pico sign-in",
      title: "Come back to your work.",
      description:
        "Sign in to restore your lessons, setup, and progress across Pico.",
      asideEyebrow: "Your workspace",
      asideTitle: "Pico remembers where you stopped.",
      asideBody:
        "Your current lesson, saved proof, setup state, and support context return with your account.",
      highlights: [
        "Resume lessons and saved proof.",
        "Keep setup progress across devices.",
        "Return to the same support context.",
      ],
      heading: "Enter the current Pico build",
      subheading:
        "Use a provider or email to open the preview and save your place.",
      submitLabel: "Enter Pico",
      loadingLabel: "Opening Pico",
    },
    register: {
      eyebrow: "Create Pico account",
      title: "Give your work somewhere to live.",
      description:
        "Save your setup, lessons, and progress to one Pico account.",
      asideEyebrow: "Why an account",
      asideTitle: "So you never restart from zero.",
      asideBody:
        "Your current route, saved proof, and support history stay attached as you move through the product.",
      highlights: [
        "One account for onboarding and Academy.",
        "Verification returns you to Pico.",
        "Your progress persists between sessions.",
      ],
      heading: "Create your Pico preview account",
      subheading:
        "Sign up once, save your place, and keep following the product as it improves.",
      submitLabel: "Create preview account",
      loadingLabel: "Creating preview account",
    },
  },
} as const;

function buildAuthHref(mode: AuthMode, nextPath: string) {
  return `/${mode}?next=${encodeURIComponent(nextPath)}`;
}

export function AuthPage({
  mode,
  nextPath,
  fallbackPath = "/dashboard",
  hostVariant = "default",
  initialError,
  initialEmail,
}: AuthPageProps) {
  const router = useRouter();
  const content = authContent[hostVariant][mode];
  const isRegister = mode === "register";
  const isPicoPreview = hostVariant === "pico";
  const redirectPath = resolveRedirectPath(nextPath, fallbackPath);

  const [name, setName] = useState("");
  const [email, setEmail] = useState(initialEmail ?? "");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState(initialError ?? "");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [resendingVerification, setResendingVerification] = useState(false);

  const verificationError = /verification/i.test(error);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isRegister && password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    if (isRegister && password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setLoading(true);
    setError("");
    setNotice("");

    try {
      const payload =
        mode === "login" ? { email, password } : { email, password, name };

      const response = await fetch(
        mode === "login" ? "/api/auth/login" : "/api/auth/register",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );

      const responsePayload = await response.json().catch(() => ({
        detail:
          mode === "login" ? "Failed to sign in" : "Failed to create account",
      }));

      if (!response.ok) {
        throw new Error(
          extractApiErrorMessage(
            responsePayload,
            mode === "login" ? "Failed to sign in" : "Failed to create account",
          ),
        );
      }

      if (isRegister && responsePayload.requires_email_verification) {
        const verificationParams = new URLSearchParams({
          email,
          next: redirectPath,
        });
        router.replace(`/verify-email?${verificationParams.toString()}`);
        router.refresh();
        return;
      }

      router.replace(redirectPath);
      router.refresh();
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : mode === "login"
            ? "Failed to sign in"
            : "Failed to create account",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleResendVerification() {
    if (!email) {
      setError("Enter your email address first");
      return;
    }

    setResendingVerification(true);
    setNotice("");

    try {
      const response = await fetch("/api/auth/resend-verification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      const payload = await response.json().catch(() => ({
        detail: "Failed to resend verification email",
      }));

      if (!response.ok) {
        throw new Error(
          extractApiErrorMessage(
            payload,
            "Failed to resend verification email",
          ),
        );
      }

      setNotice(payload.message || "Verification email sent");
    } catch (resendError) {
      setError(
        resendError instanceof Error
          ? resendError.message
          : "Failed to resend verification email",
      );
    } finally {
      setResendingVerification(false);
    }
  }

  return (
    <AuthSurface {...content} variant="access" hostVariant={hostVariant}>
      {isPicoPreview ? <PicoAuthPreviewIntro nextPath={redirectPath} /> : null}
      <div className={styles.formWrap}>
        {isPicoPreview ? (
          <div className="rounded-[26px] border border-[rgba(159,255,78,0.18)] bg-[linear-gradient(180deg,rgba(11,20,9,0.98),rgba(6,13,6,0.96))] px-4 py-4 text-[#f3faee] shadow-[0_24px_54px_rgba(4,10,3,0.3)] sm:px-5">
            <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.22em] text-[rgba(223,255,154,0.8)]">
              Pico preview note
            </p>
            <p className="mt-3 text-sm leading-7 text-[rgba(243,250,238,0.82)]">
              Pico is still being built. This login is here so the preview can
              remember your progress and let you come back to the same place
              later.
            </p>
          </div>
        ) : null}

        <div>
          <h2 className={styles.sectionTitle}>{content.heading}</h2>
          <p className={styles.bodyText}>{content.subheading}</p>
        </div>

        <div className="grid gap-2">
          {oauthProviders.map((provider) => (
            <Link
              key={provider.id}
              href={buildOAuthStartHref(provider.id, mode, redirectPath)}
              prefetch={false}
              className={`${styles.buttonSecondary} w-full`}
            >
              {provider.buttonLabel}
              <ArrowRight className="h-4 w-4" />
            </Link>
          ))}
        </div>

        <div
          className={
            isPicoPreview
              ? "flex items-center gap-3 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[rgba(113,145,103,0.72)]"
              : "flex items-center gap-3 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#675b53]"
          }
        >
          <span
            className={
              isPicoPreview
                ? "h-px flex-1 bg-[rgba(159,255,78,0.18)]"
                : "h-px flex-1 bg-[rgba(58,38,25,0.16)]"
            }
          />
          Or use email
          <span
            className={
              isPicoPreview
                ? "h-px flex-1 bg-[rgba(159,255,78,0.18)]"
                : "h-px flex-1 bg-[rgba(58,38,25,0.16)]"
            }
          />
        </div>

        <form onSubmit={handleSubmit} className={styles.formWrap}>
          {isRegister ? (
            <div className={styles.field}>
              <label htmlFor="name" className={styles.fieldLabel}>
                Name
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Your name"
                required
                autoComplete="name"
                className={styles.input}
              />
            </div>
          ) : null}

          <div className={styles.field}>
            <label htmlFor="email" className={styles.fieldLabel}>
              Email address
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
              required
              autoComplete="email"
              className={styles.input}
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="password" className={styles.fieldLabel}>
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              required
              autoComplete={isRegister ? "new-password" : "current-password"}
              className={styles.input}
            />
          </div>

          {isRegister ? (
            <div className={styles.field}>
              <label htmlFor="confirmPassword" className={styles.fieldLabel}>
                Confirm password
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder="••••••••"
                required
                autoComplete="new-password"
                className={styles.input}
              />
            </div>
          ) : null}

          {notice ? (
            <div className={styles.success} role="status">
              <CheckCircle2 className="h-4 w-4" />
              {notice}
            </div>
          ) : null}

          {error ? (
            <div className={styles.error} role="alert">
              <AlertCircle className="h-4 w-4" />
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={loading}
            className={`${styles.buttonPrimary} w-full disabled:cursor-not-allowed disabled:opacity-60`}
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {content.loadingLabel}
              </>
            ) : (
              <>
                {content.submitLabel}
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </button>
        </form>

        <div className={styles.utilityLinks}>
          {mode === "login" ? (
            <>
              <Link href="/forgot-password" className={styles.inlineLink}>
                Forgot password?
              </Link>
              {verificationError ? (
                <button
                  type="button"
                  onClick={() => void handleResendVerification()}
                  disabled={resendingVerification}
                  className={styles.inlineLink}
                >
                  {resendingVerification
                    ? "Sending verification…"
                    : "Resend verification"}
                </button>
              ) : null}
              <p className={styles.bodyText}>
                Need access?{" "}
                <Link
                  href={buildAuthHref("register", redirectPath)}
                  className={styles.inlineLink}
                >
                  Create one
                </Link>
              </p>
            </>
          ) : (
            <p className={styles.bodyText}>
              Already have an account?{" "}
              <Link
                href={buildAuthHref("login", redirectPath)}
                className={styles.inlineLink}
              >
                Sign in
              </Link>
            </p>
          )}
        </div>
      </div>
    </AuthSurface>
  );
}

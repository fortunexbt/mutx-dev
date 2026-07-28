"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, CheckCircle2, Loader2 } from "lucide-react";

import { extractApiErrorMessage } from "@/components/app/http";
import { AuthSurface } from "@/components/site/AuthSurface";
import styles from "@/components/site/marketing/MarketingCore.module.css";
import { buildOAuthStartHref, oauthProviders } from "@/lib/auth/oauth";
import { resolveRedirectPath } from "@/lib/auth/redirects";

type AuthMode = "login" | "register";
type AuthErrorTarget = "email" | "password" | "confirmPassword" | "form" | null;

type AuthPageProps = {
  mode: AuthMode;
  nextPath?: string | null;
  fallbackPath?: string;
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
} as const;

function buildAuthHref(mode: AuthMode, nextPath: string) {
  return `/${mode}?next=${encodeURIComponent(nextPath)}`;
}

export function AuthPage({
  mode,
  nextPath,
  fallbackPath = "/dashboard",
  initialError,
  initialEmail,
}: AuthPageProps) {
  const router = useRouter();
  const content = authContent.default[mode];
  const isRegister = mode === "register";
  const redirectPath = resolveRedirectPath(nextPath, fallbackPath);
  const errorId = `auth-${mode}-error`;

  const [name, setName] = useState("");
  const [email, setEmail] = useState(initialEmail ?? "");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState(initialError ?? "");
  const [errorTarget, setErrorTarget] = useState<AuthErrorTarget>(
    initialError ? "form" : null,
  );
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [resendingVerification, setResendingVerification] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmPasswordRef = useRef<HTMLInputElement>(null);

  const verificationError = /verification/i.test(error);

  function clearFieldError(field: Exclude<AuthErrorTarget, "form" | null>) {
    if (errorTarget !== field) return;
    setError("");
    setErrorTarget(null);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isRegister && password !== confirmPassword) {
      setError("Passwords do not match");
      setErrorTarget("confirmPassword");
      confirmPasswordRef.current?.focus();
      return;
    }

    if (isRegister && password.length < 8) {
      setError("Password must be at least 8 characters");
      setErrorTarget("password");
      passwordRef.current?.focus();
      return;
    }

    setLoading(true);
    setError("");
    setErrorTarget(null);
    setNotice("");

    try {
      const payload =
        mode === "login"
          ? { email, password }
          : { email, password, name, return_path: redirectPath };

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
        if (responsePayload.verification_email_sent === false) {
          verificationParams.set("delivery", "failed");
        }
        router.replace(`/verify-email?${verificationParams.toString()}`);
        router.refresh();
        return;
      }

      router.replace(redirectPath);
      router.refresh();
    } catch (submitError) {
      setErrorTarget("form");
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
      setErrorTarget("email");
      emailRef.current?.focus();
      return;
    }

    setResendingVerification(true);
    setError("");
    setErrorTarget(null);
    setNotice("");

    try {
      const response = await fetch("/api/auth/resend-verification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, return_path: redirectPath }),
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
      setErrorTarget("email");
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
    <AuthSurface {...content} variant="access">
      <div className={styles.formWrap}>
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
              <ArrowRight className="rtl-directional-icon h-4 w-4" />
            </Link>
          ))}
        </div>

        <div
          className="flex items-center gap-3 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#675b53]"
          data-auth-divider="default"
        >
          <span className="h-px flex-1 bg-[rgba(58,38,25,0.16)]" data-auth-divider-line />
          Or use email
          <span className="h-px flex-1 bg-[rgba(58,38,25,0.16)]" data-auth-divider-line />
        </div>

        <form
          onSubmit={handleSubmit}
          className={styles.formWrap}
          aria-describedby={error && errorTarget === "form" ? errorId : undefined}
          aria-busy={loading}
        >
          {isRegister ? (
            <div className={styles.field}>
              <label htmlFor="name" className={styles.fieldLabel}>
                Name
              </label>
              <input
                id="name"
                name="name"
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Your name"
                required
                autoComplete="name"
                maxLength={100}
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
              name="email"
              ref={emailRef}
              type="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                clearFieldError("email");
              }}
              placeholder="you@company.com"
              required
              autoComplete="email"
              dir="ltr"
              aria-invalid={error && errorTarget === "email" ? true : undefined}
              aria-describedby={error && errorTarget === "email" ? errorId : undefined}
              className={styles.input}
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="password" className={styles.fieldLabel}>
              Password
            </label>
            <input
              id="password"
              name="password"
              ref={passwordRef}
              type="password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
                clearFieldError("password");
              }}
              placeholder="••••••••"
              required
              autoComplete={isRegister ? "new-password" : "current-password"}
              aria-invalid={error && errorTarget === "password" ? true : undefined}
              aria-describedby={error && errorTarget === "password" ? errorId : undefined}
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
                name="confirm_password"
                ref={confirmPasswordRef}
                type="password"
                value={confirmPassword}
                onChange={(event) => {
                  setConfirmPassword(event.target.value);
                  clearFieldError("confirmPassword");
                }}
                placeholder="••••••••"
                required
                autoComplete="new-password"
                aria-invalid={error && errorTarget === "confirmPassword" ? true : undefined}
                aria-describedby={error && errorTarget === "confirmPassword" ? errorId : undefined}
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
            <div
              id={errorId}
              className={styles.error}
              role="alert"
              aria-live="assertive"
              aria-atomic="true"
            >
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
                <ArrowRight className="rtl-directional-icon h-4 w-4" />
              </>
            )}
          </button>
        </form>

        <div className={styles.utilityLinks}>
          {mode === "login" ? (
            <>
              <Link
                href={`/forgot-password?next=${encodeURIComponent(redirectPath)}`}
                className={styles.inlineLink}
              >
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

import type { NextRequest } from "next/server";

const applyAuthCookies = jest.fn((response, _request, payload) => {
  response.cookies.set("access_token", payload.access_token, {
    path: "/",
    maxAge: payload.expires_in || 1800,
  });

  if (payload.refresh_token) {
    response.cookies.set("refresh_token", payload.refresh_token, {
      path: "/",
      maxAge: 60 * 60 * 24 * 7,
    });
  }
});
const authenticatedFetch = jest.fn();
const clearAuthCookies = jest.fn((response) => {
  response.cookies.set("access_token", "", { path: "/", maxAge: 0 });
  response.cookies.set("refresh_token", "", { path: "/", maxAge: 0 });
});
const getAuthToken = jest.fn();
const getCookieDomain = jest.fn();
const getRefreshToken = jest.fn();
const hasAuthSession = jest.fn();
const shouldUseSecureCookies = jest.fn();

jest.mock("../../app/api/_lib/controlPlane", () => ({
  applyAuthCookies,
  authenticatedFetch,
  clearAuthCookies,
  getApiBaseUrl: () => "http://localhost:8000",
  getAuthToken,
  getCookieDomain,
  getRefreshToken,
  hasAuthSession,
  shouldUseSecureCookies,
}));

function mockRequest(
  cookies: Record<string, string> = {},
  url = "https://app.mutx.dev/api/auth/me",
  headers: HeadersInit = {},
) {
  return {
    url,
    nextUrl: new URL(url),
    headers: new Headers(headers),
    cookies: {
      get: (name: string) =>
        cookies[name] ? { value: cookies[name] } : undefined,
    },
  } as NextRequest;
}

function mockJsonRequest(
  body: unknown,
  url = "https://app.mutx.dev/api/auth/login",
) {
  return {
    url,
    nextUrl: new URL(url),
    cookies: {
      get: () => undefined,
    },
    json: async () => body,
  } as NextRequest;
}

describe("auth route handlers", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    applyAuthCookies.mockClear();
    authenticatedFetch.mockReset();
    clearAuthCookies.mockClear();
    getAuthToken.mockReset();
    getCookieDomain.mockReturnValue(undefined);
    getRefreshToken.mockReset();
    hasAuthSession.mockReset();
    shouldUseSecureCookies.mockReturnValue(false);
    fetchSpy = jest
      .spyOn(global as typeof globalThis, "fetch")
      .mockImplementation(jest.fn());
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  describe("POST /api/auth/login", () => {
    it("returns 400 when email is missing", async () => {
      const { POST } = await import("../../app/api/auth/login/route");

      const response = await POST(mockJsonRequest({ password: "password123" }));

      expect(response.status).toBe(400);
      const body = await response.json();
      expect(body.status).toBe("error");
      expect(body.error.code).toBe("VALIDATION_ERROR");
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("returns 400 when email format is invalid", async () => {
      const { POST } = await import("../../app/api/auth/login/route");

      const response = await POST(
        mockJsonRequest({ email: "not-an-email", password: "password123" }),
      );

      expect(response.status).toBe(400);
      const body = await response.json();
      expect(body.status).toBe("error");
      expect(body.error.code).toBe("VALIDATION_ERROR");
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("returns 400 when password is missing", async () => {
      const { POST } = await import("../../app/api/auth/login/route");

      const response = await POST(
        mockJsonRequest({ email: "operator@mutx.dev" }),
      );

      expect(response.status).toBe(400);
      const body = await response.json();
      expect(body.status).toBe("error");
      expect(body.error.code).toBe("VALIDATION_ERROR");
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("preserves upstream unauthorized responses", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Invalid credentials" }),
      });
      const { POST } = await import("../../app/api/auth/login/route");

      const response = await POST(
        mockJsonRequest({
          email: "operator@mutx.dev",
          password: "wrongpassword",
        }),
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/login",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "operator@mutx.dev",
            password: "wrongpassword",
          }),
          cache: "no-store",
        },
      );
      expect(response.status).toBe(401);
      await expect(response.json()).resolves.toEqual({
        detail: "Invalid credentials",
      });
    });

    it("returns payload and sets auth cookies on successful login", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: "test_access_token",
          refresh_token: "test_refresh_token",
          expires_in: 1800,
        }),
      });
      const { POST } = await import("../../app/api/auth/login/route");

      const response = await POST(
        mockJsonRequest({
          email: "operator@mutx.dev",
          password: "correctpassword",
        }),
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/login",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "operator@mutx.dev",
            password: "correctpassword",
          }),
          cache: "no-store",
        },
      );
      expect(response.status).toBe(200);
      await expect(response.json()).resolves.toEqual({
        access_token: "test_access_token",
        refresh_token: "test_refresh_token",
        expires_in: 1800,
      });
      const setCookieHeader = response.headers.get("set-cookie");
      expect(setCookieHeader).toContain("access_token=");
      expect(setCookieHeader).toContain("refresh_token=");
    });

    it("uses default maxAge when expires_in is absent from login response", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: "test_access_token",
          refresh_token: "test_refresh_token",
        }),
      });
      const { POST } = await import("../../app/api/auth/login/route");

      const response = await POST(
        mockJsonRequest({
          email: "operator@mutx.dev",
          password: "correctpassword",
        }),
      );

      expect(response.status).toBe(200);
      const setCookieHeader = response.headers.get("set-cookie");
      expect(setCookieHeader).toContain("access_token=");
    });
  });

  describe("POST /api/auth/register", () => {
    it("returns 400 when required fields are missing", async () => {
      const { POST } = await import("../../app/api/auth/register/route");

      const response = await POST(mockJsonRequest({}));

      expect(response.status).toBe(400);
      const body = await response.json();
      expect(body.status).toBe("error");
      expect(body.error.code).toBe("VALIDATION_ERROR");
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("returns 400 when password is too short", async () => {
      const { POST } = await import("../../app/api/auth/register/route");

      const response = await POST(
        mockJsonRequest({
          email: "operator@mutx.dev",
          password: "short",
          name: "Operator",
        }),
      );

      expect(response.status).toBe(400);
      const body = await response.json();
      expect(body.status).toBe("error");
      expect(body.error.code).toBe("VALIDATION_ERROR");
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("returns 400 when name is missing", async () => {
      const { POST } = await import("../../app/api/auth/register/route");

      const response = await POST(
        mockJsonRequest({
          email: "operator@mutx.dev",
          password: "securepassword123",
        }),
      );

      expect(response.status).toBe(400);
      const body = await response.json();
      expect(body.status).toBe("error");
      expect(body.error.code).toBe("VALIDATION_ERROR");
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("preserves upstream conflict responses", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ detail: "Email already registered" }),
      });
      const { POST } = await import("../../app/api/auth/register/route");

      const response = await POST(
        mockJsonRequest({
          email: "operator@mutx.dev",
          password: "securepassword123",
          name: "Operator",
        }),
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/register",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "operator@mutx.dev",
            password: "securepassword123",
            name: "Operator",
            verification_origin: "https://app.mutx.dev",
          }),
          cache: "no-store",
        },
      );
      expect(response.status).toBe(409);
      await expect(response.json()).resolves.toEqual({
        detail: "Email already registered",
      });
    });

    it("returns payload and sets auth cookies on successful registration", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => ({
          access_token: "new_access_token",
          refresh_token: "new_refresh_token",
          expires_in: 1800,
        }),
      });
      const { POST } = await import("../../app/api/auth/register/route");

      const response = await POST(
        mockJsonRequest({
          email: "newuser@mutx.dev",
          password: "securepassword123",
          name: "New User",
        }),
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/register",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "newuser@mutx.dev",
            password: "securepassword123",
            name: "New User",
            verification_origin: "https://app.mutx.dev",
          }),
          cache: "no-store",
        },
      );
      expect(response.status).toBe(200);
      await expect(response.json()).resolves.toEqual({
        access_token: "new_access_token",
        refresh_token: "new_refresh_token",
        expires_in: 1800,
      });
      const setCookieHeader = response.headers.get("set-cookie");
      expect(setCookieHeader).toContain("access_token=");
      expect(setCookieHeader).toContain("refresh_token=");
    });

    it("uses the active pico host and preserves the verification return path", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => ({
          requires_email_verification: true,
          message: "Verification email sent",
        }),
      });
      const { POST } = await import("../../app/api/auth/register/route");

      const response = await POST(
        mockJsonRequest(
          {
            email: "newuser@mutx.dev",
            password: "securepassword123",
            name: "New User",
            return_path: "/dashboard/runs?status=held",
          },
          "https://pico.mutx.dev/api/auth/register",
        ),
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/register",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "newuser@mutx.dev",
            password: "securepassword123",
            name: "New User",
            verification_origin: "https://pico.mutx.dev",
            return_path: "/dashboard/runs?status=held",
          }),
          cache: "no-store",
        },
      );
      expect(response.status).toBe(200);
      expect(applyAuthCookies).not.toHaveBeenCalled();
    });

    it("skips auth cookies when registration requires email verification", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => ({
          access_token: "pending_access_token",
          refresh_token: "pending_refresh_token",
          expires_in: 1800,
          requires_email_verification: true,
          verification_email_sent: true,
        }),
      });
      const { POST } = await import("../../app/api/auth/register/route");

      const response = await POST(
        mockJsonRequest(
          {
            email: "verify@mutx.dev",
            password: "securepassword123",
            name: "Verify User",
          },
          "https://app.mutx.dev/api/auth/register",
        ),
      );

      expect(response.status).toBe(200);
      await expect(response.json()).resolves.toEqual({
        access_token: "pending_access_token",
        refresh_token: "pending_refresh_token",
        expires_in: 1800,
        requires_email_verification: true,
        verification_email_sent: true,
      });
      expect(response.headers.get("set-cookie")).toBeNull();
    });
  });

  describe("POST /api/auth/refresh", () => {
    it("returns 401 when refresh cookie is missing", async () => {
      const { POST } = await import("../../app/api/auth/refresh/route");

      const response = await POST({
        json: async () => ({ refresh_token: "body_token" }),
        cookies: {
          get: () => undefined,
        },
      } as unknown as NextRequest);

      expect(response.status).toBe(401);
      await expect(response.json()).resolves.toEqual({
        detail: "Unauthorized",
      });
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("returns 401 when refresh cookie does not match body token", async () => {
      const { POST } = await import("../../app/api/auth/refresh/route");

      const response = await POST({
        json: async () => ({ refresh_token: "body_token" }),
        cookies: {
          get: () => ({ value: "different_cookie_token" }),
        },
      } as unknown as NextRequest);

      expect(response.status).toBe(401);
      await expect(response.json()).resolves.toEqual({
        detail: "Unauthorized",
      });
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("refreshes tokens when refresh cookie matches body token", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: "new_access_token",
          refresh_token: "new_refresh_token",
          expires_in: 1800,
        }),
      });
      getRefreshToken.mockReturnValue("matching_token");
      const { POST } = await import("../../app/api/auth/refresh/route");

      const response = await POST({
        json: async () => ({ refresh_token: "matching_token" }),
        cookies: {
          get: () => ({ value: "matching_token" }),
        },
      } as unknown as NextRequest);

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/refresh",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: "matching_token" }),
          cache: "no-store",
        }),
      );
      expect(response.status).toBe(200);
      await expect(response.json()).resolves.toEqual({
        access_token: "new_access_token",
        expires_in: 1800,
      });
      const setCookieHeader = response.headers.get("set-cookie");
      expect(setCookieHeader).toContain("access_token=");
      expect(setCookieHeader).toContain("refresh_token=");
    });
  });

  describe("POST /api/auth/logout", () => {
    it("returns 200 with success payload", async () => {
      const { POST } = await import("../../app/api/auth/logout/route");
      getRefreshToken.mockReturnValue(null);

      const response = await POST(mockRequest());

      expect(response.status).toBe(200);
      await expect(response.json()).resolves.toEqual({ success: true });
    });

    it("clears auth cookies by setting maxAge to 0", async () => {
      const { POST } = await import("../../app/api/auth/logout/route");
      getRefreshToken.mockReturnValue(null);

      const response = await POST(mockRequest());

      const setCookieHeader = response.headers.get("set-cookie");
      expect(setCookieHeader).toContain("access_token=");
      expect(setCookieHeader).toContain("refresh_token=");
      expect(setCookieHeader).toContain("Max-Age=0");
    });

    it("does not call the backend API when no auth cookies exist", async () => {
      const { POST } = await import("../../app/api/auth/logout/route");
      getRefreshToken.mockReturnValue(null);

      await POST(mockRequest());

      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("best-effort revokes the backend refresh session when tokens exist", async () => {
      getRefreshToken.mockReturnValue("refresh-token");
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ message: "Successfully logged out" }),
      });
      const { POST } = await import("../../app/api/auth/logout/route");

      await POST(
        mockRequest({
          access_token: "access-token",
          refresh_token: "refresh-token",
        }),
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/logout",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer access-token",
          },
          body: JSON.stringify({ refresh_token: "refresh-token" }),
          cache: "no-store",
        },
      );
    });
  });

  describe("POST /api/auth/refresh", () => {
    it("returns 401 when no refresh cookie exists", async () => {
      getRefreshToken.mockReturnValue(null);
      const { POST } = await import("../../app/api/auth/refresh/route");

      const response = await POST(mockRequest());

      expect(response.status).toBe(401);
      await expect(response.json()).resolves.toEqual({
        detail: "Unauthorized",
      });
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("uses the existing refresh cookie to request new auth tokens", async () => {
      getRefreshToken.mockReturnValue("refresh-token");
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: "new_access_token",
          refresh_token: "new_refresh_token",
          expires_in: 1800,
        }),
      });
      const { POST } = await import("../../app/api/auth/refresh/route");

      const request = mockRequest({ refresh_token: "refresh-token" });
      const response = await POST(request);

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/refresh",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: "refresh-token" }),
          cache: "no-store",
        }),
      );
      expect(response.status).toBe(200);
      await expect(response.json()).resolves.toEqual({
        access_token: "new_access_token",
        expires_in: 1800,
      });
      expect(applyAuthCookies).toHaveBeenCalledWith(
        expect.anything(),
        request,
        expect.objectContaining({
          access_token: "new_access_token",
          refresh_token: "new_refresh_token",
        }),
      );
    });
  });

  describe("GET /api/auth/me", () => {
    it("returns 401 when no auth token exists", async () => {
      hasAuthSession.mockReturnValue(false);
      const { GET } = await import("../../app/api/auth/me/route");

      const response = await GET(mockRequest());

      expect(response.status).toBe(401);
      await expect(response.json()).resolves.toEqual({
        detail: "Unauthorized",
      });
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("preserves upstream unauthorized responses", async () => {
      hasAuthSession.mockReturnValue(true);
      const request = mockRequest();
      authenticatedFetch.mockResolvedValue({
        response: {
          status: 401,
          json: async () => ({ detail: "Session expired" }),
        },
        tokenRefreshed: false,
      });
      const { GET } = await import("../../app/api/auth/me/route");

      const response = await GET(request);

      expect(authenticatedFetch).toHaveBeenCalledWith(
        request,
        "http://localhost:8000/v1/auth/me",
        {
          cache: "no-store",
        },
      );
      expect(response.status).toBe(401);
      await expect(response.json()).resolves.toEqual({
        detail: "Session expired",
      });
    });

    it("preserves successful user payloads", async () => {
      hasAuthSession.mockReturnValue(true);
      const request = mockRequest();
      authenticatedFetch.mockResolvedValue({
        response: {
          status: 200,
          json: async () => ({
            id: "user_123",
            email: "operator@mutx.dev",
            name: "Operator",
          }),
        },
        tokenRefreshed: false,
      });
      const { GET } = await import("../../app/api/auth/me/route");

      const response = await GET(request);

      expect(authenticatedFetch).toHaveBeenCalledWith(
        request,
        "http://localhost:8000/v1/auth/me",
        {
          cache: "no-store",
        },
      );
      expect(response.status).toBe(200);
      await expect(response.json()).resolves.toEqual({
        id: "user_123",
        email: "operator@mutx.dev",
        name: "Operator",
      });
    });

    it("applies refreshed auth cookies after session renewal", async () => {
      hasAuthSession.mockReturnValue(true);
      authenticatedFetch.mockResolvedValue({
        response: {
          status: 200,
          json: async () => ({ id: "user_123" }),
        },
        tokenRefreshed: true,
        refreshedTokens: {
          access_token: "new_access_token",
          refresh_token: "new_refresh_token",
          expires_in: 1800,
        },
      });
      const { GET } = await import("../../app/api/auth/me/route");

      const request = mockRequest();
      const response = await GET(request);

      expect(response.status).toBe(200);
      expect(applyAuthCookies).toHaveBeenCalledWith(
        expect.anything(),
        request,
        expect.objectContaining({
          access_token: "new_access_token",
          refresh_token: "new_refresh_token",
        }),
      );
    });
  });

  describe("POST /api/auth/forgot-password", () => {
    it("validates the request body before proxying", async () => {
      const { POST } = await import("../../app/api/auth/forgot-password/route");

      const response = await POST(mockJsonRequest({}));

      expect(response.status).toBe(400);
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("proxies forgot-password requests to the backend", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          message:
            "If an account exists with this email, a password reset link has been sent",
        }),
      });
      const { POST } = await import("../../app/api/auth/forgot-password/route");

      const response = await POST(
        mockJsonRequest({ email: "operator@mutx.dev" }),
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/forgot-password",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "operator@mutx.dev",
            email_link_origin: "https://app.mutx.dev",
          }),
          cache: "no-store",
        },
      );
      expect(response.status).toBe(200);
    });
  });

  describe("POST /api/auth/verify-email", () => {
    it("validates the verification payload before proxying", async () => {
      const { POST } = await import("../../app/api/auth/verify-email/route");

      const response = await POST(
        mockJsonRequest(
          { token: "" },
          "https://app.mutx.dev/api/auth/verify-email",
        ),
      );

      expect(response.status).toBe(400);
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("proxies verification requests to the backend", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ message: "Email has been verified successfully" }),
      });
      const { POST } = await import("../../app/api/auth/verify-email/route");

      const response = await POST(
        mockJsonRequest(
          { token: "verify-token" },
          "https://app.mutx.dev/api/auth/verify-email",
        ),
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/verify-email",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: "verify-token" }),
          cache: "no-store",
        },
      );
      expect(response.status).toBe(200);
    });
  });

  describe("POST /api/auth/resend-verification", () => {
    it("validates the resend payload before proxying", async () => {
      const { POST } =
        await import("../../app/api/auth/resend-verification/route");

      const response = await POST(
        mockJsonRequest(
          {},
          "https://app.mutx.dev/api/auth/resend-verification",
        ),
      );

      expect(response.status).toBe(400);
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("proxies resend-verification requests to the backend", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          message:
            "If an account exists and is not verified, a verification email has been sent",
        }),
      });
      const { POST } =
        await import("../../app/api/auth/resend-verification/route");

      const response = await POST(
        mockJsonRequest(
          { email: "operator@mutx.dev" },
          "https://app.mutx.dev/api/auth/resend-verification",
        ),
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/resend-verification",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "operator@mutx.dev",
            verification_origin: "https://app.mutx.dev",
          }),
          cache: "no-store",
        },
      );
      expect(response.status).toBe(200);
    });
  });

  describe("GET /api/auth/oauth/[provider]/start", () => {
    it("redirects to the provider and stores oauth cookies", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          authorization_url:
            "https://accounts.google.com/o/oauth2/v2/auth?state=test",
          state: "server-bound-state",
        }),
      });
      const { GET } =
        await import("../../app/api/auth/oauth/[provider]/start/route");

      const response = await GET(
        mockRequest(
          {},
          "https://app.mutx.dev/api/auth/oauth/google/start?next=%2Fdashboard%2Fwebhooks&intent=register",
        ),
        { params: Promise.resolve({ provider: "google" }) },
      );

      expect(global.fetch).toHaveBeenCalledWith(
        expect.objectContaining({
          href: expect.stringContaining(
            "http://localhost:8000/v1/auth/oauth/google/authorize?",
          ),
        }),
        { cache: "no-store" },
      );
      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe(
        "https://accounts.google.com/o/oauth2/v2/auth?state=test",
      );
      const setCookieHeader = response.headers.get("set-cookie");
      expect(setCookieHeader).toContain(
        "mutx_oauth_state=server-bound-state",
      );
      expect(setCookieHeader).toContain("mutx_oauth_next=");
      expect(setCookieHeader).toContain("mutx_oauth_intent=");
      expect(setCookieHeader).toContain("SameSite=none");
    });

    it.each(["google", "github", "discord", "apple"])(
      "starts %s OAuth with the pico callback origin",
      async (provider) => {
        (global.fetch as jest.Mock).mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            authorization_url: `https://provider.example/${provider}`,
            state: `server-bound-state-${provider}`,
          }),
        });
        const { GET } =
          await import("../../app/api/auth/oauth/[provider]/start/route");

        const response = await GET(
          mockRequest(
            {},
            `https://pico.mutx.dev/api/auth/oauth/${provider}/start?next=%2Fonboarding&intent=login`,
          ),
          { params: Promise.resolve({ provider }) },
        );

        const authorizeUrl = (global.fetch as jest.Mock).mock.calls[0][0] as URL;
        expect(authorizeUrl.searchParams.get("redirect_uri")).toBe(
          `https://pico.mutx.dev/api/auth/oauth/${provider}/callback`,
        );
        expect(response.status).toBe(307);
        expect(response.headers.get("location")).toBe(
          `https://provider.example/${provider}`,
        );
      },
    );
  });

  describe("GET /api/auth/oauth/[provider]/callback", () => {
    it("ignores spoofed forwarded hosts when exchanging and redirecting", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: "oauth_access_token",
          refresh_token: "oauth_refresh_token",
          expires_in: 1800,
        }),
      });
      const { GET } =
        await import("../../app/api/auth/oauth/[provider]/callback/route");

      const response = await GET(
        mockRequest(
          {
            mutx_oauth_state: "state-123",
            mutx_oauth_next: "/dashboard/webhooks",
            mutx_oauth_intent: "register",
          },
          "https://app.mutx.dev/api/auth/oauth/google/callback?code=provider-code&state=state-123",
          {
            host: "evil.example",
            "x-forwarded-host": "evil.example",
            "x-forwarded-proto": "http",
          },
        ),
        { params: Promise.resolve({ provider: "google" }) },
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/oauth/google/exchange",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            code: "provider-code",
            redirect_uri: "https://app.mutx.dev/api/auth/oauth/google/callback",
            state: "state-123",
          }),
          cache: "no-store",
        },
      );
      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe(
        "https://app.mutx.dev/dashboard/webhooks",
      );
      const setCookieHeader = response.headers.get("set-cookie");
      expect(setCookieHeader).toContain("access_token=");
      expect(setCookieHeader).toContain("refresh_token=");
      expect(setCookieHeader).toContain("mutx_oauth_state=;");
    });

    it("ignores spoofed forwarded hosts on callback failures", async () => {
      const { GET } =
        await import("../../app/api/auth/oauth/[provider]/callback/route");

      const response = await GET(
        mockRequest(
          {
            mutx_oauth_state: "different-state",
            mutx_oauth_next: "/\\evil.example/steal",
            mutx_oauth_intent: "login",
          },
          "https://app.mutx.dev/api/auth/oauth/google/callback?code=provider-code&state=state-123",
          {
            host: "evil.example",
            "x-forwarded-host": "evil.example",
            "x-forwarded-proto": "http",
          },
        ),
        { params: Promise.resolve({ provider: "google" }) },
      );

      expect(global.fetch).not.toHaveBeenCalled();
      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe(
        "https://app.mutx.dev/login?next=%2Fdashboard&error=OAuth+session+expired.+Start+sign-in+again.",
      );
    });

    it("falls back to the pico root when oauth callback has no stored next target", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: "oauth_access_token",
          refresh_token: "oauth_refresh_token",
          expires_in: 1800,
        }),
      });
      const { GET } =
        await import("../../app/api/auth/oauth/[provider]/callback/route");

      const response = await GET(
        mockRequest(
          {
            mutx_oauth_state: "state-123",
            mutx_oauth_intent: "login",
          },
          "https://pico.mutx.dev/api/auth/oauth/google/callback?code=provider-code&state=state-123",
        ),
        { params: Promise.resolve({ provider: "google" }) },
      );

      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe("https://pico.mutx.dev/");
    });

    it("exchanges Apple form_post callbacks with the pico redirect URI", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: "oauth_access_token",
          refresh_token: "oauth_refresh_token",
          expires_in: 1800,
        }),
      });
      const { POST } =
        await import("../../app/api/auth/oauth/[provider]/callback/route");
      const formData = new Map<string, string>([
        ["code", "apple-code"],
        ["state", "state-123"],
      ]);

      const response = await POST(
        {
          ...mockRequest(
            {
              mutx_oauth_state: "state-123",
              mutx_oauth_intent: "login",
            },
            "https://pico.mutx.dev/api/auth/oauth/apple/callback",
          ),
          formData: async () => formData,
        } as unknown as NextRequest,
        { params: Promise.resolve({ provider: "apple" }) },
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/oauth/apple/exchange",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            code: "apple-code",
            redirect_uri: "https://pico.mutx.dev/api/auth/oauth/apple/callback",
            state: "state-123",
          }),
          cache: "no-store",
        },
      );
      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe("https://pico.mutx.dev/");
    });
  });

  describe("POST /api/auth/reset-password", () => {
    it("validates the reset payload before proxying", async () => {
      const { POST } = await import("../../app/api/auth/reset-password/route");

      const response = await POST(
        mockJsonRequest({ token: "", new_password: "short" }),
      );

      expect(response.status).toBe(400);
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("proxies reset-password requests to the backend", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ message: "Password has been reset successfully" }),
      });
      const { POST } = await import("../../app/api/auth/reset-password/route");

      const response = await POST(
        mockJsonRequest({
          token: "reset-token",
          new_password: "StrongPassword123!",
        }),
      );

      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/reset-password",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            token: "reset-token",
            new_password: "StrongPassword123!",
          }),
          cache: "no-store",
        },
      );
      expect(response.status).toBe(200);
    });
  });
});

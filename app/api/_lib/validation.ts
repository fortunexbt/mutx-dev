import { z } from "zod";
import { NextResponse } from "next/server";

const localeSchema = z
  .string()
  .trim()
  .toLowerCase()
  .regex(/^[a-z]{2}(?:-[a-z]{2})?$/, "Invalid locale format")
  .optional();

function validationErrorResponse(
  details: Record<string, { message: string }[]>,
) {
  return NextResponse.json(
    {
      status: "error" as const,
      error: {
        code: "VALIDATION_ERROR",
        message: "Request validation failed",
        details,
      },
    },
    { status: 400 },
  );
}

function invalidJsonResponse() {
  return NextResponse.json(
    {
      status: "error" as const,
      error: {
        code: "INVALID_JSON",
        message: "Invalid JSON in request body",
      },
    },
    { status: 400 },
  );
}

export async function validateData<T extends z.ZodSchema>(
  schema: T,
  body: unknown,
): Promise<
  | { success: true; data: z.infer<T> }
  | { success: false; response: NextResponse }
> {
  const result = await schema.safeParseAsync(body);

  if (!result.success) {
    const formatted = result.error.format();
    const details: Record<string, { message: string }[]> = {};

    for (const [key, value] of Object.entries(formatted)) {
      if (
        key !== "_errors" &&
        value &&
        typeof value === "object" &&
        "_errors" in value
      ) {
        const errObj = value as Record<string, unknown>;
        const errors = errObj._errors as unknown[];
        details[key] = errors.map((msg) => ({ message: String(msg) }));
      }
    }

    return { success: false, response: validationErrorResponse(details) };
  }

  return { success: true, data: result.data };
}

// Generic validation helper
export async function validateRequest<T extends z.ZodSchema>(
  schema: T,
  request: Request,
): Promise<
  | { success: true; data: z.infer<T> }
  | { success: false; response: NextResponse }
> {
  try {
    const body = await request.json();
    return await validateData(schema, body);
  } catch {
    return { success: false, response: invalidJsonResponse() };
  }
}

// Common validation schemas
export const schemas = {
  // Auth schemas
  login: z.object({
    email: z.string().email("Invalid email format"),
    password: z.string().min(1, "Password is required"),
  }),

  register: z.object({
    email: z.string().email("Invalid email format"),
    password: z.string().min(8, "Password must be at least 8 characters"),
    name: z.string().min(1, "Name is required").max(100, "Name too long"),
    return_path: z.string().max(1024, "Return path too long").optional(),
  }),

  localBootstrap: z.object({
    name: z
      .string()
      .min(1, "Name is required")
      .max(100, "Name too long")
      .default("Local Operator"),
  }),

  refresh: z.object({
    refresh_token: z.string().min(1, "Refresh token is required"),
  }),

  forgotPassword: z.object({
    email: z.string().email("Invalid email format"),
    return_path: z.string().max(1024, "Return path too long").optional(),
  }),

  verifyEmail: z.object({
    token: z.string().min(1, "Verification token is required"),
  }),

  resendVerification: z.object({
    email: z.string().email("Invalid email format"),
    return_path: z.string().max(1024, "Return path too long").optional(),
  }),

  resetPassword: z.object({
    token: z.string().min(1, "Reset token is required"),
    new_password: z.string().min(8, "Password must be at least 8 characters"),
  }),

  // Lead schema
  lead: z.object({
    email: z.string().email("Invalid email format"),
    name: z.string().max(100, "Name too long").optional(),
    company: z.string().max(200, "Company name too long").optional(),
    message: z.string().max(2000, "Message too long").optional(),
    locale: localeSchema,
    source: z.string().max(50, "Source too long").optional(),
  }),

  // API Key schemas
  apiKeyCreate: z.object({
    name: z.string().min(1, "Name is required").max(100, "Name too long"),
    expires_in_days: z
      .number()
      .int()
      .positive()
      .max(365, "Max expiry is 365 days")
      .optional(),
  }),

  // Agent schemas
  agentCreate: z
    .object({
      name: z.string().min(1, "Name is required").max(255, "Name too long"),
      description: z.string().max(1000, "Description too long").optional(),
      type: z
        .enum(["openai", "anthropic", "langchain", "custom", "openclaw"])
        .default("openai"),
      config: z
        .union([z.record(z.string(), z.unknown()), z.string()])
        .optional(),
    })
    .strict(),

  agentUpdate: z.object({
    name: z
      .string()
      .min(1, "Name is required")
      .max(100, "Name too long")
      .optional(),
    description: z.string().max(500, "Description too long").optional(),
    type: z.enum(["openai", "anthropic", "langchain", "custom"]).optional(),
    config: z.record(z.string(), z.unknown()).optional(),
  }),

  // Deployment schemas
  deploymentCreate: z
    .object({
      agent_id: z.string().uuid("Invalid agent ID"),
      replicas: z
        .number()
        .int()
        .positive()
        .max(10, "Max replicas is 10")
        .optional(),
    })
    .strict(),

  // Webhook schemas
  webhookCreate: z
    .object({
      url: z.string().url("Invalid URL format").max(512, "URL too long"),
      name: z.string().max(120, "Name too long").optional(),
      events: z
        .array(z.string().min(1, "Event name cannot be empty"))
        .default(["*"]),
      secret: z.string().max(64, "Secret too long").optional(),
      is_active: z.boolean().optional(),
    })
    .strict(),

  webhookUpdate: z
    .object({
      url: z
        .string()
        .url("Invalid URL format")
        .max(512, "URL too long")
        .optional(),
      name: z.string().max(120, "Name too long").optional(),
      events: z
        .array(z.string().min(1, "Event name cannot be empty"))
        .optional(),
      is_active: z.boolean().optional(),
      reset_circuit: z.boolean().optional(),
    })
    .strict(),

  swarmCreate: z.object({
    name: z.string().min(1, "Name is required").max(255, "Name too long"),
    description: z.string().max(1000, "Description too long").optional(),
    agent_ids: z
      .array(z.string().uuid("Invalid agent ID"))
      .min(1, "At least one agent is required")
      .max(20, "Too many agents"),
    min_replicas: z.number().int().min(1).max(10).optional(),
    max_replicas: z.number().int().min(1).max(50).optional(),
  }),

  swarmScale: z.object({
    replicas: z.number().int().min(1).max(50),
  }),

  alertResolve: z.object({
    resolved: z.boolean(),
  }),

  // Newsletter schema
  newsletter: z.object({
    email: z.string().email("Invalid email format"),
    locale: localeSchema,
  }),

  // Generic ID parameter
  idParam: z.object({
    id: z.string().uuid("Invalid ID format"),
  }),
};

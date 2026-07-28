# Multi-stage build for MUTX Next.js application
FROM node:24-alpine3.23@sha256:595398b0081eacda8e1c4c5b97b76cd1020e4d58a8ebcb4843b9bca1e79e7436 AS base

# Keep the container package manager aligned with packageManager and CI.
RUN npm install -g npm@11.12.1

# Dependencies stage
FROM base AS deps
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

# Builder stage
FROM base AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN rm -rf public/_next

# Build the Next.js app
RUN npm run build

# Runner stage
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]

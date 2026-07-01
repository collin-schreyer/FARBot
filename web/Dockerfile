# Multi-stage build for a slim Next.js standalone image (App Runner listens on 8080).
FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8080
ENV HOSTNAME=0.0.0.0
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 8080
# Force bind to all interfaces — the container runtime auto-sets HOSTNAME to the
# container's name, which Next.js standalone would otherwise bind to.
CMD ["sh", "-c", "HOSTNAME=0.0.0.0 node server.js"]

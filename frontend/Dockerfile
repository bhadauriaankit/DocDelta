# syntax=docker/dockerfile:1

# ---- deps: install once, reused by dev and builder ----
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- dev: used by docker-compose for local development ----
# Runs `next dev` against a bind-mounted source directory so edits on the
# host are picked up immediately (see docker-compose.yml for the volumes).
FROM deps AS dev
WORKDIR /app
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ---- builder: production build ----
FROM deps AS builder
WORKDIR /app
COPY . .
# NEXT_PUBLIC_* vars must be present at build time — they get baked into
# the client bundle, not read at runtime like server-side env vars.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# ---- prod: minimal runtime image using Next's standalone output ----
FROM node:20-slim AS prod
WORKDIR /app
ENV NODE_ENV=production

RUN groupadd --system app && useradd --system --gid app app

# .next/standalone already contains a trimmed node_modules + server.js —
# no `npm install` needed in this final stage at all.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

USER app
EXPOSE 3000
CMD ["node", "server.js"]

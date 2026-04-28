FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
ENV NEXT_PRIVATE_LOCAL_WEBPACK=true
ARG NEXT_PUBLIC_EVENT_SVC_URL
ARG NEXT_PUBLIC_AI_SVC_URL
ENV NEXT_PUBLIC_EVENT_SVC_URL=$NEXT_PUBLIC_EVENT_SVC_URL
ENV NEXT_PUBLIC_AI_SVC_URL=$NEXT_PUBLIC_AI_SVC_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3001
ENV PORT 3001
CMD ["node", "server.js"]

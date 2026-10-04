FROM node:24-bookworm-slim AS dev

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./

RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 3000

CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "3000"]

# For demonstrations (compose.demo.yaml): the production build, so no Nuxt DevTools and no page compiled on
# its first visit. Nuxt's output carries its own server and dependencies.
FROM dev AS demo-build

RUN pnpm build

FROM node:24-bookworm-slim AS demo

WORKDIR /app

COPY --from=demo-build /app/.output ./.output

EXPOSE 3000

CMD ["node", ".output/server/index.mjs"]

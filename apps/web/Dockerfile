# REWIND investigator UI: built once, served as static files by nginx, which also
# proxies /api to the API so the browser talks to one origin, as the dev server does.

FROM node:22-alpine AS build
WORKDIR /web
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80

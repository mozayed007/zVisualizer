FROM oven/bun:1.3.12 AS build

WORKDIR /app

COPY apps/frontend/package.json /app/package.json
COPY apps/frontend/bun.lock /app/bun.lock
RUN bun install --frozen-lockfile

COPY apps/frontend /app

ARG VITE_API_BASE_URL=
ARG VITE_CHAT_API_KEY=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_CHAT_API_KEY=${VITE_CHAT_API_KEY}

RUN bun run build

FROM nginx:1.27-alpine AS runtime

COPY docker/nginx/frontend.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

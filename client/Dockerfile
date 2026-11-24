# The dashboard's production build, served by Caddy. Built from the repository
# root so it can share deploy/healthcheck.sh.

FROM node:22-alpine AS build
WORKDIR /client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

FROM caddy:2.11.9-alpine
COPY client/Caddyfile /etc/caddy/Caddyfile
COPY deploy/healthcheck.sh /usr/local/bin/healthcheck
COPY --from=build /client/dist /srv

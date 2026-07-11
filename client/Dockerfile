# Multi-stage: build the Vite app, then serve the static bundle with nginx.
# nginx also reverse-proxies /api to the gateway so the client and API are
# same-origin in production (session cookie + OAuth redirects just work).

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

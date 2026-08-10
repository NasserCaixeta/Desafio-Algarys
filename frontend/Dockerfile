FROM node:22-alpine AS builder

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
ARG VITE_API_URL=
ARG VITE_API_TIMEOUT_MS=10000
ARG VITE_POLL_INTERVAL_MS=2000
ENV VITE_API_URL=$VITE_API_URL \
    VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS \
    VITE_POLL_INTERVAL_MS=$VITE_POLL_INTERVAL_MS
RUN npm run build


FROM nginx:1.28-alpine AS runtime

COPY frontend/nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /app/dist /usr/share/nginx/html

RUN chown -R nginx:nginx /usr/share/nginx/html
USER nginx
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8080/nginx-health >/dev/null || exit 1

ENTRYPOINT ["nginx", "-g", "daemon off;"]

FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS frontend
ARG VITE_PRIMEUI_LICENSE_KEY
ENV VITE_PRIMEUI_LICENSE_KEY=$VITE_PRIMEUI_LICENSE_KEY
WORKDIR /src/frontend
RUN npm install -g pnpm@11.19.0
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2
WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY requirements-runtime.lock ./
COPY backend ./backend
COPY scripts/artifact_smoke.py ./scripts/artifact_smoke.py
COPY libs/portable-webtoolbox-embedded-v0.7.0/webtoolbox-embedded ./libs/webtoolbox
COPY --from=frontend /src/frontend/dist ./frontend/dist
RUN pip install --no-cache-dir --require-hashes -r requirements-runtime.lock && pip install --no-deps --no-build-isolation . './libs/webtoolbox'
RUN useradd --system --uid 10001 --create-home tracker && mkdir -p /data && chown tracker /data
USER tracker
ENV APP_HOST=0.0.0.0 APP_PORT=8000 APP_DATA_DIR=/data APP_ALLOW_REMOTE_HUMAN=false
VOLUME ["/data"]
EXPOSE 8000
CMD ["application-tracker"]

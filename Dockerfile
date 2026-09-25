FROM node:24-alpine AS frontend
WORKDIR /src/frontend
RUN npm install -g pnpm@11.19.0
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY backend ./backend
COPY --from=frontend /src/frontend/dist ./frontend/dist
RUN pip install --no-cache-dir .
ENV APP_HOST=0.0.0.0 APP_PORT=8000 APP_DATA_DIR=/data APP_ALLOW_REMOTE_HUMAN=true
VOLUME ["/data"]
EXPOSE 8000
CMD ["application-tracker"]

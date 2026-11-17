# One Render Web Service: build React once, serve through the same FastAPI origin.
FROM node:22-alpine AS frontend-build
WORKDIR /src
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Render Docker deployments supply service environment variables as Docker build args.
# These are intentionally PUBLIC Supabase client settings, never a server secret.
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
RUN test -n "$VITE_SUPABASE_URL" && test -n "$VITE_SUPABASE_PUBLISHABLE_KEY" && npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv/backend
WORKDIR /srv
COPY backend/requirements.txt /srv/backend/requirements.txt
RUN python -m pip install --no-cache-dir -r /srv/backend/requirements.txt
COPY backend/ /srv/backend/
COPY --from=frontend-build /src/dist/ /srv/frontend_dist/
COPY serve.py /srv/serve.py
# Render's public router forwards to $PORT; FastAPI must listen on all interfaces.
CMD ["sh", "-c", "exec uvicorn serve:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]

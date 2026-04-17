# Deployment Information

**Student:** Huynh Khai Huy — 2A202600082  
**Date:** 17/04/2026

---

## Public URL

```
https://agent-production-6cf7.up.railway.app
```

## Platform

**Railway** — Docker build, Redis add-on (internal network)

- Project: `huyhuynh-production-agent`
- Service: `agent`
- Region: Railway auto-assigned
- Build time: ~50s
- Redis: `redis.railway.internal:6379`

---

## Test Commands

### Health Check (liveness probe)

```bash
curl https://agent-production-6cf7.up.railway.app/health
```

Expected response:
```json
{"status": "ok", "instance": "instance-2db640", "uptime_seconds": 588.2}
```

### Readiness Check

```bash
curl https://agent-production-6cf7.up.railway.app/ready
```

Expected response:
```json
{"status": "ready", "instance": "instance-2db640"}
```

### Authentication Required (no key → 422)

```bash
curl -X POST https://agent-production-6cf7.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

Expected: `422 Unprocessable Entity` (FastAPI enforces required `X-API-Key` header at validation layer)

### API Test (with authentication → 200)

```bash
curl -X POST https://agent-production-6cf7.up.railway.app/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Docker?", "session_id": "test-1"}'
```

Expected response:
```json
{
  "answer": "Container là cách đóng gói app để chạy ở nơi. Build once, run anywhere!",
  "session_id": "test-1",
  "served_by": "instance-2db640"
}
```

### Rate Limiting Test (11th request → 429)

```bash
for i in $(seq 1 11); do
  curl -s -X POST https://agent-production-6cf7.up.railway.app/ask \
    -H "X-API-Key: dev-key-change-me" \
    -H "Content-Type: application/json" \
    -d '{"question": "test", "session_id": "rate-test"}' \
    -w " [HTTP %{http_code}]\n" -o /dev/null
done
# First 10: HTTP 200
# Request 11+: HTTP 429
```

---

## Environment Variables Set on Railway

| Variable | Value | Notes |
|----------|-------|-------|
| `ENVIRONMENT` | `staging` | Skips production key validation |
| `AGENT_API_KEY` | `dev-key-change-me` | Auth key for all requests |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | Railway reference var → internal Redis |
| `PORT` | (injected by Railway) | Dynamic port via `sh -c '... --port ${PORT:-8000}'` |
| `LOG_LEVEL` | `INFO` | Structured JSON logs |

---

## CI/CD

**Repository:** https://github.com/huyhuynh12hhk/huy-production-agent  
**Workflow:** `.github/workflows/deploy-railway.yml`  
**Trigger:** Push to `main` branch  
**Secret required:** `RAILWAY_TOKEN` (project-scoped token from Railway dashboard)

Auto-deploy runs `railway up --service agent --detach` on every push.

---

## Production Readiness Score

```
20/20 checks passed (100%) — verified by 06-lab-complete/check_production_ready.py
```

| Check | Status |
|-------|--------|
| Dockerfile exists | ✅ |
| docker-compose.yml exists | ✅ |
| .dockerignore exists | ✅ |
| .env.example exists | ✅ |
| requirements.txt exists | ✅ |
| railway.toml exists | ✅ |
| .env in .gitignore | ✅ |
| No hardcoded secrets in code | ✅ |
| /health endpoint | ✅ |
| /ready endpoint | ✅ |
| Authentication implemented | ✅ |
| Rate limiting implemented | ✅ |
| Graceful shutdown (SIGTERM) | ✅ |
| Structured logging (JSON) | ✅ |
| Multi-stage Docker build | ✅ |
| Non-root user in container | ✅ |
| HEALTHCHECK instruction | ✅ |
| Slim base image | ✅ |
| .dockerignore covers .env | ✅ |
| .dockerignore covers __pycache__ | ✅ |

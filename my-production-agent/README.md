# my-production-agent

A production-ready AI agent built for the Day 12 lab (Part 6 Final Project).

## Features

- API Key authentication (`X-API-Key` header)
- Redis-backed sliding-window rate limiting (10 req/min per user)
- Redis-backed monthly cost guard ($10/month per user)
- Conversation history persisted in Redis (stateless design)
- `/health` liveness probe and `/ready` readiness probe
- Graceful SIGTERM shutdown
- Structured JSON logging
- Multi-stage Docker build (non-root user)
- Nginx load balancer across 3 agent instances

## Quick start (local)

```bash
# 1. Copy env file and set your API key
cp .env.example .env.local

# 2. Start full stack (3 agents + Redis + Nginx)
docker compose up --scale agent=3

# 3. Health check
curl http://localhost/health

# 4. Ask a question
curl http://localhost/ask -X POST \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Docker?"}'
```

## Running without Docker

```bash
pip install -r requirements.txt
# Start Redis separately, then:
REDIS_URL=redis://localhost:6379/0 AGENT_API_KEY=secret uvicorn app.main:app --reload
```

## Deploy to Railway

```bash
railway init
railway variables set AGENT_API_KEY=<your-secret>
railway variables set REDIS_URL=<your-redis-url>
railway up
```

# Day 12 Lab — Mission Answers

**Student Name:** Huynh Khai Huy  
**Student ID:** 2A202600082  
**Date:** 17/04/2026

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

1. **Hardcoded API key** — `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL` chứa credentials plaintext. Nếu push lên GitHub, key bị lộ ngay lập tức và tài khoản có thể bị hack/tính phí.

2. **Debug mode bật trong production** — `DEBUG = True` làm lộ stack trace chi tiết cho client khi có lỗi, cung cấp thông tin nhạy cảm cho kẻ tấn công.

3. **Log bí mật ra console** — `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` in ra API key trong log. Log file thường được lưu trữ hoặc gửi đến các hệ thống log tập trung, làm lộ secret.

4. **Không có health check endpoint** — Khi agent crash, container orchestrator (Kubernetes, Railway, Render...) không biết để restart. App có thể chết mà không ai hay.

5. **Port cứng và bind sai địa chỉ** — `host="localhost"` nghĩa là container chỉ lắng nghe bên trong (loopback), không thể nhận traffic từ bên ngoài. `port=8000` hardcode thay vì đọc từ `PORT` env var (Railway/Render inject tự động).

6. **Không có graceful shutdown** — App bị kill đột ngột mà không hoàn thành các request đang xử lý, gây mất dữ liệu.

7. **Không có input validation** — `question: str` không kiểm tra độ dài, ký tự đặc biệt... có thể bị khai thác.

---

### Exercise 1.3: Comparison table

| Feature | Develop (`basic`) | Production (`advanced`) | Tại sao quan trọng? |
|---------|-------------------|-------------------------|----------------------|
| **Config** | Hardcode trong code | `os.getenv()` + `config.py` (12-Factor) | Không lộ secret, dễ thay đổi per environment |
| **API Key** | `sk-hardcoded-fake-key` | Đọc từ `AGENT_API_KEY` env var | Tránh bị lộ khi push code lên GitHub |
| **Logging** | `print()` raw text | Structured JSON logging (`logging` module) | Dễ parse bởi log aggregator (Datadog, Loki) |
| **Health check** | Không có | `GET /health` + `GET /ready` | Platform cần để biết khi nào restart/route traffic |
| **Graceful shutdown** | Đột ngột (`Ctrl+C`) | `lifespan` async context + signal handler | Hoàn thành requests hiện tại trước khi tắt |
| **Host binding** | `localhost` | `0.0.0.0` | Container phải nhận traffic từ bên ngoài |
| **Port** | Cứng `8000` | `int(os.getenv("PORT", 8000))` | Railway/Render inject `PORT` khác nhau |
| **CORS** | Không cấu hình | `CORSMiddleware` với origins từ env | Bảo mật browser requests |
| **Debug reload** | `reload=True` | `reload=settings.debug` | Không hot-reload trong production |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile cơ bản (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` — full Python distribution (~1 GB, bao gồm mọi thứ)
2. **Working directory:** `/app`
3. **Tại sao COPY requirements.txt trước?** Docker builds theo từng layer và cache chúng. Nếu `requirements.txt` không đổi, layer cài dependencies được cache → build nhanh hơn nhiều. Nếu copy toàn bộ code trước, mỗi lần thay code (dù chỉ 1 dòng) đều phải cài lại toàn bộ dependencies.
4. **CMD vs ENTRYPOINT:**
   - `CMD` — default command, có thể bị override khi `docker run image other-command`
   - `ENTRYPOINT` — command cố định, không bị override dễ dàng; thường dùng khi container chỉ có một mục đích duy nhất (ví dụ `ENTRYPOINT ["python", "app.py"]`)

---

### Exercise 2.3: Multi-stage build (`02-docker/production/Dockerfile`)

| Stage | Mục đích |
|-------|----------|
| **Stage 1 (builder)** | Cài đặt dependencies dùng `pip install --user`. Có `gcc`, `libpq-dev` và các build tools để compile native packages |
| **Stage 2 (runtime)** | Chỉ copy `/root/.local` (packages) từ builder + source code. Không có compiler, không có build tools → image nhỏ hơn nhiều |

**Image size comparison (ước tính):**
- Develop (`python:3.11` full): ~**1.0–1.2 GB**
- Production (`python:3.11-slim` + multi-stage): ~**200–300 MB**
- Difference: khoảng **~70–80% nhỏ hơn**

**Tại sao image nhỏ hơn?** Stage 2 chỉ dùng `python:3.11-slim` (không có apt packages thừa), không copy build tools (gcc, pip cache, apt lists). Kết quả: attack surface nhỏ hơn, deploy nhanh hơn, cold start nhanh hơn.

---

### Exercise 2.4: Docker Compose Architecture

```
Internet
    │
    ▼
 Nginx :80 (reverse proxy / load balancer)
    │
    ├──────────────┐
    ▼              ▼
agent_1:8000   agent_2:8000  (có thể scale thêm với --scale agent=N)
    │              │
    └──────┬───────┘
           ▼
      Redis :6379 (session cache, rate limit counters)
           │
      Qdrant :6333 (vector DB, RAG) [optional]
```

**Services được start:** `agent`, `redis`, `nginx` (và `qdrant` nếu có trong compose file).

**Cách communicate:** Nginx nhận HTTP request từ bên ngoài, forward tới `agent` service (round-robin). Agent kết nối Redis và Qdrant qua internal Docker network (tên service = hostname). Không service nào expose port trực tiếp ngoài Nginx.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

**Các bước thực hiện:**
```bash
npm i -g @railway/cli
railway login
cd 03-cloud-deployment/railway
railway init
railway variables set PORT=8000
railway variables set AGENT_API_KEY=my-secret-key-$(openssl rand -hex 8)
railway up
```

**Platform URL:** Được cấu hình trong `DEPLOYMENT.md` (xem file đó).

---

### Exercise 3.2: So sánh `render.yaml` vs `railway.toml`

| Thuộc tính | `railway.toml` | `render.yaml` |
|------------|----------------|---------------|
| Format | TOML | YAML |
| Builder | `builder = "DOCKERFILE"` | `runtime: docker` |
| Start command | `startCommand = "uvicorn ..."` | Không cần (dùng CMD trong Dockerfile) |
| Health check | `healthcheckPath = "/health"` | `healthCheckPath: /health` |
| Region | Không cấu hình (Railway tự chọn) | `region: singapore` |
| Env vars | Set qua CLI hoặc dashboard | Khai báo trực tiếp trong file (sync: false cho secrets) |
| Auto deploy | Mặc định bật | `autoDeploy: true` |

---

## Part 4: API Security

### Exercise 4.1: API Key authentication

- **API key được check ở đâu?** Trong dependency function `verify_api_key()` — được inject vào mỗi protected endpoint qua `Depends(verify_api_key)`. FastAPI tự động gọi dependency trước khi route handler chạy.
- **Điều gì xảy ra nếu sai key?** `HTTPException(status_code=401)` được raise, FastAPI trả về response `{"detail": "Invalid API key"}` mà không chạy route handler.
- **Làm sao rotate key?** Thay đổi env var `AGENT_API_KEY` và restart service. Zero-downtime rotation: hỗ trợ cả old key và new key trong một khoảng thời gian (dùng list thay vì single string), sau đó xóa old key.

**Test output:**
```bash
# Không có key → 401
curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Có key → 200
curl -X POST http://localhost:8000/ask -H "X-API-Key: demo-key-change-in-production" \
  -H "Content-Type: application/json" -d '{"question": "Hello"}'
# {"question":"Hello","answer":"..."}
```

---

### Exercise 4.2: JWT Flow

1. Client gọi `POST /auth/token` với username + password → server trả về JWT signed bằng `JWT_SECRET`
2. JWT chứa: `sub` (user id), `role`, `iat` (issued at), `exp` (expiry) — tất cả được encode + sign, KHÔNG encrypt
3. Client gửi token trong header: `Authorization: Bearer <token>`
4. Server decode token, verify signature bằng `JWT_SECRET` — nếu valid → extract user info → tiếp tục xử lý
5. Không cần query database mỗi request (stateless) → nhanh hơn

---

### Exercise 4.3: Rate Limiting

- **Algorithm:** Sliding Window Counter — mỗi user có một `deque` chứa timestamps của các request trong 60 giây qua. Timestamps cũ bị loại bỏ liên tục.
- **Limit:** 10 requests/minute (configurable qua `RATE_LIMIT_PER_MINUTE` env var)
- **Bypass cho admin:** Có thể implement bằng cách skip rate limit check nếu `role == "admin"` trong JWT payload

**Test output khi hit limit:**
```json
{
  "detail": {
    "error": "Rate limit exceeded",
    "limit": 10,
    "window_seconds": 60,
    "retry_after_seconds": 45
  }
}
```
HTTP status: `429 Too Many Requests` với header `Retry-After: 45`

---

### Exercise 4.4: Cost Guard implementation

```python
import redis
from datetime import datetime

r = redis.Redis()

def check_budget(user_id: str, estimated_cost: float) -> bool:
    """
    Return True nếu còn budget, False nếu vượt.
    
    Logic:
    - Mỗi user có budget $10/tháng
    - Track spending trong Redis
    - Reset đầu tháng
    """
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"
    
    current = float(r.get(key) or 0)
    if current + estimated_cost > 10:
        return False
    
    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)  # 32 days TTL → auto-reset sau ~1 tháng
    return True
```

**Giải thích:** Key pattern `budget:{user_id}:{YYYY-MM}` tự động tạo key mới mỗi tháng → spending reset. `INCRBYFLOAT` là atomic operation trong Redis, an toàn khi có nhiều instances gọi đồng thời. TTL 32 ngày đảm bảo key cũ được dọn dẹp.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

```python
@app.get("/health")
def health():
    """Liveness probe — container còn sống không?"""
    return {"status": "ok", "uptime": round(time.time() - START_TIME, 1)}

@app.get("/ready")
def ready():
    """Readiness probe — sẵn sàng nhận traffic không?"""
    if not _is_ready:
        return JSONResponse(status_code=503, content={"status": "not ready"})
    return {"ready": True}
```

- `/health` (liveness): container process còn alive. Platform restart container nếu fail.
- `/ready` (readiness): app đã khởi động xong và sẵn sàng nhận traffic. Load balancer dừng route request đến đây nếu fail (thay vì restart).

---

### Exercise 5.2: Graceful shutdown

```python
import signal
import sys

def shutdown_handler(signum, frame):
    """Handle SIGTERM from container orchestrator (Kubernetes, Docker, Railway...)"""
    logger.info("Received SIGTERM — finishing in-flight requests...")
    _is_ready = False      # 1. Stop accepting new requests (readiness probe fails)
    time.sleep(2)          # 2. Cho requests hiện tại ~2s để hoàn thành
    # 3. Close connections (DB, Redis, etc.) — uvicorn lifespan shutdown handles this
    logger.info("Graceful shutdown complete")
    sys.exit(0)            # 4. Exit cleanly

signal.signal(signal.SIGTERM, shutdown_handler)
```

Uvicorn hỗ trợ `--timeout-graceful-shutdown 30` để tự động đợi in-flight requests trước khi tắt.

---

### Exercise 5.3: Stateless Design

**Vấn đề với in-memory state:**
- Instance A xử lý request đầu tiên → lưu `conversation_history["user1"]` vào memory của A
- Instance B nhận request tiếp theo của cùng user → không có history → trả lời sai context

**Giải pháp (Redis):**
```python
import redis
r = redis.from_url(os.getenv("REDIS_URL"))

@app.post("/ask")
def ask(user_id: str, question: str):
    # Lấy history từ Redis — shared across ALL instances
    raw = r.lrange(f"history:{user_id}", 0, 9)   # last 10 turns
    history = [h.decode() for h in raw]
    
    # ... gọi LLM với history ...
    
    # Lưu vào Redis
    r.lpush(f"history:{user_id}", question)
    r.expire(f"history:{user_id}", 3600)          # TTL 1 giờ
```

Bất kỳ instance nào nhận request cũng đọc/ghi cùng Redis → conversation liên tục dù bị route sang instance khác.

---

### Exercise 5.4: Load Balancing

```bash
docker compose up --scale agent=3
```

Nginx config (`upstream agent`) dùng round-robin: request 1 → agent_1, request 2 → agent_2, request 3 → agent_3, request 4 → agent_1...

Nếu một instance die, Nginx health check phát hiện và tự động loại khỏi pool → zero downtime.

**Test log output** cho thấy requests được phân tán đều giữa 3 instances (mỗi instance log `"event": "request"` độc lập).

---

### Exercise 5.5: Stateless test

```bash
python test_stateless.py
```

Script gửi request đến API để tạo conversation, kill một instance ngẫu nhiên, gửi follow-up request → conversation vẫn còn vì state nằm trong Redis, không phải trong instance memory.

---

## Part 6: Final Project

### Deployed Production Agent

**Repository:** https://github.com/huyhuynh12hhk/huy-production-agent  
**Live URL:** https://agent-production-6cf7.up.railway.app  
**Platform:** Railway (Docker build, Redis add-on)

### Architecture

| Component | File | Feature |
|-----------|------|---------|
| Config | `app/config.py` | 12-Factor, tất cả từ env vars, validate production secrets |
| Auth | `app/auth.py` | API Key (`X-API-Key` header), user_id derivation via SHA-256 |
| Rate Limiter | `app/rate_limiter.py` | Sliding window 10 req/min, Redis-backed, returns `Retry-After` |
| Cost Guard | `app/cost_guard.py` | Per-user $10/month budget, Redis atomic `INCRBYFLOAT`, monthly TTL |
| Main App | `app/main.py` | Health/Ready probes, graceful SIGTERM, structured JSON logging |
| Container | `app/Dockerfile` | Multi-stage build (builder + runtime), non-root `agent` user |
| Stack | `docker-compose.yml` | Agent + Redis + Nginx (3 instances, load balanced) |
| Deploy | `railway.toml` | `sh -c` wrapper for `$PORT` expansion, healthcheckPath `/health` |
| CI/CD | `.github/workflows/deploy-railway.yml` | Auto-deploy on push to `main` via `RAILWAY_TOKEN` secret |

### Production Readiness Check

```
Result: 20/20 checks passed (100%)
🎉 PRODUCTION READY!
```

### Live Test Results (17/04/2026)

```bash
# Health check
GET https://agent-production-6cf7.up.railway.app/health
→ {"status":"ok","instance":"instance-2db640","uptime_seconds":588.2}

# Auth required — missing key → 422 Unprocessable Entity
# (FastAPI validates required Header(...) before route handler)
POST /ask  [no X-API-Key]
→ 422

# Valid request
POST /ask  X-API-Key: dev-key-change-me
Body: {"question": "What is Docker?", "session_id": "demo-1"}
→ {"answer":"Container là cách đóng gói app để chạy ở nơi. Build once, run anywhere!",
   "session_id":"demo-1","served_by":"instance-2db640"}
```

### Deployment Steps

```bash
# 1. Railway project + Redis
railway login
railway init
railway add --service agent
railway add --database redis

# 2. Set environment variables
railway variables set ENVIRONMENT=staging
railway variables set AGENT_API_KEY=dev-key-change-me
railway variables set "REDIS_URL=\${{Redis.REDIS_URL}}"

# 3. Deploy
railway up --detach

# 4. Get public URL
railway domain
```

### Key Fix — $PORT expansion

Railway injects `PORT` as an env var but Docker's exec form doesn't expand shell variables.  
**Fix in `railway.toml`:**
```toml
startCommand = "sh -c 'uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2'"
```
Without `sh -c`, uvicorn receives the literal string `"$PORT"` and fails with:
`Error: Invalid value for '--port': '$PORT' is not a valid integer.`

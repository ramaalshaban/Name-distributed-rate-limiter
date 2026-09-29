import os
import time
import uuid
import redis
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    redis_host: str = "localhost"
    redis_port: int = 6379
    window_seconds : int = 10
    max_requests: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()



app = FastAPI(title="Distributed Rate Limiter Proxy")

REDIS_HOST = settings.redis_host
REDIS_PORT = settings.redis_port

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

with open("rate_limiter.lua", "r") as f:
    lua_script_content = f.read()
rate_limit_script = r.register_script(lua_script_content)

WINDOW_SECONDS = settings.window_seconds
MAX_REQUESTS = 100
MAX_DAY_LIMIT = 15

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    api_key = request.headers.get("X-API-Key", request.client.host)
    redis_key = f"rate_limit:{api_key}"
    redis_sec_key =  f"daily_limit:{api_key}"

    
    now = time.time()
    req_id = str(uuid.uuid4())
    
    allowed, current_count , current_daily_count, limit_type= rate_limit_script(
        keys=[redis_key,redis_sec_key],
        args=[now, WINDOW_SECONDS, MAX_REQUESTS,MAX_DAY_LIMIT, req_id]
    )
    
    if not allowed:
        if limit_type == "daily":
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "Daily quota exceeded"},
                headers={
                    "Retry-After": "86400",
                    "X-RateLimit-Limit": str(MAX_DAY_LIMIT),
                    "X-RateLimit-Remaining": "0"
                }
            )
        return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "Too Many Requests"},
                headers={
                    "Retry-After": str(WINDOW_SECONDS),
                    "X-RateLimit-Limit": str(MAX_REQUESTS),
                    "X-RateLimit-Remaining": "0"
                }
            )
    
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(MAX_REQUESTS)
    response.headers["X-RateLimit-Remaining"] = str(MAX_REQUESTS - current_count)
    return response

@app.get("/api/v1/data")
async def get_data():
    return {"status": "success", "message": "Here is your protected data!"}

@app.get("/")
async def root():
    instance_name = os.getenv("APP_INSTANCE", "unknown")
    return {"message": "Hello World", "handled_by": instance_name}
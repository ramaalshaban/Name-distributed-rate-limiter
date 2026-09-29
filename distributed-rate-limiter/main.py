import os
import time
import uuid
import redis
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings, SettingsConfigDict


import json

with open("tiers.json", "r", encoding="utf-8") as file:
    tiers_config = json.load(file)


class Settings(BaseSettings):
    redis_host: str = "localhost"
    redis_port: int = 6379


    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()



app = FastAPI(title="Distributed Rate Limiter Proxy")

REDIS_HOST = settings.redis_host
REDIS_PORT = settings.redis_port

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

with open("rate_limiter.lua", "r") as f:
    lua_script_content = f.read()
rate_limit_script = r.register_script(lua_script_content)





@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    api_key = request.headers.get("X-API-Key", request.client.host)
    tier_name = tiers_config["api_keys"].get(api_key, "free")
    tier = tiers_config["tiers"][tier_name]
    redis_key = f"rate_limit:{api_key}"
    redis_sec_key =  f"daily_limit:{api_key}"

    
    now = time.time()
    req_id = str(uuid.uuid4())
    
    allowed, current_count , current_daily_count, limit_type= rate_limit_script(
        keys=[redis_key,redis_sec_key],
        args=[now, tier["window_seconds"],  tier["max_requests"],tier["max_day_limit"], req_id]
    )
    
    if not allowed:
        if limit_type == "daily":
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "Daily quota exceeded"},
                headers={
                    "Retry-After": "86400",
                    "X-RateLimit-Limit": str(tier["max_day_limit"]),
                    "X-RateLimit-Remaining": "0"
                }
            )
        return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "Too Many Requests"},
                headers={
                    "Retry-After": str(tier["window_seconds"]),
                    "X-RateLimit-Limit": str(tier["max_requests"]),
                    "X-RateLimit-Remaining": "0"
                }
            )
    
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str( tier["max_requests"])
    response.headers["X-RateLimit-Remaining"] = str( tier["max_requests"] - current_count)
    response.headers["X-DailyLimit"] = str(tier["max_day_limit"])
    response.headers["X-DailyRemaining"] = str(tier["max_day_limit"] - current_daily_count)
    return response

@app.get("/api/v1/data")
async def get_data():
    return {"status": "success", "message": "Here is your protected data!"}


local rate_key = KEYS[1]
local quota_key = KEYS[2]

local now = tonumber(ARGV[1]) 
local window = tonumber(ARGV[2]) 
local max_limit = tonumber(ARGV[3]) 
local max_day_limit = tonumber(ARGV[4])
local request_id = ARGV[5] 

local clear_before = now - window 
local day_start = now - (now % 86400)


redis.call('ZREMRANGEBYSCORE', rate_key, 0, clear_before)
redis.call('ZREMRANGEBYSCORE', quota_key, '-inf', day_start - 1)


local current_requests = redis.call('ZCARD', rate_key) 

local current_daily_requests = redis.call('ZCARD',quota_key)

if not max_limit or not max_day_limit then
    return redis.error_reply("Missing or invalid arguments. Both must be numbers.")
end

if current_daily_requests>= max_day_limit then
    return {0, current_requests, current_daily_requests, "daily"}
end

if current_requests >= max_limit then
    return {0, current_requests, current_daily_requests, "rate"}
end


redis.call('ZADD',quota_key, now, request_id)
redis.call('EXPIRE', quota_key, 86400)

redis.call('ZADD',rate_key, now, request_id)
redis.call('EXPIRE', rate_key, math.ceil(window))

return {1, current_requests + 1, current_daily_requests + 1, "ok"}

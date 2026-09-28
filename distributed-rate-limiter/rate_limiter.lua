local key = KEYS[1]
local now = tonumber(ARGV[1]) 
local window = tonumber(ARGV[2]) 
local max_limit = tonumber(ARGV[3]) 
local request_id = ARGV[4] 

local clear_before = now - window 

redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)

local current_requests = redis.call('ZCARD', key) 

if current_requests >= max_limit then
    return {0, current_requests}
else
    redis.call('ZADD',key, now, request_id)
    redis.call('EXPIRE', key, math.ceil(window))
    return {1, current_requests + 1}
end
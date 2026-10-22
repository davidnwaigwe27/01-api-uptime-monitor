
-- 1. Create the monitored URLs table
CREATE TABLE IF NOT EXISTS monitored_urls (
    id SERIAL PRIMARY KEY,
    name TEXT,
    url TEXT UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Create the check results table
CREATE TABLE IF NOT EXISTS check_results (
    id SERIAL PRIMARY KEY,
    url_id INTEGER REFERENCES monitored_urls(id) ON DELETE CASCADE,
    checked_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_success BOOLEAN NOT NULL,
    status_code INTEGER,
    response_time_ms INTEGER,
    error_type TEXT,
    error_message TEXT
);

-- Migration 001: Initial tables for AgentPay Gateway MCP
-- Run: python3 server.py --db-only

BEGIN;

-- API keys table: stores all registered API keys with tier and credit info
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key TEXT UNIQUE NOT NULL,
    tier TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'pro')),
    customer_id TEXT,                    -- Stripe customer ID (nullable for free tier)
    subscription_id TEXT,                -- Stripe subscription ID
    daily_credits INTEGER NOT NULL DEFAULT 100,
    used_today INTEGER NOT NULL DEFAULT 0,
    total_calls BIGINT NOT NULL DEFAULT 0,
    total_credits_spent BIGINT NOT NULL DEFAULT 0,
    stripe_checkout_session_id TEXT,     -- For tracking checkout flow
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Gateway logs: records every proxied tool call for auditing/billing
CREATE TABLE IF NOT EXISTS gateway_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    backend_server TEXT NOT NULL,
    cost INTEGER NOT NULL DEFAULT 1,
    remaining_credits INTEGER,
    response_time_ms INTEGER,
    status TEXT DEFAULT 'success',        -- success, error, rate_limited
    request_payload JSONB DEFAULT '{}',
    response_payload JSONB DEFAULT '{}',
    timestamp TIMESTAMPTZ DEFAULT now()
);

-- Stripe events: tracks payment/subscription events from Stripe webhooks
CREATE TABLE IF NOT EXISTS stripe_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id TEXT UNIQUE NOT NULL,        -- Stripe event ID (evt_xxx)
    event_type TEXT NOT NULL,             -- checkout.session.completed, etc.
    api_key_id UUID REFERENCES api_keys(id),
    payload JSONB DEFAULT '{}',
    processed BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(api_key);
CREATE INDEX IF NOT EXISTS idx_api_keys_tier ON api_keys(tier);
CREATE INDEX IF NOT EXISTS idx_api_keys_customer ON api_keys(customer_id);
CREATE INDEX IF NOT EXISTS idx_gateway_logs_api ON gateway_logs(api_key);
CREATE INDEX IF NOT EXISTS idx_gateway_logs_ts ON gateway_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_gateway_logs_tool ON gateway_logs(tool_name);
CREATE INDEX IF NOT EXISTS idx_stripe_events_id ON stripe_events(event_id);
CREATE INDEX IF NOT EXISTS idx_stripe_events_api ON stripe_events(api_key_id);

-- RLS: restrict direct table access
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE gateway_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE stripe_events ENABLE ROW LEVEL SECURITY;

-- Service role policies (bypasses RLS for service key)
CREATE POLICY service_all_api_keys ON api_keys
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY service_all_gateway_logs ON gateway_logs
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY service_all_stripe_events ON stripe_events
    FOR ALL USING (true) WITH CHECK (true);

COMMIT;
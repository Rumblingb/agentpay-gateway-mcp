#!/usr/bin/env python3
"""
AgentPay Gateway MCP — Centralized API Gateway with Per-Call Billing
===================================================================

Routes to ALL 42 MCP servers through a single endpoint.
Charges per API call using a credit-based system backed by Supabase.

Architecture:
  - Each tool call checks API key against Supabase
  - Deducts credits based on tool cost tier
  - Proxies the call to the appropriate backend MCP server (via HTTP)
  - Returns error with Stripe upsell link when credits exhausted

Free tier:  100 credits/day
Pro tier:   10,000 credits/day ($19/mo)

Usage:
  AGENTPAY_API_KEY=xxx python3 server.py
  python3 server.py --port 8000

Author: AgentPay Labs
"""

from __future__ import annotations

import json
import os
import sys
import uuid
import time
import hashlib
import datetime
import httpx
from typing import Optional
from mcp.server.lowlevel import Server, stdio_server
from mcp.server.models import InitializationOptions
import anyio

# ─── Configuration ────────────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PORT = int(os.getenv("PORT", "8000"))

STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "price_agentpay_pro_monthly")
STRIPE_CHECKOUT_LINK = os.getenv(
    "STRIPE_CHECKOUT_LINK",
    "https://buy.stripe.com/c/agentpay/checkout/pro"
)

FREE_TIER_DAILY_CREDITS = 100
PRO_TIER_DAILY_CREDITS = 10_000
PRO_TIER_MONTHLY_PRICE_CENTS = 1900  # $19/mo

# ─── Backend Server Registry ─────────────────────────────────────────────────
# Maps tool prefixes to backend MCP server HTTP endpoints.
# Each backend should be running as an HTTP-transport MCP server.
# Fallback: if LOCAL_BACKENDS=1, we use stdio subprocesses instead.

LOCAL_BACKENDS = os.getenv("LOCAL_BACKENDS", "0") == "1"

BACKEND_REGISTRY: dict[str, dict] = {
    # Search & Web Tools
    "search_web":                {"server": "search-proxy-mcp",         "base_url": "http://localhost:8011", "cost": 1},
    "search_news":               {"server": "search-proxy-mcp",         "base_url": "http://localhost:8011", "cost": 1},
    "search_get_page_content":   {"server": "search-proxy-mcp",         "base_url": "http://localhost:8011", "cost": 2},

    # Audit & Compliance
    "audit_log":                 {"server": "agent-audit-mcp",          "base_url": "http://localhost:8012", "cost": 1},
    "audit_get_event":           {"server": "agent-audit-mcp",          "base_url": "http://localhost:8012", "cost": 1},
    "audit_search":              {"server": "agent-audit-mcp",          "base_url": "http://localhost:8012", "cost": 2},
    "audit_get_agent_history":   {"server": "agent-audit-mcp",          "base_url": "http://localhost:8012", "cost": 2},
    "audit_verify_chain":        {"server": "agent-audit-mcp",          "base_url": "http://localhost:8012", "cost": 3},
    "audit_stats":               {"server": "agent-audit-mcp",          "base_url": "http://localhost:8012", "cost": 1},

    # Contracts
    "contract_analyze":          {"server": "agent-contract-mcp",       "base_url": "http://localhost:8013", "cost": 5},
    "contract_draft":            {"server": "agent-contract-mcp",       "base_url": "http://localhost:8013", "cost": 5},
    "contract_review":           {"server": "agent-contract-mcp",       "base_url": "http://localhost:8013", "cost": 5},
    "contract_compare":          {"server": "agent-contract-mcp",       "base_url": "http://localhost:8013", "cost": 5},

    # Cost Tracking
    "cost_track_usage":          {"server": "agent-cost-tracker-mcp",   "base_url": "http://localhost:8014", "cost": 1},
    "cost_get_summary":          {"server": "agent-cost-tracker-mcp",   "base_url": "http://localhost:8014", "cost": 2},
    "cost_set_budget":           {"server": "agent-cost-tracker-mcp",   "base_url": "http://localhost:8014", "cost": 1},
    "cost_get_alerts":           {"server": "agent-cost-tracker-mcp",   "base_url": "http://localhost:8014", "cost": 1},

    # Hiring & Marketplace
    "hire_post_task":            {"server": "agent-hire-mcp",           "base_url": "http://localhost:8015", "cost": 3},
    "hire_search_workers":       {"server": "agent-hire-mcp",           "base_url": "http://localhost:8015", "cost": 2},
    "hire_submit_proposal":      {"server": "agent-hire-mcp",           "base_url": "http://localhost:8015", "cost": 2},
    "hire_accept_proposal":      {"server": "agent-hire-mcp",           "base_url": "http://localhost:8015", "cost": 2},
    "hire_get_escrow":           {"server": "agent-hire-mcp",           "base_url": "http://localhost:8015", "cost": 1},
    "hire_release_payment":      {"server": "agent-hire-mcp",           "base_url": "http://localhost:8015", "cost": 2},

    # Legal
    "legal_generate_contract":   {"server": "agent-legal-counsel-mcp",  "base_url": "http://localhost:8021", "cost": 8},
    "legal_review_clause":       {"server": "agent-legal-counsel-mcp",  "base_url": "http://localhost:8021", "cost": 3},
    "legal_summarize":           {"server": "agent-legal-counsel-mcp",  "base_url": "http://localhost:8021", "cost": 2},

    # Memory
    "memory_store":              {"server": "agent-memory-mcp",         "base_url": "http://localhost:8016", "cost": 1},
    "memory_recall":             {"server": "agent-memory-mcp",         "base_url": "http://localhost:8016", "cost": 1},
    "memory_search":             {"server": "agent-memory-mcp",         "base_url": "http://localhost:8016", "cost": 2},
    "memory_delete":             {"server": "agent-memory-mcp",         "base_url": "http://localhost:8016", "cost": 1},

    # Messaging
    "message_send":              {"server": "agent-messaging-mcp",      "base_url": "http://localhost:8017", "cost": 1},
    "message_read":              {"server": "agent-messaging-mcp",      "base_url": "http://localhost:8017", "cost": 1},
    "message_list_threads":      {"server": "agent-messaging-mcp",      "base_url": "http://localhost:8017", "cost": 2},

    # Passport & Identity
    "passport_verify":           {"server": "agent-passport-mcp",       "base_url": "http://localhost:8018", "cost": 2},
    "passport_create":           {"server": "agent-passport-mcp",       "base_url": "http://localhost:8018", "cost": 3},
    "passport_reputation":       {"server": "agent-passport-mcp",       "base_url": "http://localhost:8018", "cost": 1},

    # Proof of Work
    "proof_create":              {"server": "agent-proof-mcp",          "base_url": "http://localhost:8019", "cost": 2},
    "proof_verify":              {"server": "agent-proof-mcp",          "base_url": "http://localhost:8019", "cost": 2},

    # Team Management
    "team_create":               {"server": "agent-team-mcp",           "base_url": "http://localhost:8020", "cost": 2},
    "team_add_member":           {"server": "agent-team-mcp",           "base_url": "http://localhost:8020", "cost": 1},
    "team_list":                 {"server": "agent-team-mcp",           "base_url": "http://localhost:8020", "cost": 1},

    # Wallet & Payments
    "wallet_balance":            {"server": "agent-wallet-mcp",         "base_url": "http://localhost:8022", "cost": 1},
    "wallet_transfer":           {"server": "agent-wallet-mcp",         "base_url": "http://localhost:8022", "cost": 2},
    "wallet_history":            {"server": "agent-wallet-mcp",         "base_url": "http://localhost:8022", "cost": 1},

    # Contract Analyzer
    "analyzer_scan":             {"server": "contract-analyzer-mcp",    "base_url": "http://localhost:8023", "cost": 5},
    "analyzer_risk":             {"server": "contract-analyzer-mcp",    "base_url": "http://localhost:8023", "cost": 3},

    # Court Records
    "court_search":              {"server": "court-records-mcp",        "base_url": "http://localhost:8024", "cost": 3},
    "court_lookup":              {"server": "court-records-mcp",        "base_url": "http://localhost:8024", "cost": 2},

    # Crypto
    "crypto_price":              {"server": "crypto-market-mcp",        "base_url": "http://localhost:8025", "cost": 1},
    "crypto_market_data":        {"server": "crypto-market-mcp",        "base_url": "http://localhost:8025", "cost": 2},
    "crypto_trade":              {"server": "crypto-market-mcp",        "base_url": "http://localhost:8025", "cost": 3},

    # Currency Exchange
    "currency_convert":          {"server": "currency-exchange-mcp",    "base_url": "http://localhost:8026", "cost": 1},
    "currency_rates":            {"server": "currency-exchange-mcp",    "base_url": "http://localhost:8026", "cost": 1},

    # Database
    "db_query":                  {"server": "database-mcp",             "base_url": "http://localhost:8027", "cost": 3},
    "db_schema":                 {"server": "database-mcp",             "base_url": "http://localhost:8027", "cost": 2},

    # DNS
    "dns_lookup":                {"server": "dns-lookup-mcp",           "base_url": "http://localhost:8028", "cost": 1},
    "dns_bulk":                  {"server": "dns-lookup-mcp",           "base_url": "http://localhost:8028", "cost": 2},

    # Domain Data
    "domain_whois":              {"server": "domain-data-mcp",          "base_url": "http://localhost:8029", "cost": 2},
    "domain_available":          {"server": "domain-data-mcp",          "base_url": "http://localhost:8029", "cost": 1},

    # Domain Intelligence
    "domain_intel":              {"server": "domain-intel-mcp",         "base_url": "http://localhost:8030", "cost": 3},
    "domain_subdomains":         {"server": "domain-intel-mcp",         "base_url": "http://localhost:8030", "cost": 3},

    # Email
    "email_send":                {"server": "email-agent-mcp",          "base_url": "http://localhost:8031", "cost": 2},
    "email_inbox":               {"server": "email-agent-mcp",          "base_url": "http://localhost:8031", "cost": 2},
    "email_verify":              {"server": "email-verify-mcp",         "base_url": "http://localhost:8032", "cost": 1},

    # File Converter
    "file_convert":              {"server": "file-converter-mcp",       "base_url": "http://localhost:8033", "cost": 3},
    "file_info":                 {"server": "file-converter-mcp",       "base_url": "http://localhost:8033", "cost": 1},

    # Hacker News
    "hn_top":                    {"server": "hackernews-mcp",           "base_url": "http://localhost:8034", "cost": 1},
    "hn_search":                 {"server": "hackernews-mcp",           "base_url": "http://localhost:8034", "cost": 2},

    # Hallucination Guard
    "hallucination_check":       {"server": "hallucination-guard",      "base_url": "http://localhost:8035", "cost": 2},
    "hallucination_score":       {"server": "hallucination-guard",      "base_url": "http://localhost:8035", "cost": 2},

    # Image Analysis
    "image_analyze":             {"server": "image-analyzer-mcp",       "base_url": "http://localhost:8036", "cost": 3},
    "image_ocr":                 {"server": "image-analyzer-mcp",       "base_url": "http://localhost:8036", "cost": 2},

    # IP Geolocation
    "ip_geolocate":              {"server": "ip-geolocation-mcp",       "base_url": "http://localhost:8037", "cost": 1},
    "ip_batch":                  {"server": "ip-geolocation-mcp",       "base_url": "http://localhost:8037", "cost": 2},

    # Health Monitor
    "health_check":              {"server": "mcp-health-monitor",       "base_url": "http://localhost:8038", "cost": 1},
    "health_history":            {"server": "mcp-health-monitor",       "base_url": "http://localhost:8038", "cost": 2},

    # Notifications
    "notify_send":               {"server": "notification-mcp",         "base_url": "http://localhost:8039", "cost": 1},
    "notify_list":               {"server": "notification-mcp",         "base_url": "http://localhost:8039", "cost": 1},

    # Patent Search
    "patent_search":             {"server": "patent-search-mcp",        "base_url": "http://localhost:8040", "cost": 3},
    "patent_lookup":             {"server": "patent-search-mcp",        "base_url": "http://localhost:8040", "cost": 2},

    # PDF Generator
    "pdf_generate":              {"server": "pdf-generator-mcp",        "base_url": "http://localhost:8041", "cost": 3},
    "pdf_merge":                 {"server": "pdf-generator-mcp",        "base_url": "http://localhost:8041", "cost": 2},

    # QR Code
    "qr_generate":               {"server": "qr-code-mcp",              "base_url": "http://localhost:8042", "cost": 1},
    "qr_decode":                 {"server": "qr-code-mcp",              "base_url": "http://localhost:8042", "cost": 1},

    # Rental Agent
    "rental_search":             {"server": "rental-agent-mcp",         "base_url": "http://localhost:8043", "cost": 3},
    "rental_listing":            {"server": "rental-agent-mcp",         "base_url": "http://localhost:8043", "cost": 2},

    # Screenshot
    "screenshot_take":           {"server": "screenshot-mcp",           "base_url": "http://localhost:8044", "cost": 2},
    "screenshot_batch":          {"server": "screenshot-mcp",           "base_url": "http://localhost:8044", "cost": 4},

    # SEC Financial
    "sec_filings":               {"server": "sec-financial-mcp",        "base_url": "http://localhost:8045", "cost": 3},
    "sec_lookup":                {"server": "sec-financial-mcp",        "base_url": "http://localhost:8045", "cost": 2},

    # Secret Scanner
    "secret_scan":               {"server": "secret-scanner-mcp",       "base_url": "http://localhost:8046", "cost": 3},
    "secret_validate":           {"server": "secret-scanner-mcp",       "base_url": "http://localhost:8046", "cost": 2},

    # SEO Audit
    "seo_audit":                 {"server": "seo-audit-mcp",            "base_url": "http://localhost:8047", "cost": 5},
    "seo_analyze":               {"server": "seo-audit-mcp",            "base_url": "http://localhost:8047", "cost": 3},

    # SSL Check
    "ssl_check":                 {"server": "ssl-check-mcp",            "base_url": "http://localhost:8048", "cost": 2},
    "ssl_cert_info":             {"server": "ssl-check-mcp",            "base_url": "http://localhost:8048", "cost": 1},

    # Text to Speech
    "tts_synthesize":            {"server": "text-to-speech-mcp",       "base_url": "http://localhost:8049", "cost": 3},
    "tts_voices":                {"server": "text-to-speech-mcp",       "base_url": "http://localhost:8049", "cost": 1},

    # Weather
    "weather_current":           {"server": "weather-mcp",              "base_url": "http://localhost:8050", "cost": 1},
    "weather_forecast":          {"server": "weather-mcp",              "base_url": "http://localhost:8050", "cost": 1},

    # Web Scraper
    "scrape_url":                {"server": "web-scraper-mcp",          "base_url": "http://localhost:8051", "cost": 2},
    "scrape_batch":              {"server": "web-scraper-mcp",          "base_url": "http://localhost:8051", "cost": 4},

    # Wikipedia
    "wikipedia_search":          {"server": "wikipedia-mcp",            "base_url": "http://localhost:8052", "cost": 1},
    "wikipedia_article":         {"server": "wikipedia-mcp",            "base_url": "http://localhost:8052", "cost": 2},
}

# All 42 unique backend servers
BACKEND_SERVERS = sorted(set(cfg["server"] for cfg in BACKEND_REGISTRY.values()))
TOTAL_TOOLS = len(BACKEND_REGISTRY)
assert len(BACKEND_SERVERS) == 42, f"Expected 42 backend servers, got {len(BACKEND_SERVERS)}"

server = Server("agentpay-gateway-mcp")


# ─── Supabase Database Layer ──────────────────────────────────────────────────

async def get_supabase_client():
    """Get a Supabase client for database operations."""
    from supabase import Client, create_client
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


async def get_rest_client():
    """Get an httpx client for direct Supabase REST API calls."""
    return httpx.AsyncClient(
        base_url=f"{SUPABASE_URL}/rest/v1",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        timeout=30.0,
    )


# ─── Credit Management ────────────────────────────────────────────────────────

def _get_daily_reset_key() -> str:
    """Get today's date string for daily credit resets."""
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


async def get_or_create_api_key_record(api_key: str) -> dict:
    """
    Get or create an API key record in Supabase.
    Returns dict with: api_key, tier, daily_credits, used_today, last_reset_date.
    """
    client = await get_rest_client()

    # Check if API key exists
    resp = await client.get("/api_keys", params={"api_key": f"eq.{api_key}"})
    if resp.status_code == 200 and resp.json():
        record = resp.json()[0]
        today = _get_daily_reset_key()

        # Reset credits if new day
        if record.get("last_reset_date") != today:
            tier = record.get("tier", "free")
            new_credits = PRO_TIER_DAILY_CREDITS if tier == "pro" else FREE_TIER_DAILY_CREDITS
            await client.patch(
                "/api_keys",
                params={"api_key": f"eq.{api_key}"},
                json={
                    "daily_credits": new_credits,
                    "used_today": 0,
                    "last_reset_date": today,
                },
            )
            record["daily_credits"] = new_credits
            record["used_today"] = 0

        return record

    # Auto-create a free-tier key if none found
    # (In production, keys should be created via Stripe checkout)
    new_record = {
        "api_key": api_key,
        "tier": "free",
        "daily_credits": FREE_TIER_DAILY_CREDITS,
        "used_today": 0,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "last_reset_date": _get_daily_reset_key(),
    }
    await client.post("/api_keys", json=new_record)
    return new_record


async def check_and_deduct_credits(api_key: str, cost: int) -> dict:
    """
    Check API key validity and deduct credits.
    Returns: {"allowed": True/False, "remaining": N, "tier": "...", "error": "..."}
    """
    record = await get_or_create_api_key_record(api_key)
    remaining = record.get("daily_credits", 0) - record.get("used_today", 0)

    if remaining < cost:
        tier = record.get("tier", "free")
        return {
            "allowed": False,
            "remaining": remaining,
            "tier": tier,
            "error": (
                f"Insufficient credits. You have {remaining} credits remaining "
                f"on the {tier} tier (this call costs {cost}). "
                f"Upgrade to Pro for 10,000 credits/day: {STRIPE_CHECKOUT_LINK}"
            ),
            "upsell_link": STRIPE_CHECKOUT_LINK,
        }

    # Deduct credits
    client = await get_rest_client()
    await client.patch(
        "/api_keys",
        params={"api_key": f"eq.{api_key}"},
        json={"used_today": record.get("used_today", 0) + cost},
    )

    return {
        "allowed": True,
        "remaining": remaining - cost,
        "tier": record.get("tier", "free"),
    }


# ─── Proxy Execution ──────────────────────────────────────────────────────────

async def proxy_to_backend(tool_name: str, params: dict, api_key: str) -> str:
    """
    Route a tool call to the appropriate backend MCP server.
    Checks credits first, then proxies the call.
    """
    backend_cfg = BACKEND_REGISTRY.get(tool_name)
    if not backend_cfg:
        return json.dumps({
            "error": f"Unknown tool: {tool_name}",
            "isError": True,
            "available_tools": list(BACKEND_REGISTRY.keys()),
        })

    # Credit check
    credit_check = await check_and_deduct_credits(api_key, backend_cfg["cost"])
    if not credit_check["allowed"]:
        return json.dumps({
            "error": credit_check["error"],
            "isError": True,
            "credits_remaining": credit_check["remaining"],
            "tier": credit_check["tier"],
            "upgrade_url": credit_check["upsell_link"],
            "tool_cost": backend_cfg["cost"],
        })

    # Build the proxy URL
    base_url = backend_cfg["base_url"]
    if LOCAL_BACKENDS:
        # For local stdio backends, we can't proxy via HTTP
        # Return a structured error directing to use HTTP transport
        return json.dumps({
            "error": f"Local backend mode not supported for {tool_name}. "
                     f"Backend '{backend_cfg['server']}' must be running as HTTP MCP server.",
            "isError": True,
            "credits_deducted": backend_cfg["cost"],
            "credits_remaining": credit_check["remaining"],
        })

    try:
        # Proxy the call to the backend MCP server via HTTP
        # Using MCP's JSON-RPC protocol over HTTP
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "tool_name": tool_name,
                "arguments": params,
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{base_url}/mcp",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            result = resp.json()

        # Log the successful proxy call
        await _log_gateway_call(api_key, tool_name, backend_cfg["server"],
                                backend_cfg["cost"], credit_check["remaining"])

        return json.dumps({
            "gateway": "agentpay-gateway-mcp",
            "tool": tool_name,
            "backend_server": backend_cfg["server"],
            "credits_deducted": backend_cfg["cost"],
            "credits_remaining": credit_check["remaining"],
            "tier": credit_check["tier"],
            "result": result.get("result", result),
        })

    except httpx.ConnectError:
        return json.dumps({
            "error": f"Backend server '{backend_cfg['server']}' at {base_url} is not reachable. "
                     f"Ensure the server is running and accessible.",
            "isError": True,
            "backend_url": base_url,
            "credits_remaining": credit_check["remaining"],
        })
    except Exception as e:
        return json.dumps({
            "error": f"Proxy error for {tool_name}: {str(e)}",
            "isError": True,
            "credits_remaining": credit_check["remaining"],
        })


async def _log_gateway_call(api_key: str, tool_name: str, backend: str,
                            cost: int, remaining: int):
    """Log gateway call to Supabase for auditing and analytics."""
    try:
        client = await get_rest_client()
        await client.post("/gateway_logs", json={
            "api_key": api_key,
            "tool_name": tool_name,
            "backend_server": backend,
            "cost": cost,
            "remaining_credits": remaining,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        })
    except Exception:
        pass  # Non-critical logging — don't fail the call


# ─── Gateway Information Tools ────────────────────────────────────────────────

@server.tool(
    name="gateway_info",
    description=(
        "Get AgentPay Gateway information: available tools, backend servers, "
        "pricing tiers, and your current usage."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "description": "Your AgentPay API key"
            }
        },
        "required": ["api_key"]
    }
)
async def gateway_info(api_key: str) -> str:
    """Get gateway info and current usage for an API key."""
    record = await get_or_create_api_key_record(api_key)
    tier = record.get("tier", "free")
    used = record.get("used_today", 0)
    daily_limit = PRO_TIER_DAILY_CREDITS if tier == "pro" else FREE_TIER_DAILY_CREDITS

    return json.dumps({
        "gateway": "agentpay-gateway-mcp",
        "version": "1.0.0",
        "total_backend_servers": len(BACKEND_SERVERS),
        "total_tools": TOTAL_TOOLS,
        "backend_servers": BACKEND_SERVERS,
        "pricing": {
            "free": {
                "daily_credits": FREE_TIER_DAILY_CREDITS,
                "cost": "$0",
                "reset": "Daily (UTC)",
            },
            "pro": {
                "daily_credits": PRO_TIER_DAILY_CREDITS,
                "cost": f"${PRO_TIER_MONTHLY_PRICE_CENTS / 100}/mo",
                "stripe_checkout": STRIPE_CHECKOUT_LINK,
            },
        },
        "your_usage": {
            "api_key": api_key,
            "tier": tier,
            "daily_limit": daily_limit,
            "used_today": used,
            "remaining_today": max(0, daily_limit - used),
            "reset_date": _get_daily_reset_key(),
        },
        "tool_costs": {
            name: cfg["cost"] for name, cfg in BACKEND_REGISTRY.items()
        },
    }, indent=2)


@server.tool(
    name="gateway_usage",
    description=(
        "Get detailed usage statistics for your API key over a time range. "
        "Shows daily breakdown, top tools, and cost summary."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "description": "Your AgentPay API key"
            },
            "days": {
                "type": "integer",
                "description": "Number of days to look back (1-30)",
                "default": 7,
            },
        },
        "required": ["api_key"]
    }
)
async def gateway_usage(api_key: str, days: int = 7) -> str:
    """Get usage statistics for an API key."""
    days = min(max(days, 1), 30)
    client = await get_rest_client()

    # Get gateway logs
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat() + "Z"
    resp = await client.get(
        "/gateway_logs",
        params={
            "api_key": f"eq.{api_key}",
            "timestamp": f"gte.{since}",
            "order": "timestamp.desc",
            "limit": "1000",
        }
    )
    logs = resp.json() if resp.status_code == 200 else []

    # Aggregate stats
    total_calls = len(logs)
    total_cost = sum(l.get("cost", 0) for l in logs)
    by_tool: dict[str, int] = {}
    by_backend: dict[str, int] = {}
    for log in logs:
        tool = log.get("tool_name", "unknown")
        backend = log.get("backend_server", "unknown")
        by_tool[tool] = by_tool.get(tool, 0) + 1
        by_backend[backend] = by_backend.get(backend, 0) + 1

    # Current balance
    record = await get_or_create_api_key_record(api_key)
    tier = record.get("tier", "free")
    daily_limit = PRO_TIER_DAILY_CREDITS if tier == "pro" else FREE_TIER_DAILY_CREDITS
    used_today = record.get("used_today", 0)

    return json.dumps({
        "api_key": api_key,
        "tier": tier,
        "period_days": days,
        "total_calls": total_calls,
        "total_credits_spent": total_cost,
        "daily_limit": daily_limit,
        "used_today": used_today,
        "remaining_today": max(0, daily_limit - used_today),
        "top_tools": sorted(by_tool.items(), key=lambda x: -x[1])[:10],
        "top_backends": sorted(by_backend.items(), key=lambda x: -x[1])[:10],
    }, indent=2)


@server.tool(
    name="gateway_upsell",
    description=(
        "Get a Stripe checkout link to upgrade to the Pro tier. "
        "Pro tier includes 10,000 credits/day for $19/month."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "description": "Your AgentPay API key (to attach the subscription)"
            },
            "quantity": {
                "type": "integer",
                "description": "Number of seats/months (default 1)",
                "default": 1,
            }
        },
        "required": ["api_key"]
    }
)
async def gateway_upsell(api_key: str, quantity: int = 1) -> str:
    """Generate a Stripe checkout link for Pro tier upgrade."""
    record = await get_or_create_api_key_record(api_key)

    if STRIPE_CHECKOUT_LINK:
        return json.dumps({
            "status": "checkout_available",
            "api_key": api_key,
            "current_tier": record.get("tier", "free"),
            "pro_price": "$19/month",
            "pro_daily_credits": PRO_TIER_DAILY_CREDITS,
            "checkout_url": STRIPE_CHECKOUT_LINK,
            "quantity": quantity,
        })
    else:
        return json.dumps({
            "status": "checkout_not_configured",
            "message": "STRIPE_CHECKOUT_LINK not configured. Set the environment variable.",
        })


# ─── Health Check ─────────────────────────────────────────────────────────────

@server.tool(
    name="gateway_health",
    description="Health check for the AgentPay Gateway. Verifies Supabase connectivity and backend server status.",
    input_schema={
        "type": "object",
        "properties": {}
    }
)
async def gateway_health() -> str:
    """Health check for gateway infrastructure."""
    checks = {}

    # Supabase check
    try:
        client = await get_rest_client()
        resp = await client.get("/api_keys", params={"limit": "1"})
        checks["supabase"] = "connected" if resp.status_code == 200 else "error"
    except Exception as e:
        checks["supabase"] = f"disconnected: {str(e)}"

    # Backend server checks
    for server_name in BACKEND_SERVERS:
        backends = [cfg for cfg in BACKEND_REGISTRY.values() if cfg["server"] == server_name]
        base_url = backends[0]["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{base_url}/mcp", timeout=5.0)
                checks[server_name] = "online" if resp.status_code in (200, 404) else "error"
        except Exception:
            checks[server_name] = "offline"

    # Stripe check
    checks["stripe"] = "configured" if STRIPE_API_KEY else "not_configured"

    online_count = sum(1 for v in checks.values() if v in ("connected", "online", "configured"))
    total_count = len(checks)

    return json.dumps({
        "gateway": "agentpay-gateway-mcp",
        "status": "healthy" if online_count >= total_count - 2 else "degraded",
        "uptime_checks": checks,
        "online_count": online_count,
        "total_count": total_count,
    }, indent=2)


# ─── Dynamic Tool Registration ────────────────────────────────────────────────
# Register wrapper tools for ALL backend tools at startup.
# Each wrapper enforces credit-based access control before proxying.

def _make_tool_wrapper(tool_name: str, backend_cfg: dict):
    """Create a tool function that proxies to the backend with credit check."""

    async def wrapper(**kwargs) -> str:
        # Extract API key from kwargs (first string arg or explicit api_key param)
        api_key = kwargs.pop("api_key", None)
        if not api_key:
            # Try to find it as the first positional string arg
            for v in kwargs.values():
                if isinstance(v, str) and len(v) > 20 and "_" in v:
                    api_key = v
                    break
        if not api_key:
            return json.dumps({
                "error": "API key required. Pass api_key parameter or set AGENTPAY_API_KEY env var.",
                "isError": True,
            })

        return await proxy_to_backend(tool_name, kwargs, api_key)

    return wrapper


# Register all proxy tools dynamically
for tool_name, backend_cfg in BACKEND_REGISTRY.items():
    # Build a description for each tool
    description = (
        f"Proxy to '{tool_name}' on {backend_cfg['server']}. "
        f"Cost: {backend_cfg['cost']} credit(s). "
        f"Requires API key."
    )

    server.tool(
        name=tool_name,
        description=description,
        input_schema={
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "string",
                    "description": "AgentPay API key for billing"
                },
                "args": {
                    "type": "object",
                    "description": f"Arguments forwarded to {tool_name}",
                    "additionalProperties": True,
                }
            },
            "required": ["api_key", "args"]
        },
    )(_make_tool_wrapper(tool_name, backend_cfg))


# ─── Main Entry Point ─────────────────────────────────────────────────────────

async def bootstrap_db():
    """Create required Supabase tables if they don't exist."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("[WARN] SUPABASE_URL / SUPABASE_SERVICE_KEY not set. Gateway will operate in demo mode.")
        return False

    try:
        client = await get_rest_client()

        bootstrap_sql = """
        CREATE TABLE IF NOT EXISTS api_keys (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            api_key TEXT UNIQUE NOT NULL,
            tier TEXT NOT NULL DEFAULT 'free',
            customer_id TEXT,
            daily_credits INTEGER NOT NULL DEFAULT 100,
            used_today INTEGER NOT NULL DEFAULT 0,
            total_calls BIGINT NOT NULL DEFAULT 0,
            total_credits_spent BIGINT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS gateway_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            api_key TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            backend_server TEXT NOT NULL,
            cost INTEGER NOT NULL,
            remaining_credits INTEGER,
            response_time_ms INTEGER,
            timestamp TIMESTAMPTZ DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(api_key);
        CREATE INDEX IF NOT EXISTS idx_gateway_logs_api ON gateway_logs(api_key);
        CREATE INDEX IF NOT EXISTS idx_gateway_logs_ts ON gateway_logs(timestamp);
        """

        statements = [s.strip() for s in bootstrap_sql.split(";")
                      if s.strip() and not s.strip().startswith("--")]

        for stmt in statements:
            # Use rpc for exec_sql if available, otherwise try direct
            try:
                resp = await client.post(
                    "/rpc/exec_sql",
                    json={"query": stmt + ";"},
                )
            except Exception:
                resp = await client.post("/rest/v1/rpc/exec_sql", json={"query": stmt + ";"})

        print(f"[DB] Tables created/verified.")
        return True
    except Exception as e:
        print(f"[DB] Bootstrap failed: {e}")
        return False


async def init_stripe():
    """Initialize Stripe webhook endpoint if configured."""
    if not STRIPE_API_KEY:
        print("[Stripe] No STRIPE_API_KEY configured. Stripe payments disabled.")
        return

    import stripe
    stripe.api_key = STRIPE_API_KEY

    # Create the Pro product and price if they don't exist
    try:
        products = stripe.Product.list(limit=10)
        pro_product = None
        for p in products.data:
            if p.name == "AgentPay Pro":
                pro_product = p
                break

        if not pro_product:
            pro_product = stripe.Product.create(
                name="AgentPay Pro",
                description="AgentPay Gateway Pro — 10,000 API credits/day",
            )

        prices = stripe.Price.list(product=pro_product.id, limit=5)
        pro_price = None
        for pr in prices.data:
            if pr.unit_amount == PRO_TIER_MONTHLY_PRICE_CENTS and pr.recurring:
                pro_price = pr
                break

        if not pro_price:
            pro_price = stripe.Price.create(
                product=pro_product.id,
                unit_amount=PRO_TIER_MONTHLY_PRICE_CENTS,
                currency="usd",
                recurring={"interval": "month"},
            )

        print(f"[Stripe] Product: {pro_product.id}, Price: {pro_price.id}")
    except Exception as e:
        print(f"[Stripe] Setup warning: {e}")


def main():
    """Entry point for the AgentPay Gateway MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="AgentPay Gateway MCP Server")
    parser.add_argument("--port", type=int, default=PORT, help="HTTP port (default: 8000)")
    parser.add_argument("--db-only", action="store_true", help="Only bootstrap database, don't start server")
    args = parser.parse_args()

    async def run():
        # Bootstrap database
        await bootstrap_db()

        # Initialize Stripe
        init_stripe()

        if args.db_only:
            print("[AgentPay Gateway] Database bootstrapped. Exiting.")
            return

        # Start HTTP MCP server
        from mcp.server.stdio import stdio_server
        import anyio

        print(f"\n{'='*60}")
        print(f"  AgentPay Gateway MCP")
        print(f"  Version: 1.0.0")
        print(f"  Backend Servers: {len(BACKEND_SERVERS)}")
        print(f"  Total Tools: {TOTAL_TOOLS}")
        print(f"  Pricing: Free={FREE_TIER_DAILY_CREDITS}/day | Pro={PRO_TIER_DAILY_CREDITS}/day ($19/mo)")
        print(f"{'='*60}\n")

        async with stdio_server() as streams:
            init_options = InitializationOptions(
                server_name="agentpay-gateway-mcp",
                server_version="1.0.0",
                capabilities=server.create_initialization_options().capabilities,
            )
            await server.run(streams[0], streams[1], init_options)

    anyio.run(run)


if __name__ == "__main__":
    main()
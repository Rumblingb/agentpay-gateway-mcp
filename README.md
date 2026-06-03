# AgentPay Gateway MCP

One MCP installation gives your agent access to 42 backend servers — web search, legal analysis, domain intelligence, QR codes, email verification, SEC filings, patent lookup, and more — with per-call credit billing and one API key instead of 42.

## What your agent can do

- Call any of the 90+ tools across 42 specialized backend servers through a single MCP endpoint — no separate accounts or API keys per service
- Pay per call using a credit system: most tools cost 1–3 credits, compute-heavy tools (contract analysis, SEO audit, legal contract generation) cost 5–8 credits
- Check remaining daily credits and account status at any time via `gateway_info`
- Get a Stripe checkout link to upgrade when credits are exhausted — the server returns the URL directly
- Run in demo mode locally (no database) or full mode with Supabase-backed credit ledger and Stripe billing
- Deploy via Docker with environment variables for a production-ready self-hosted gateway

## Installation

**Requires:** Python 3.10+, `mcp`, `httpx`, `anyio` packages.

```bash
pip install mcp httpx anyio
```

The gateway runs as an HTTP server (not stdio). It must be started separately before connecting your MCP client.

```bash
# Demo mode — no database required
python server.py --port 8000

# Production mode — set env vars first
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_SERVICE_KEY=your-service-key
export STRIPE_API_KEY=sk_live_...
export STRIPE_CHECKOUT_LINK=https://buy.stripe.com/...
python server.py --port 8000
```

**Claude Desktop** — add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "agentpay-gateway": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "X-API-Key": "YOUR_API_KEY_HERE"
      }
    }
  }
}
```

**Cursor** — add to `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "agentpay-gateway": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "X-API-Key": "YOUR_API_KEY_HERE"
      }
    }
  }
}
```

**Docker:**

```bash
docker build -t agentpay-gateway .
docker run -p 8000:8000 \
  -e SUPABASE_URL=https://your-project.supabase.co \
  -e SUPABASE_SERVICE_KEY=your-service-key \
  -e STRIPE_API_KEY=sk_live_... \
  -e STRIPE_CHECKOUT_LINK=https://buy.stripe.com/... \
  agentpay-gateway
```

## Tool Reference

| Tool | Description | Key params |
|------|-------------|------------|
| `gateway_info` | Check credit balance, tier, and daily usage | `api_key` |
| `gateway_upsell` | Get Stripe checkout URL to upgrade to Pro | `api_key` |
| Any backend tool | Proxied to the appropriate backend server | `api_key`, plus the tool's own params in `args` |

### Credit costs by category

| Category | Tools | Credits per call |
|----------|-------|-----------------|
| Search, weather, DNS, QR, Wikipedia | `search_web`, `weather_current`, `dns_lookup`, `qr_generate`, etc. | 1 |
| Audit, memory, messaging, email verify | `audit_log`, `memory_store`, `message_send`, etc. | 1–2 |
| Domain intel, screenshots, crypto, PDF | `domain_intel`, `screenshot_take`, `pdf_generate`, etc. | 2–4 |
| Court records, SEC filings, patent search | `court_search`, `sec_filings`, `patent_search`, etc. | 2–3 |
| Contract analysis, legal, SEO audit | `contract_analyze`, `legal_generate_contract`, `seo_audit`, etc. | 3–8 |

## Backend Server Registry (42 servers)

| Category | Servers |
|----------|---------|
| Search & Web | search-proxy-mcp, web-scraper-mcp, hackernews-mcp, wikipedia-mcp |
| Compliance & Audit | agent-audit-mcp, hallucination-guard, secret-scanner-mcp |
| Finance | agent-wallet-mcp, crypto-market-mcp, currency-exchange-mcp, sec-financial-mcp |
| Legal | agent-contract-mcp, agent-legal-counsel-mcp, contract-analyzer-mcp, court-records-mcp |
| Identity & Trust | agent-passport-mcp, agent-proof-mcp |
| Agents & Teams | agent-hire-mcp, agent-team-mcp, agent-memory-mcp, agent-messaging-mcp |
| Domain & Network | dns-lookup-mcp, domain-data-mcp, domain-intel-mcp, ip-geolocation-mcp, ssl-check-mcp |
| Productivity | email-agent-mcp, email-verify-mcp, notification-mcp, pdf-generator-mcp, file-converter-mcp, qr-code-mcp, screenshot-mcp, text-to-speech-mcp |
| Intelligence | image-analyzer-mcp, patent-search-mcp, seo-audit-mcp, rental-agent-mcp, weather-mcp |
| Infrastructure | database-mcp, mcp-health-monitor, agent-cost-tracker-mcp |

## Pricing

| Tier | Daily credits | Monthly price | Cost per call |
|------|--------------|---------------|---------------|
| Free | 100 | $0 | 1–8 credits |
| Pro | 10,000 | $19/month | 1–8 credits |

Credits reset daily. When credits are exhausted, `gateway_upsell` returns a Stripe checkout URL.

## License

MIT — AgentPay Labs. Source: [github.com/Rumblingb/agentpay-gateway-mcp](https://github.com/Rumblingb/agentpay-gateway-mcp)

# AgentPay Gateway MCP

The **picks and shovels** play — a centralized API gateway that routes to all 42 MCP servers with **per-call billing**.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENTPAY GATEWAY MCP                         │
│                                                                 │
│  ┌──────────┐   ┌───────────┐   ┌──────────┐   ┌───────────┐  │
│  │ API Key  │──▶│ Credit    │──▶│ Routing  │──▶│ Backend   │  │
│  │ Auth     │   │ Check     │   │ Engine   │   │ MCP Server│  │
│  └──────────┘   └───────────┘   └──────────┘   └───────────┘  │
│       │              │              │              │            │
│       ▼              ▼              ▼              ▼            │
│  ┌──────────┐   ┌───────────┐   ┌──────────┐   ┌───────────┐  │
│  │ Supabase │   │ Supabase  │   │ Backend  │   │ Stripe    │  │
│  │ API Keys │   │ Credits   │   │ HTTP     │   │ Checkout  │  │
│  │ Table    │   │ Ledger    │   │ Proxy    │   │ Payments  │  │
│  └──────────┘   └───────────┘   └──────────┘   └───────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

- **Single MCP endpoint** routing to 42 backend MCP servers
- **Per-call credit billing** instead of per-subscription
- **Free tier**: 100 credits/day
- **Pro tier**: 10,000 credits/day ($19/mo)
- **Auto-reset** credits daily
- **Stripe upsell** links for upgrades
- **Full audit trail** with credit deduction logging

## Setup

### Prerequisites

- Python 3.10+
- MCP-compatible client (Claude Desktop, Cursor, etc.)
- Supabase project for database (optional for local demo)
- Stripe account (optional, for production billing)

### Quick Start (Demo Mode — No DB Required)

```bash
cd agentpay-gateway-mcp
pip install -r requirements.txt
python3 server.py
```

### Full Setup (With Supabase + Stripe)

1. **Create a Supabase project** at https://supabase.com
2. **Set environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```
3. **Bootstrap the database**:
   ```bash
   python3 server.py --db-only
   ```
4. **Start the gateway**:
   ```bash
   python3 server.py --port 8000
   ```

### Docker

```bash
docker build -t agentpay-gateway .
docker run -p 8000:8000 \
  -e SUPABASE_URL=xxx \
  -e SUPABASE_SERVICE_KEY=xxx \
  -e STRIPE_API_KEY=sk_live_xxx \
  -e STRIPE_CHECKOUT_LINK=https://buy.stripe.com/xxx \
  agentpay-gateway
```

## MCP Client Configuration

```json
{
  "mcpServers": {
    "agentpay-gateway": {
      "url": "http://localhost:8000/mcp",
      "apiKey": "YOUR_API_KEY_HERE"
    }
  }
}
```

## Pricing Tiers

| Tier | Daily Credits | Monthly Price | Cost per Call |
|------|--------------|---------------|---------------|
| Free | 100 | $0 | 1 credit/call |
| Pro | 10,000 | $19/mo | 1 credit/call |

## Usage

### Check Balance
```python
result = await client.call_tool("gateway_info", {
    "api_key": "your-api-key"
})
```

### Use Any Tool
```python
# All 42 tools are proxied through the gateway
result = await client.call_tool("search_web", {
    "api_key": "your-api-key",
    "args": {"query": "latest news", "max_results": 5}
})
```

### Upgrade to Pro
```python
result = await client.call_tool("gateway_upsell", {
    "api_key": "your-api-key"
})
# Returns Stripe checkout URL
```

## Backend Server Registry

All 42 MCP servers routed through this gateway:

| Server | Tools | Port |
|--------|-------|------|
| search-proxy-mcp | 3 | 8011 |
| agent-audit-mcp | 5 | 8012 |
| agent-contract-mcp | 4 | 8013 |
| agent-cost-tracker-mcp | 4 | 8014 |
| agent-hire-mcp | 6 | 8015 |
| agent-legal-counsel-mcp | 3 | 8021 |
| agent-memory-mcp | 4 | 8016 |
| agent-messaging-mcp | 3 | 8017 |
| agent-passport-mcp | 3 | 8018 |
| agent-proof-mcp | 2 | 8019 |
| agent-team-mcp | 3 | 8020 |
| agent-wallet-mcp | 3 | 8022 |
| contract-analyzer-mcp | 2 | 8023 |
| court-records-mcp | 2 | 8024 |
| crypto-market-mcp | 3 | 8025 |
| currency-exchange-mcp | 2 | 8026 |
| database-mcp | 2 | 8027 |
| dns-lookup-mcp | 2 | 8028 |
| domain-data-mcp | 2 | 8029 |
| domain-intel-mcp | 2 | 8030 |
| email-agent-mcp | 3 | 8031 |
| email-verify-mcp | 1 | 8032 |
| file-converter-mcp | 2 | 8033 |
| hackernews-mcp | 2 | 8034 |
| hallucination-guard | 2 | 8035 |
| image-analyzer-mcp | 2 | 8036 |
| ip-geolocation-mcp | 2 | 8037 |
| mcp-health-monitor | 2 | 8038 |
| notification-mcp | 2 | 8039 |
| patent-search-mcp | 2 | 8040 |
| pdf-generator-mcp | 2 | 8041 |
| qr-code-mcp | 2 | 8042 |
| rental-agent-mcp | 2 | 8043 |
| screenshot-mcp | 2 | 8044 |
| sec-financial-mcp | 2 | 8045 |
| secret-scanner-mcp | 2 | 8046 |
| seo-audit-mcp | 2 | 8047 |
| ssl-check-mcp | 2 | 8048 |
| text-to-speech-mcp | 2 | 8049 |
| weather-mcp | 2 | 8050 |
| web-scraper-mcp | 2 | 8051 |
| wikipedia-mcp | 2 | 8052 |

## License

MIT — AgentPay Labs
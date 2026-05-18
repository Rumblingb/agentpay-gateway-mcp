#!/usr/bin/env python3
"""
AgentPay Gateway MCP — Development Runner with Mock Backends

Run this for local development without needing real MCP backend servers.
It starts mock HTTP MCP servers that respond with sample data, letting you
test the gateway's routing, billing, and credit logic end-to-end.

Usage:
    python3 run_dev.py          # Start gateway + mock backends
    python3 run_dev.py --test   # Run tests against mocks
"""

from __future__ import annotations

import asyncio
import json
import sys
import os
import uuid
import datetime
import argparse

import httpx
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ─── Mock Backend Server ─────────────────────────────────────────────────────

class MockMCPHandler(BaseHTTPRequestHandler):
    """Minimal HTTP MCP server that responds to MCP tool calls."""

    server_name = "mock-backend"

    def log_message(self, format, *args):
        pass  # Suppress logging

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
            return

        method = payload.get("method", "")
        request_id = payload.get("id", str(uuid.uuid4()))

        if method == "tools/call":
            tool_name = payload.get("params", {}).get("tool_name", "")
            args = payload.get("params", {}).get("arguments", {})
            response = self.handle_tool_call(tool_name, args)
        elif method == "tools/list":
            response = self.handle_tool_list()
        elif method == "initialize":
            response = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                }
            }
        else:
            response = {"error": f"Unknown method: {method}"}

        self._send_json({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": response,
        })

    def handle_tool_list(self):
        return {
            "tools": [
                {
                    "name": self.server_name + "_tool",
                    "description": f"Mock tool for {self.server_name}",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Test query"}
                        }
                    }
                }
            ]
        }

    def handle_tool_call(self, tool_name: str, args: dict) -> dict:
        """Generate mock response for any tool call."""
        api_key = args.get("api_key", "")
        actual_args = args.get("args", args)

        # Simulate different tool behaviors
        if "search" in tool_name.lower():
            return {
                "query": actual_args.get("query", "test"),
                "results": [
                    {"title": f"Mock Result 1 for {tool_name}", "url": "https://example.com/1"},
                    {"title": f"Mock Result 2 for {tool_name}", "url": "https://example.com/2"},
                ],
                "source": self.server_name,
            }
        elif "weather" in tool_name.lower():
            return {
                "location": actual_args.get("location", "Earth"),
                "temperature": 72,
                "conditions": "Partly Cloudy",
                "humidity": 0.65,
                "source": self.server_name,
            }
        elif "crypto" in tool_name.lower():
            return {
                "symbol": actual_args.get("symbol", "BTC"),
                "price_usd": 67542.50,
                "change_24h": "+2.3%",
                "source": self.server_name,
            }
        elif "wikipedia" in tool_name.lower():
            return {
                "query": actual_args.get("query", "test"),
                "summary": f"Mock Wikipedia article about {actual_args.get('query', 'the query')}.",
                "source": self.server_name,
            }
        elif "dns" in tool_name.lower():
            return {
                "domain": actual_args.get("domain", "example.com"),
                "records": [
                    {"type": "A", "value": "93.184.216.34"},
                    {"type": "MX", "value": "mail.example.com"},
                ],
                "source": self.server_name,
            }
        elif "ssl" in tool_name.lower():
            return {
                "domain": actual_args.get("domain", "example.com"),
                "valid": True,
                "expires": "2027-05-13",
                "issuer": "Let's Encrypt",
                "source": self.server_name,
            }
        elif "image" in tool_name.lower():
            return {
                "analysis": f"Mock analysis of image from {self.server_name}",
                "labels": ["architecture", "outdoor"],
                "confidence": 0.89,
                "source": self.server_name,
            }
        elif "health" in tool_name.lower():
            return {
                "status": "healthy",
                "uptime": "99.9%",
                "source": self.server_name,
            }
        elif "notify" in tool_name.lower() or "message" in tool_name.lower() or "email" in tool_name.lower():
            return {
                "status": "sent",
                "id": f"msg_{uuid.uuid4().hex[:8]}",
                "source": self.server_name,
            }
        elif "audit" in tool_name.lower():
            return {
                "events": [],
                "total": 0,
                "chain_valid": True,
                "source": self.server_name,
            }
        elif "passport" in tool_name.lower():
            return {
                "verified": True,
                "reputation_score": 85,
                "source": self.server_name,
            }
        elif "wallet" in tool_name.lower():
            return {
                "balance": 1000,
                "currency": "AGP",
                "source": self.server_name,
            }
        elif "contract" in tool_name.lower() or "analyze" in tool_name.lower():
            return {
                "analysis": f"Contract analysis from {self.server_name}",
                "risk_score": 0.15,
                "clauses": 12,
                "source": self.server_name,
            }
        elif "seo" in tool_name.lower():
            return {
                "score": 78,
                "issues": ["missing meta description", "slow load time"],
                "source": self.server_name,
            }
        elif "scrape" in tool_name.lower():
            return {
                "content": f"Scraped content from {self.server_name}",
                "word_count": 2450,
                "source": self.server_name,
            }
        elif "translate" in tool_name.lower() or "file" in tool_name.lower() or "pdf" in tool_name.lower() or "qr" in tool_name.lower():
            return {
                "result": f"Operation completed by {self.server_name}",
                "source": self.server_name,
            }
        elif "crime" in tool_name.lower() or "court" in tool_name.lower():
            return {
                "records": [],
                "count": 0,
                "source": self.server_name,
            }
        elif "patent" in tool_name.lower():
            return {
                "results": [],
                "total": 0,
                "source": self.server_name,
            }
        elif "secret" in tool_name.lower():
            return {
                "scan_result": "clean",
                "secrets_found": 0,
                "source": self.server_name,
            }
        elif "rental" in tool_name.lower():
            return {
                "listings": [],
                "average_price": 1500,
                "source": self.server_name,
            }
        elif "screenshot" in tool_name.lower():
            return {
                "screenshot_url": f"https://example.com/screenshot_{uuid.uuid4().hex[:8]}.png",
                "source": self.server_name,
            }
        elif "text-to-speech" in tool_name.lower() or "tts" in tool_name.lower():
            return {
                "audio_url": f"https://example.com/audio_{uuid.uuid4().hex[:8]}.mp3",
                "duration_seconds": 30,
                "source": self.server_name,
            }
        elif "memory" in tool_name.lower():
            return {
                "stored": True,
                "key": actual_args.get("key", "default"),
                "source": self.server_name,
            }
        elif "domain-intel" in tool_name.lower() or "domain_intel" in tool_name.lower():
            return {
                "domain": actual_args.get("domain", "example.com"),
                "risk_score": 0.2,
                "whois": {"registrar": "Mock Registrar", "created": "2020-01-01"},
                "source": self.server_name,
            }
        elif "currency" in tool_name.lower() or "exchange" in tool_name.lower():
            return {
                "from": actual_args.get("from", "USD"),
                "to": actual_args.get("to", "EUR"),
                "rate": 0.92,
                "result": actual_args.get("amount", 100) * 0.92,
                "source": self.server_name,
            }
        elif "team" in tool_name.lower():
            return {
                "team": [{"id": "agent_1", "name": "Alpha Agent", "role": "analyst"}],
                "source": self.server_name,
            }
        elif "hire" in tool_name.lower():
            return {
                "tasks": [],
                "escrow_balance": 0,
                "source": self.server_name,
            }
        elif "legal" in tool_name.lower():
            return {
                "contract": f"Mock legal contract from {self.server_name}",
                "clauses": 8,
                "jurisdiction": "US-DE",
                "source": self.server_name,
            }
        elif "cost" in tool_name.lower():
            return {
                "total_spend": 0,
                "budget": 1000,
                "alerts": [],
                "source": self.server_name,
            }
        elif "sec" in tool_name.lower() and "financial" in tool_name.lower():
            return {
                "filings": [],
                "total": 0,
                "source": self.server_name,
            }
        elif "homepage" in tool_name.lower() or "landing" in tool_name.lower():
            return {
                "html": f"<html><body>Mock landing page from {self.server_name}</body></html>",
                "source": self.server_name,
            }
        elif "proof" in tool_name.lower():
            return {
                "proof": f"Mock proof_{uuid.uuid4().hex[:16]}",
                "verified": True,
                "source": self.server_name,
            }
        elif "speaker" in tool_name.lower() or "agent" in tool_name.lower():
            return {
                "speakers": [],
                "count": 0,
                "source": self.server_name,
            }
        elif "hacker" in tool_name.lower() or "hn" in tool_name.lower():
            return {
                "stories": [
                    {"title": "Mock HN Story", "score": 100, "url": "https://news.ycombinator.com/item?id=999999"}
                ],
                "source": self.server_name,
            }
        else:
            return {
                "result": f"Mock response for {tool_name}",
                "args_received": actual_args,
                "source": self.server_name,
            }

    def _send_json(self, data):
        body = json.dumps(data, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode())


def run_mock_server(port: int, server_name: str):
    """Run a mock MCP server on the given port."""
    handler = type("Handler", (MockMCPHandler,), {"server_name": server_name})
    httpd = HTTPServer(("127.0.0.1", port), handler)
    print(f"  [{server_name}] Mock server started on port {port}")
    httpd.serve_forever()


# ─── Mock Backend Registry ──────────────────────────────────────────────────

MOCK_BACKENDS = [
    ("search-proxy-mcp",          8011),
    ("agent-audit-mcp",           8012),
    ("agent-contract-mcp",        8013),
    ("agent-cost-tracker-mcp",    8014),
    ("agent-hire-mcp",            8015),
    ("agent-legal-counsel-mcp",   8021),
    ("agent-memory-mcp",          8016),
    ("agent-messaging-mcp",       8017),
    ("agent-passport-mcp",        8018),
    ("agent-proof-mcp",           8019),
    ("agent-team-mcp",            8020),
    ("agent-wallet-mcp",          8022),
    ("contract-analyzer-mcp",     8023),
    ("court-records-mcp",         8024),
    ("crypto-market-mcp",         8025),
    ("currency-exchange-mcp",     8026),
    ("database-mcp",              8027),
    ("dns-lookup-mcp",            8028),
    ("domain-data-mcp",           8029),
    ("domain-intel-mcp",          8030),
    ("email-agent-mcp",           8031),
    ("email-verify-mcp",          8032),
    ("file-converter-mcp",        8033),
    ("hackernews-mcp",            8034),
    ("hallucination-guard",       8035),
    ("image-analyzer-mcp",        8036),
    ("ip-geolocation-mcp",        8037),
    ("mcp-health-monitor",        8038),
    ("notification-mcp",          8039),
    ("patent-search-mcp",         8040),
    ("pdf-generator-mcp",         8041),
    ("qr-code-mcp",               8042),
    ("rental-agent-mcp",          8043),
    ("screenshot-mcp",            8044),
    ("sec-financial-mcp",         8045),
    ("secret-scanner-mcp",        8046),
    ("seo-audit-mcp",             8047),
    ("ssl-check-mcp",             8048),
    ("text-to-speech-mcp",        8049),
    ("weather-mcp",               8050),
    ("web-scraper-mcp",           8051),
    ("wikipedia-mcp",             8052),
]

assert len(MOCK_BACKENDS) == 42, f"Expected 42 mock backends, got {len(MOCK_BACKENDS)}"


async def run_gateway():
    """Start the gateway server in this process."""
    from server import main as gateway_main

    # Set env to use mock backends
    os.environ["LOCAL_BACKENDS"] = "0"

    # Patch the server's backend URLs to point to our mocks
    from server import BACKEND_REGISTRY
    # Override each backend's base_url to localhost
    for name, cfg in BACKEND_REGISTRY.items():
        for mock_name, mock_port in MOCK_BACKENDS:
            if cfg["server"] == mock_name:
                cfg["base_url"] = f"http://127.0.0.1:{mock_port}"
                break

    print("\n  Gateway routing updated to localhost mock servers.\n")

    # Run the gateway
    gateway_main()


async def run_tests_against_mocks():
    """Run the test suite against mock backends."""
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"])


async def main():
    parser = argparse.ArgumentParser(description="AgentPay Gateway Dev Runner")
    parser.add_argument("--test", action="store_true", help="Run tests after starting servers")
    parser.add_argument("--gateway-only", action="store_true", help="Start only the gateway (backends must be running separately)")
    args = parser.parse_args()

    if args.gateway_only:
        await run_gateway()
        return

    # Start all 42 mock backend servers in background threads
    print(f"\n{'='*60}")
    print(f"  Starting 42 Mock Backend Servers...")
    print(f"{'='*60}\n")

    threads = []
    for server_name, port in MOCK_BACKENDS:
        t = threading.Thread(target=run_mock_server, args=(port, server_name), daemon=True)
        t.start()
        threads.append(t)

    # Give servers time to start
    await asyncio.sleep(1.0)

    # Patch gateway registry
    from server import BACKEND_REGISTRY
    for name, cfg in BACKEND_REGISTRY.items():
        for mock_name, mock_port in MOCK_BACKENDS:
            if cfg["server"] == mock_name:
                cfg["base_url"] = f"http://127.0.0.1:{mock_port}"
                break

    if args.test:
        print("\n  Running tests...\n")
        await run_tests_against_mocks()
    else:
        print("\n  All mock servers running. Starting gateway...\n")
        await run_gateway()


if __name__ == "__main__":
    asyncio.run(main())
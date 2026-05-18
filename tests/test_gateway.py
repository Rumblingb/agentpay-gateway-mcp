#!/usr/bin/env python3
"""
Tests for AgentPay Gateway MCP
Run: python3 -m pytest tests/ -v
"""

import pytest
import json
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_api_key():
    """Return a sample API key for testing."""
    return "test_key_abc123def456"


@pytest.fixture
def pro_api_key():
    """Return a sample Pro-tier API key."""
    return "pro_key_xyz789"


# ─── Test: Backend Registry ──────────────────────────────────────────────────

def test_backend_registry_has_all_servers():
    """Verify all 42 backend servers are registered."""
    from server import BACKEND_REGISTRY, BACKEND_SERVERS

    assert len(BACKEND_SERVERS) == 42, f"Expected 42 servers, got {len(BACKEND_SERVERS)}"
    assert len(BACKEND_REGISTRY) >= 42, "Should have at least 42 tools"
    assert "search_web" in BACKEND_REGISTRY
    assert "weather_current" in BACKEND_REGISTRY
    assert "wikipedia_search" in BACKEND_REGISTRY
    assert "crypto_price" in BACKEND_REGISTRY


def test_backend_registry_costs():
    """Verify all tools have a cost assigned."""
    from server import BACKEND_REGISTRY

    for tool, cfg in BACKEND_REGISTRY.items():
        assert "cost" in cfg, f"Tool {tool} missing cost"
        assert cfg["cost"] >= 1, f"Tool {tool} cost must be >= 1"
        assert cfg["server"] in BACKEND_SERVERS, f"Tool {tool} has unknown server {cfg['server']}"


def test_backend_servers_count():
    """Verify exactly 42 unique backend servers."""
    from server import BACKEND_SERVERS
    assert len(BACKEND_SERVERS) == 42


# ─── Test: Credit Management ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_or_create_api_key_record(sample_api_key):
    """Test that API key records are created on first access."""
    from unittest.mock import AsyncMock, patch, MagicMock

    mock_record = {
        "api_key": sample_api_key,
        "tier": "free",
        "daily_credits": 100,
        "used_today": 0,
        "last_reset_date": "2026-05-13",
    }

    with patch("server.get_rest_client", return_value=AsyncMock()) as mock_client_fn:
        mock_client = mock_client_fn.return_value
        mock_client.get.return_value = MagicMock(status_code=200, json=lambda: [mock_record])

        from server import get_or_create_api_key_record
        result = await get_or_create_api_key_record(sample_api_key)

        assert result["api_key"] == sample_api_key
        assert result["tier"] == "free"
        assert result["daily_credits"] == 100


@pytest.mark.asyncio
async def test_check_and_deduct_credits_free_tier(sample_api_key):
    """Test credit deduction on free tier."""
    mock_record = {
        "api_key": sample_api_key,
        "tier": "free",
        "daily_credits": 100,
        "used_today": 0,
        "last_reset_date": "2026-05-13",
    }

    with patch("server.get_rest_client", return_value=AsyncMock()) as mock_client_fn:
        mock_client = mock_client_fn.return_value
        mock_client.get.return_value = MagicMock(status_code=200, json=lambda: [mock_record])
        mock_client.patch.return_value = MagicMock(status_code=200, json=lambda: [mock_record])

        from server import check_and_deduct_credits
        result = await check_and_deduct_credits(sample_api_key, 5)

        assert result["allowed"] is True
        assert result["remaining"] == 95
        assert result["tier"] == "free"


@pytest.mark.asyncio
async def test_check_and_deduct_credits_insufficient(sample_api_key):
    """Test that insufficient credits are denied with upsell link."""
    import os
    os.environ.setdefault("STRIPE_CHECKOUT_LINK", "https://buy.stripe.com/test")

    mock_record = {
        "api_key": sample_api_key,
        "tier": "free",
        "daily_credits": 100,
        "used_today": 98,
        "last_reset_date": "2026-05-13",
    }

    with patch("server.get_rest_client", return_value=AsyncMock()) as mock_client_fn:
        mock_client = mock_client_fn.return_value
        mock_client.get.return_value = MagicMock(status_code=200, json=lambda: [mock_record])

        from server import check_and_deduct_credits
        result = await check_and_deduct_credits(sample_api_key, 5)

        assert result["allowed"] is False
        assert result["remaining"] == 2
        assert "upgrade" in result["error"].lower() or "upsell" in result.get("upsell_link", "").lower()


@pytest.mark.asyncio
async def test_check_and_deduct_credits_pro_tier(pro_api_key):
    """Test that pro tier has 10,000 credits."""
    mock_record = {
        "api_key": pro_api_key,
        "tier": "pro",
        "daily_credits": 10000,
        "used_today": 500,
        "last_reset_date": "2026-05-13",
    }

    with patch("server.get_rest_client", return_value=AsyncMock()) as mock_client_fn:
        mock_client = mock_client_fn.return_value
        mock_client.get.return_value = MagicMock(status_code=200, json=lambda: [mock_record])
        mock_client.patch.return_value = MagicMock(status_code=200, json=lambda: [mock_record])

        from server import check_and_deduct_credits, PRO_TIER_DAILY_CREDITS
        result = await check_and_deduct_credits(pro_api_key, 50)

        assert result["allowed"] is True
        assert result["remaining"] == PRO_TIER_DAILY_CREDITS - 500 - 50
        assert result["tier"] == "pro"


@pytest.mark.asyncio
async def test_daily_credit_reset(sample_api_key):
    """Test that credits reset on a new day."""
    mock_record_old = {
        "api_key": sample_api_key,
        "tier": "free",
        "daily_credits": 0,
        "used_today": 100,
        "last_reset_date": "2026-05-12",  # Yesterday
    }

    updated_record = dict(mock_record_old)
    updated_record["daily_credits"] = 100
    updated_record["used_today"] = 0
    updated_record["last_reset_date"] = "2026-05-13"

    with patch("server._get_daily_reset_key", return_value="2026-05-13"):
        with patch("server.get_rest_client", return_value=AsyncMock()) as mock_client_fn:
            mock_client = mock_client_fn.return_value
            mock_client.get.return_value = MagicMock(status_code=200, json=lambda: [mock_record_old])
            mock_client.patch.return_value = MagicMock(status_code=200, json=lambda: [updated_record])

            from server import get_or_create_api_key_record
            result = await get_or_create_api_key_record(sample_api_key)

            assert result["daily_credits"] == 100
            assert result["used_today"] == 0


# ─── Test: Gateway Info ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gateway_info(sample_api_key):
    """Test gateway_info returns expected structure."""
    with patch("server.get_or_create_api_key_record") as mock_get:
        mock_get.return_value = {
            "tier": "free",
            "daily_credits": 100,
            "used_today": 10,
        }

        from server import gateway_info
        result = json.loads(await gateway_info(sample_api_key))

        assert result["gateway"] == "agentpay-gateway-mcp"
        assert "total_backend_servers" in result
        assert result["your_usage"]["tier"] == "free"
        assert result["your_usage"]["remaining_today"] == 90
        assert "pricing" in result


@pytest.mark.asyncio
async def test_gateway_usage(sample_api_key):
    """Test gateway_usage returns expected structure."""
    with patch("server.get_rest_client") as mock_rest_fn:
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(status_code=200, json=lambda: [
            {"tool_name": "search_web", "cost": 1, "timestamp": "2026-05-13T10:00:00Z"},
            {"tool_name": "search_web", "cost": 1, "timestamp": "2026-05-13T10:01:00Z"},
            {"tool_name": "crypto_price", "cost": 1, "timestamp": "2026-05-13T10:02:00Z"},
        ])
        mock_rest_fn.return_value = mock_client

        with patch("server.get_or_create_api_key_record") as mock_get:
            mock_get.return_value = {
                "tier": "free",
                "daily_credits": 100,
                "used_today": 3,
            }

            from server import gateway_usage
            result = json.loads(await gateway_usage(sample_api_key, days=7))

            assert result["total_calls"] == 3
            assert result["total_credits_spent"] == 3
            assert len(result["top_tools"]) == 2


@pytest.mark.asyncio
async def test_gateway_upsell(sample_api_key):
    """Test upsell returns checkout link."""
    import os
    os.environ.setdefault("STRIPE_CHECKOUT_LINK", "https://buy.stripe.com/test")

    with patch("server.get_or_create_api_key_record") as mock_get:
        mock_get.return_value = {
            "tier": "free",
            "daily_credits": 100,
            "used_today": 0,
        }

        from server import gateway_upsell
        result = json.loads(await gateway_upsell(sample_api_key))

        assert result["status"] == "checkout_available"
        assert "checkout_url" in result


# ─── Test: Proxy Logic ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_proxy_to_backend_success(sample_api_key):
    """Test successful proxy call with credit deduction."""
    with patch("server.check_and_deduct_credits") as mock_credits:
        mock_credits.return_value = {
            "allowed": True,
            "remaining": 95,
            "tier": "free",
        }

        with patch("server.httpx.AsyncClient") as mock_http:
            mock_resp = AsyncMock()
            mock_resp.json.return_value = {"result": {"data": "test"}}
            mock_resp.status_code = 200

            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__.return_value = mock_resp
            mock_ctx_mgr.__aexit__.return_value = None
            mock_http.return_value = mock_ctx_mgr

            from server import proxy_to_backend
            result = json.loads(await proxy_to_backend("search_web", {"query": "test"}, sample_api_key))

            assert "gateway" in result
            assert result["credits_remaining"] == 95


@pytest.mark.asyncio
async def test_proxy_to_backend_rate_limited(sample_api_key):
    """Test proxy returns error when credits are insufficient."""
    with patch("server.check_and_deduct_credits") as mock_credits:
        mock_credits.return_value = {
            "allowed": False,
            "remaining": 0,
            "tier": "free",
            "error": "Insufficient credits",
            "upsell_link": "https://buy.stripe.com/test",
        }

        from server import proxy_to_backend
        result = json.loads(await proxy_to_backend("search_web", {"query": "test"}, sample_api_key))

        assert result["isError"] is True
        assert "Insufficient credits" in result["error"]
        assert result["credits_remaining"] == 0


@pytest.mark.asyncio
async def test_proxy_to_backend_unknown_tool(sample_api_key):
    """Test proxy returns error for unknown tool."""
    from server import proxy_to_backend
    result = json.loads(await proxy_to_backend("nonexistent_tool", {}, sample_api_key))

    assert result["isError"] is True
    assert "Unknown tool" in result["error"]


# ─── Test: Health Check ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gateway_health():
    """Test health check returns expected structure."""
    from server import gateway_health
    result = json.loads(await gateway_health())

    assert result["gateway"] == "agentpay-gateway-mcp"
    assert "uptime_checks" in result
    assert "online_count" in result
    assert "total_count" in result


# ─── Test: Missing API Key ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_api_key():
    """Test that missing API key returns proper error."""
    from server import proxy_to_backend
    result = json.loads(await proxy_to_backend("search_web", {"query": "test"}, ""))

    assert result["isError"] is True
    assert "API key" in result["error"]


# ─── Test: Credit Cost Mapping ───────────────────────────────────────────────

def test_cost_tiers():
    """Verify cost tiers are reasonable."""
    from server import BACKEND_REGISTRY

    for tool, cfg in BACKEND_REGISTRY.items():
        # Basic tools cost 1-2
        assert cfg["cost"] >= 1, f"{tool} cost must be >= 1"
        # Complex tools can cost up to 8
        assert cfg["cost"] <= 8, f"{tool} cost must be <= 8"


def test_search_tools_cost():
    """Verify search tools are cheapest (1-2 credits)."""
    from server import BACKEND_REGISTRY

    search_tools = ["search_web", "search_news", "search_get_page_content"]
    for tool in search_tools:
        assert tool in BACKEND_REGISTRY
        assert BACKEND_REGISTRY[tool]["cost"] <= 2


def test_complex_tools_cost_more():
    """Verify complex tools (contract analysis, etc.) cost more."""
    from server import BACKEND_REGISTRY

    complex_tools = [
        "contract_analyze", "analyzer_scan", "seo_audit",
        "legal_generate_contract", "pdf_generate",
    ]
    for tool in complex_tools:
        if tool in BACKEND_REGISTRY:
            assert BACKEND_REGISTRY[tool]["cost"] >= 3, f"{tool} should be more expensive"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
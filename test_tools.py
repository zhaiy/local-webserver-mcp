#!/usr/bin/env python3
"""Test script for the MCP Web Server."""

import asyncio
from mcp_web_server.server import (
    web_search,
    extract_webpage_content,
    http_request,
    fetch_json,
)


async def test_all():
    """Test all tools."""
    print("=" * 60)
    print("MCP Web Server - Tools Test")
    print("=" * 60)

    # Test 1: Web Search
    print("\n[1] Testing web_search...")
    results = web_search("MCP protocol", num_results=3)
    for i, r in enumerate(results, 1):
        print(f"    {i}. {r.get('title', 'N/A')[:50]}")
        print(f"       {r.get('url', 'N/A')[:60]}")
    print(f"    ✓ Found {len(results)} results")

    # Test 2: HTTP Request
    print("\n[2] Testing http_request...")
    result = await http_request("https://jsonplaceholder.typicode.com/posts/1")
    print(f"    Status: {result['status_code']}")
    print(f"    Body preview: {result['body'][:100]}...")
    print("    ✓ HTTP request successful")

    # Test 3: Extract Webpage Content
    print("\n[3] Testing extract_webpage_content...")
    result = await extract_webpage_content(
        "https://jsonplaceholder.typicode.com", max_length=300
    )
    print(f"    Title: {result.get('title', 'N/A')}")
    print(f"    Content: {result.get('content', '')[:100]}...")
    print("    ✓ Content extraction successful")

    # Test 4: Fetch JSON
    print("\n[4] Testing fetch_json...")
    result = await fetch_json("https://jsonplaceholder.typicode.com/posts/1")
    print(f"    Title: {result.get('title', 'N/A')}")
    print(f"    Body: {result.get('body', 'N/A')[:50]}...")
    print("    ✓ JSON fetch successful")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_all())

"""
End-to-end test script for Convergence.
Run with: python scripts/test_e2e.py

Tests the full pipeline without needing GitHub webhooks.
"""

import asyncio
import httpx
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000"

# Test with a real public PR that has code changes
# Change these to test with different PRs
TEST_CASES = [
    # Small PR - good for quick tests
    {"owner": "octocat", "repo": "Hello-World", "pr_number": 2846},
    # FastAPI PR - usually has Python code
    # {"owner": "tiangolo", "repo": "fastapi", "pr_number": 11377},
]


async def test_health():
    """Test health endpoint."""
    print("\n🏥 Testing health endpoint...")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        print(f"   ✅ Health: {data}")
    return True


async def test_create_session(owner: str, repo: str, pr_number: int) -> str | None:
    """Create a review session from a PR."""
    print(f"\n📝 Creating session for {owner}/{repo}#{pr_number}...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{BASE_URL}/webhook/test-pr",
            params={"owner": owner, "repo": repo, "pr_number": pr_number}
        )
        
        if r.status_code != 200:
            print(f"   ❌ Failed: {r.status_code} - {r.text}")
            return None
        
        data = r.json()
        
        if data.get("status") == "skipped":
            print(f"   ⚠️ Skipped: {data.get('reason')}")
            return None
        
        session_id = data.get("session_id")
        print(f"   ✅ Session created: {session_id}")
        print(f"   📁 Files: {data.get('files_count')} - {data.get('files', [])[:3]}...")
        return session_id


async def test_run_agents(session_id: str) -> dict | None:
    """Run all agents on a session."""
    print(f"\n🤖 Running agents on session {session_id[:8]}...")
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{BASE_URL}/webhook/sessions/{session_id}/analyze")
        
        if r.status_code != 200:
            print(f"   ❌ Failed: {r.status_code} - {r.text}")
            return None
        
        data = r.json()
        print(f"   ✅ Agents completed: {data.get('agents', [])}")
        print(f"   📊 Findings: {data.get('findings_count', {})}")
        return data


async def test_full_review(session_id: str) -> dict | None:
    """Run full orchestration pipeline."""
    print(f"\n🔄 Running full review pipeline...")
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(
            f"{BASE_URL}/webhook/sessions/{session_id}/review",
            params={"post_to_github": False}
        )
        
        if r.status_code != 200:
            print(f"   ❌ Failed: {r.status_code} - {r.text}")
            return None
        
        data = r.json()
        print(f"   ✅ Review complete!")
        print(f"   ⏱️ Duration: {data.get('duration_ms', 0)}ms")
        print(f"   📊 Total findings: {data.get('findings_count', 0)}")
        print(f"   🚨 Critical: {data.get('critical_count', 0)}")
        return data


async def test_get_findings(session_id: str):
    """Get detailed findings."""
    print(f"\n📋 Fetching findings...")
    
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/webhook/sessions/{session_id}/findings")
        
        if r.status_code != 200:
            print(f"   ❌ Failed: {r.status_code}")
            return
        
        data = r.json()
        
        for agent, info in data.get("findings_by_agent", {}).items():
            findings = info.get("findings", [])
            print(f"\n   [{agent.upper()}] {len(findings)} findings")
            for f in findings[:2]:  # Show first 2
                sev = "🔴" if f.get("severity", 0) >= 4 else "🟡" if f.get("severity", 0) >= 2 else "⚪"
                print(f"      {sev} {f.get('title', 'No title')[:60]}")


async def test_preview_markdown(session_id: str):
    """Preview generated markdown."""
    print(f"\n📄 Preview markdown review...")
    
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/webhook/sessions/{session_id}/review-preview")
        
        if r.status_code != 200:
            print(f"   ❌ No review generated yet")
            return
        
        markdown = r.text
        # Show first 1000 chars
        print("\n" + "="*60)
        print(markdown[:1500])
        if len(markdown) > 1500:
            print(f"\n... [{len(markdown) - 1500} more characters]")
        print("="*60)


async def run_full_test():
    """Run complete E2E test."""
    print("="*60)
    print("🚀 CONVERGENCE E2E TEST")
    print(f"   Time: {datetime.now().isoformat()}")
    print(f"   Server: {BASE_URL}")
    print("="*60)
    
    # Health check
    try:
        await test_health()
    except Exception as e:
        print(f"❌ Server not running? {e}")
        print("\n👉 Start server with: uvicorn app.main:app --reload --port 8000")
        sys.exit(1)
    
    # Test each PR
    for tc in TEST_CASES:
        print("\n" + "="*60)
        print(f"Testing: {tc['owner']}/{tc['repo']}#{tc['pr_number']}")
        print("="*60)
        
        # Create session
        session_id = await test_create_session(
            tc["owner"], tc["repo"], tc["pr_number"]
        )
        
        if not session_id:
            continue
        
        # Run full review
        result = await test_full_review(session_id)
        
        if not result:
            continue
        
        # Show findings
        await test_get_findings(session_id)
        
        # Preview markdown
        await test_preview_markdown(session_id)
    
    print("\n" + "="*60)
    print("✅ E2E TEST COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(run_full_test())
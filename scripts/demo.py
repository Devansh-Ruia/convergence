"""
Interactive demo script for hackathon presentation.
Run with: python scripts/demo.py

This provides a step-by-step demo with pauses for explanation.
"""

import asyncio
import httpx
import sys
import time

BASE_URL = "http://localhost:8000"

# Configure your demo PR here
DEMO_PR = {
    "owner": "your-username",
    "repo": "your-test-repo",
    "pr_number": 1
}


def pause(message: str = "Press Enter to continue..."):
    """Pause for presenter."""
    input(f"\n⏸️  {message}")


def header(text: str):
    """Print section header."""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60 + "\n")


async def demo():
    """Run interactive demo."""
    
    header("🎯 CONVERGENCE - Multi-Agent PR Review System")
    print("Welcome to Convergence!")
    print("This demo shows how multiple AI agents collaborate to review code.\n")
    pause()
    
    # Step 1: Health Check
    header("Step 1: Verify System Health")
    print("First, let's verify the system is running...")
    
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/health")
        print(f"Response: {r.json()}")
    
    pause()
    
    # Step 2: Create Session
    header("Step 2: Create Review Session")
    print(f"Creating a review session for PR #{DEMO_PR['pr_number']}...")
    print(f"Repository: {DEMO_PR['owner']}/{DEMO_PR['repo']}\n")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{BASE_URL}/webhook/test-pr",
            params=DEMO_PR
        )
        data = r.json()
        session_id = data.get("session_id")
        
        print(f"✅ Session ID: {session_id}")
        print(f"📁 Files to review: {data.get('files_count')}")
        for f in data.get("files", [])[:5]:
            print(f"   - {f}")
    
    pause()
    
    # Step 3: Run Agents
    header("Step 3: Dispatch AI Agents")
    print("Now we dispatch 3 specialized agents in PARALLEL:")
    print("  🔒 Security Agent  - Finds vulnerabilities")
    print("  ⚡ Performance Agent - Identifies bottlenecks")
    print("  🧪 Testing Agent - Spots coverage gaps\n")
    print("Watch them work...")
    
    pause("Press Enter to start agents...")
    
    start = time.time()
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{BASE_URL}/webhook/sessions/{session_id}/analyze")
        data = r.json()
        
        elapsed = time.time() - start
        print(f"\n⏱️ Completed in {elapsed:.1f} seconds")
        print("\nFindings per agent:")
        for agent, count in data.get("findings_count", {}).items():
            emoji = {"security": "🔒", "performance": "⚡", "testing": "🧪"}.get(agent, "📋")
            print(f"  {emoji} {agent.title()}: {count} findings")
    
    pause()
    
    # Step 4: Show Raw Findings
    header("Step 4: Examine Agent Findings")
    print("Let's look at what each agent found...\n")
    
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/webhook/sessions/{session_id}/findings")
        data = r.json()
        
        for agent, info in data.get("findings_by_agent", {}).items():
            findings = info.get("findings", [])
            emoji = {"security": "🔒", "performance": "⚡", "testing": "🧪"}.get(agent, "📋")
            
            print(f"\n{emoji} {agent.upper()} AGENT ({len(findings)} findings)")
            print("-" * 40)
            
            for f in findings[:2]:
                sev = f.get("severity", 0)
                sev_icon = "🔴" if sev >= 4 else "🟠" if sev >= 3 else "🟡"
                print(f"\n{sev_icon} [{f.get('category', 'issue')}] {f.get('title', 'Issue')}")
                print(f"   📁 {f.get('file_path')}:{f.get('line_start')}")
                desc = f.get('description', '')[:100]
                print(f"   {desc}...")
    
    pause()
    
    # Step 5: Convergence
    header("Step 5: CONVERGENCE - Merge & Synthesize")
    print("Now the magic happens! 🪄")
    print("\nConvergence will:")
    print("  1. Group findings by code location")
    print("  2. Boost severity when multiple agents agree")
    print("  3. Deduplicate similar issues")
    print("  4. Generate a unified review\n")
    
    pause("Press Enter to run convergence...")
    
    start = time.time()
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{BASE_URL}/webhook/sessions/{session_id}/review",
            params={"post_to_github": False}
        )
        data = r.json()
        
        elapsed = time.time() - start
        print(f"\n✅ Convergence complete in {elapsed:.1f}s")
        print(f"\n📊 RESULTS:")
        print(f"   Total findings: {data.get('findings_count')}")
        print(f"   Critical issues: {data.get('critical_count')}")
        print(f"   Agents used: {', '.join(data.get('agents_completed', []))}")
    
    pause()
    
    # Step 6: Show Final Review
    header("Step 6: Generated Review")
    print("Here's the final review that would be posted to GitHub:\n")
    
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/webhook/sessions/{session_id}/review-preview")
        markdown = r.text
        print(markdown[:2000])
        if len(markdown) > 2000:
            print(f"\n... [truncated, {len(markdown)} total chars]")
    
    pause()
    
    # Step 7: Post to GitHub (optional)
    header("Step 7: Post to GitHub (Optional)")
    print("Ready to post this review to GitHub?")
    print(f"PR: https://github.com/{DEMO_PR['owner']}/{DEMO_PR['repo']}/pull/{DEMO_PR['pr_number']}\n")
    
    response = input("Post to GitHub? (yes/no): ").strip().lower()
    
    if response == "yes":
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{BASE_URL}/webhook/sessions/{session_id}/post-review")
            data = r.json()
            print(f"\n✅ Posted! Review ID: {data.get('github_review_id')}")
            print(f"🔗 View at: {data.get('pr_url')}")
    else:
        print("\n⏭️ Skipped posting.")
    
    # Done
    header("🎉 DEMO COMPLETE")
    print("Convergence successfully demonstrated:")
    print("  ✅ Multi-agent parallel analysis")
    print("  ✅ Cross-agent finding correlation")
    print("  ✅ Severity boosting on agreement")
    print("  ✅ Unified review synthesis")
    print("  ✅ GitHub integration\n")
    print("Thank you! 🙏\n")


if __name__ == "__main__":
    print("\n🎬 Starting Convergence Demo...")
    print("Make sure the server is running on localhost:8000\n")
    
    try:
        asyncio.run(demo())
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted. Goodbye!")
    except httpx.ConnectError:
        print("\n❌ Cannot connect to server!")
        print("👉 Start with: uvicorn app.main:app --reload --port 8000")
import time
import logging
from datetime import datetime
from bson import ObjectId

from app.integrations.mongodb import get_db
from app.integrations import github
from app.models.session import ReviewSession, GitHubContext, FileChange
from app.agents import run_all_agents
from app.orchestrator.convergence import merge_overlapping_findings, synthesize_markdown

logger = logging.getLogger(__name__)


async def orchestrate_review(
    session_id: str | None = None,
    payload: dict | None = None,
    post_to_github: bool = True
) -> dict:
    """
    Main orchestration function.
    
    Either provide:
    - session_id: to process an existing session
    - payload: GitHub webhook payload to create new session
    
    Returns dict with review results.
    """
    db = get_db()
    start_time = time.time()
    
    # ─────────────────────────────────────────────────────────
    # STEP 1: Get or Create Session
    # ─────────────────────────────────────────────────────────
    
    if session_id:
        # Load existing session
        session_doc = await db.review_sessions.find_one({"_id": ObjectId(session_id)})
        if not session_doc:
            raise ValueError(f"Session not found: {session_id}")
        logger.info(f"Loaded existing session: {session_id}")
    
    elif payload:
        # Create new session from webhook payload
        session_id = await create_session_from_payload(payload)
        session_doc = await db.review_sessions.find_one({"_id": ObjectId(session_id)})
        logger.info(f"Created new session: {session_id}")
    
    else:
        raise ValueError("Must provide either session_id or payload")
    
    # Extract session data
    github_ctx = session_doc["github"]
    files = [FileChange(**f) for f in session_doc.get("files", [])]
    
    if not files:
        logger.warning(f"Session {session_id} has no files to review")
        await db.review_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"status": "complete", "error": "No reviewable files"}}
        )
        return {"status": "skipped", "reason": "No reviewable files"}
    
    # ─────────────────────────────────────────────────────────
    # STEP 2: Run All Agents in Parallel
    # ─────────────────────────────────────────────────────────
    
    logger.info(f"Starting agent analysis for session {session_id}")
    
    agent_results = await run_all_agents(
        session_id=session_id,
        repo_owner=github_ctx["repo_owner"],
        repo_name=github_ctx["repo_name"],
        pr_title=github_ctx["pr_title"],
        files=files
    )
    
    agents_completed = list(agent_results.keys())
    
    # ─────────────────────────────────────────────────────────
    # STEP 3: Update Status to Converging
    # ─────────────────────────────────────────────────────────
    
    await db.review_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {
            "$set": {
                "status": "converging",
                "agents_completed": agents_completed,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    # ─────────────────────────────────────────────────────────
    # STEP 4: Convergence - Merge & Deduplicate Findings
    # ─────────────────────────────────────────────────────────
    
    logger.info(f"Running convergence pass for session {session_id}")
    
    # Collect findings from each agent
    findings_by_agent = {}
    for agent_type, result in agent_results.items():
        findings_by_agent[agent_type] = result.get("findings", [])
    
    # Merge overlapping findings
    merged_findings = merge_overlapping_findings(findings_by_agent)
    
    # ─────────────────────────────────────────────────────────
    # STEP 5: Synthesize Final Review Markdown
    # ─────────────────────────────────────────────────────────
    
    duration_ms = int((time.time() - start_time) * 1000)
    
    review_markdown = synthesize_markdown(
        pr_title=github_ctx["pr_title"],
        pr_url=github_ctx["pr_url"],
        findings=merged_findings,
        agents_completed=agents_completed,
        duration_ms=duration_ms
    )
    
    # ─────────────────────────────────────────────────────────
    # STEP 6: Post to GitHub (Optional)
    # ─────────────────────────────────────────────────────────
    
    github_review_id = None
    
    if post_to_github:
        try:
            # Determine review event type
            critical_count = len([f for f in merged_findings if f.get("severity", 0) >= 4])
            event = "REQUEST_CHANGES" if critical_count > 0 else "COMMENT"
            
            github_review_id = await github.post_pr_review(
                owner=github_ctx["repo_owner"],
                repo=github_ctx["repo_name"],
                pr_number=github_ctx["pr_number"],
                body=review_markdown,
                event=event
            )
            logger.info(f"Posted review {github_review_id} to GitHub")
        except Exception as e:
            logger.error(f"Failed to post review to GitHub: {e}")
            # Continue - we still want to save the review locally
    
    # ─────────────────────────────────────────────────────────
    # STEP 7: Save Final Review to MongoDB
    # ─────────────────────────────────────────────────────────
    
    critical_count = len([f for f in merged_findings if f.get("severity", 0) >= 4])
    
    final_review = {
        "summary": review_markdown,
        "findings_count": len(merged_findings),
        "critical_count": critical_count,
        "posted_at": datetime.utcnow(),
        "github_review_id": github_review_id,
        "duration_ms": duration_ms
    }
    
    await db.review_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {
            "$set": {
                "status": "complete",
                "final_review": final_review,
                "completed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    logger.info(f"Review complete for session {session_id}: {len(merged_findings)} findings in {duration_ms}ms")
    
    return {
        "status": "complete",
        "session_id": session_id,
        "findings_count": len(merged_findings),
        "critical_count": critical_count,
        "agents_completed": agents_completed,
        "duration_ms": duration_ms,
        "github_review_id": github_review_id,
        "review_markdown": review_markdown
    }


async def create_session_from_payload(payload: dict) -> str:
    """Create a new review session from GitHub webhook payload."""
    db = get_db()
    pr = payload["pull_request"]
    repo = payload["repository"]
    
    github_ctx = GitHubContext(
        repo_owner=repo["owner"]["login"],
        repo_name=repo["name"],
        pr_number=pr["number"],
        pr_title=pr["title"],
        pr_url=pr["html_url"],
        head_sha=pr["head"]["sha"],
        author=pr["user"]["login"]
    )
    
    # Check for existing session
    existing = await db.review_sessions.find_one({
        "github.repo_owner": github_ctx.repo_owner,
        "github.repo_name": github_ctx.repo_name,
        "github.pr_number": github_ctx.pr_number,
        "github.head_sha": github_ctx.head_sha
    })
    
    if existing:
        return str(existing["_id"])
    
    # Fetch files
    files = await github.get_pr_files(
        owner=github_ctx.repo_owner,
        repo=github_ctx.repo_name,
        pr_number=github_ctx.pr_number
    )
    
    session = ReviewSession(
        github=github_ctx,
        files=files,
        status="pending"
    )
    
    result = await db.review_sessions.insert_one(session.model_dump())
    return str(result.inserted_id)
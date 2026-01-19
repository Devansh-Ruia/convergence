from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
from bson import ObjectId
from app.config import settings
from app.models.session import ReviewSession, GitHubContext, FileChange
from app.integrations.mongodb import get_db
from app.integrations import github
from app.agents import run_all_agents
from app.orchestrator import orchestrate_review
from datetime import datetime
import hmac
import hashlib
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_signature(body: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    if not settings.github_webhook_secret:
        logger.warning("No webhook secret configured, skipping verification")
        return True

    if not signature:
        return False

    expected = (
        "sha256="
        + hmac.new(
            settings.github_webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
    )

    return hmac.compare_digest(signature, expected)


@router.post("/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle GitHub webhook events."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event_type = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(body)

    logger.info(f"Received GitHub event: {event_type}")

    if event_type == "pull_request":
        action = payload.get("action", "")
        pr_number = payload.get("pull_request", {}).get("number")

        if action in ["opened", "synchronize", "reopened"]:
            logger.info(f"Processing PR #{pr_number} (action: {action})")

            # Run full orchestration in background
            background_tasks.add_task(
                orchestrate_review,
                session_id=None,
                payload=payload,
                post_to_github=True,
            )

            return {
                "status": "processing",
                "event": event_type,
                "action": action,
                "pr_number": pr_number,
            }

    return {"status": "ignored", "event": event_type}


@router.post("/test-pr")
async def test_pr_review(owner: str, repo: str, pr_number: int):
    """
    Test endpoint to create a session from a PR.
    Usage: POST /webhook/test-pr?owner=acme&repo=backend&pr_number=123
    """
    db = get_db()

    pr_data = await github.get_pr_details(owner, repo, pr_number)
    files = await github.get_pr_files(owner, repo, pr_number)

    if not files:
        return {"status": "skipped", "reason": "No reviewable files found"}

    github_ctx = GitHubContext(
        repo_owner=owner,
        repo_name=repo,
        pr_number=pr_number,
        pr_title=pr_data["title"],
        pr_url=pr_data["html_url"],
        head_sha=pr_data["head"]["sha"],
        author=pr_data["user"]["login"],
    )

    session = ReviewSession(github=github_ctx, files=files, status="pending")
    result = await db.review_sessions.insert_one(session.model_dump())
    session_id = str(result.inserted_id)

    return {
        "status": "created",
        "session_id": session_id,
        "pr_title": github_ctx.pr_title,
        "files_count": len(files),
        "files": [f.path for f in files],
    }


@router.post("/sessions/{session_id}/analyze")
async def analyze_session(session_id: str):
    """Run all agents on a session (without GitHub posting)."""
    db = get_db()

    try:
        session = await db.review_sessions.find_one({"_id": ObjectId(session_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID format")

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.get("status") in ["analyzing", "converging", "complete"]:
        return {
            "status": "already_processing",
            "session_id": session_id,
            "current_status": session.get("status"),
        }

    files = [FileChange(**f) for f in session.get("files", [])]

    if not files:
        return {"status": "skipped", "reason": "No files to analyze"}

    results = await run_all_agents(
        session_id=session_id,
        repo_owner=session["github"]["repo_owner"],
        repo_name=session["github"]["repo_name"],
        pr_title=session["github"]["pr_title"],
        files=files,
    )

    total_findings = sum(len(data.get("findings", [])) for data in results.values())

    return {
        "status": "completed",
        "session_id": session_id,
        "agents": list(results.keys()),
        "findings_count": {
            agent: len(data.get("findings", [])) for agent, data in results.items()
        },
        "total_findings": total_findings,
    }


@router.post("/sessions/{session_id}/review")
async def run_full_review(session_id: str, post_to_github: bool = False, template: str = "default"):
    """
    Run the FULL orchestration pipeline on a session.
    - Runs all agents
    - Merges/deduplicates findings
    - Generates markdown review
    - Optionally posts to GitHub

    Usage: POST /webhook/sessions/{id}/review?post_to_github=true&template=checklist
    """
    try:
        result = await orchestrate_review(
            session_id=session_id, post_to_github=post_to_github, template=template
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/review-preview")
async def preview_review(session_id: str):
    """
    Get the generated review markdown without posting to GitHub.
    Useful for previewing before posting.
    """
    db = get_db()

    try:
        session = await db.review_sessions.find_one({"_id": ObjectId(session_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    final_review = session.get("final_review")
    if not final_review:
        raise HTTPException(
            status_code=400, detail="Review not yet generated. Run /review first."
        )

    return PlainTextResponse(
        content=final_review.get("summary", ""), media_type="text/markdown"
    )


@router.post("/sessions/{session_id}/post-review")
async def post_existing_review(session_id: str):
    """
    Post an already-generated review to GitHub.
    Use this after previewing with /review-preview.
    """
    db = get_db()

    try:
        session = await db.review_sessions.find_one({"_id": ObjectId(session_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    final_review = session.get("final_review")
    if not final_review:
        raise HTTPException(status_code=400, detail="Review not generated yet")

    if final_review.get("github_review_id"):
        return {
            "status": "already_posted",
            "github_review_id": final_review["github_review_id"],
        }

    # Post to GitHub
    review_markdown = final_review.get("summary", "")
    critical_count = final_review.get("critical_count", 0)
    event = "REQUEST_CHANGES" if critical_count > 0 else "COMMENT"

    github_ctx = session["github"]
    github_review_id = await github.post_pr_review(
        owner=github_ctx["repo_owner"],
        repo=github_ctx["repo_name"],
        pr_number=github_ctx["pr_number"],
        body=review_markdown,
        event=event,
    )

    # Update session
    await db.review_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"final_review.github_review_id": github_review_id}},
    )

    return {
        "status": "posted",
        "github_review_id": github_review_id,
        "pr_url": github_ctx["pr_url"],
    }


@router.get("/sessions/{session_id}/findings")
async def get_session_findings(session_id: str):
    """Get all agent findings for a session."""
    db = get_db()

    try:
        oid = ObjectId(session_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await db.review_sessions.find_one({"_id": oid})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    cursor = db.agent_findings.find({"session_id": oid})
    findings_docs = await cursor.to_list(length=10)

    findings_by_agent = {}
    for doc in findings_docs:
        agent_type = doc["agent_type"]
        findings_by_agent[agent_type] = {
            "findings": doc.get("findings", []),
            "summary": doc.get("summary", ""),
            "latency_ms": doc.get("latency_ms", 0),
        }

    return {
        "session_id": session_id,
        "status": session.get("status"),
        "pr_title": session["github"]["pr_title"],
        "agents_completed": session.get("agents_completed", []),
        "findings_by_agent": findings_by_agent,
    }


@router.get("/sessions")
async def list_sessions(limit: int = 10):
    """List recent review sessions."""
    db = get_db()

    try:
        cursor = db.review_sessions.find().sort("created_at", -1).limit(limit)
        sessions = await cursor.to_list(length=limit)

        result = []
        for s in sessions:
            try:
                github_data = s.get("github", {})
                result.append(
                    {
                        "_id": str(s["_id"]),
                        "pr_title": github_data.get("pr_title", "Unknown PR"),
                        "pr_number": github_data.get("pr_number", 0),
                        "repo": f"{github_data.get('repo_owner', 'unknown')}/{github_data.get('repo_name', 'unknown')}",
                        "status": s.get("status", "unknown"),
                        "files_count": len(s.get("files", [])),
                        "agents_completed": s.get("agents_completed", []),
                        "findings_count": s.get("final_review", {}).get(
                            "findings_count", 0
                        ),
                        "created_at": s.get("created_at"),
                    }
                )
            except Exception as e:
                logger.error(f"Error processing session {s.get('_id')}: {e}")
                continue

        return {"sessions": result}
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing sessions: {str(e)}")


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get full session details."""
    db = get_db()

    try:
        session = await db.review_sessions.find_one({"_id": ObjectId(session_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session["_id"] = str(session["_id"])
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and its findings."""
    db = get_db()

    try:
        oid = ObjectId(session_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    # Delete findings
    await db.agent_findings.delete_many({"session_id": oid})

    # Delete session
    result = await db.review_sessions.delete_one({"_id": oid})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"status": "deleted", "session_id": session_id}

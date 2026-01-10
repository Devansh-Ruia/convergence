from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from app.config import settings
from app.models.session import ReviewSession, GitHubContext, FileChange
from app.integrations.mongodb import get_db
from app.integrations import github
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
    
    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)


async def process_pr_event(payload: dict) -> str:
    """
    Process a PR event and create a review session.
    Returns the session ID.
    """
    db = get_db()
    pr = payload["pull_request"]
    repo = payload["repository"]
    
    # Create GitHub context
    github_ctx = GitHubContext(
        repo_owner=repo["owner"]["login"],
        repo_name=repo["name"],
        pr_number=pr["number"],
        pr_title=pr["title"],
        pr_url=pr["html_url"],
        head_sha=pr["head"]["sha"],
        author=pr["user"]["login"]
    )
    
    # Check if session already exists for this PR
    existing = await db.review_sessions.find_one({
        "github.repo_owner": github_ctx.repo_owner,
        "github.repo_name": github_ctx.repo_name,
        "github.pr_number": github_ctx.pr_number,
        "github.head_sha": github_ctx.head_sha
    })
    
    if existing:
        logger.info(f"Session already exists for PR #{github_ctx.pr_number} @ {github_ctx.head_sha}")
        return str(existing["_id"])
    
    # Fetch PR files
    files = await github.get_pr_files(
        owner=github_ctx.repo_owner,
        repo=github_ctx.repo_name,
        pr_number=github_ctx.pr_number
    )
    
    # Create session
    session = ReviewSession(
        github=github_ctx,
        files=files,
        status="pending"
    )
    
    result = await db.review_sessions.insert_one(session.model_dump())
    session_id = str(result.inserted_id)
    
    logger.info(f"Created session {session_id} for PR #{github_ctx.pr_number}")
    return session_id


@router.post("/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle GitHub webhook events."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    
    # Verify signature
    if not verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    event_type = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(body)
    
    logger.info(f"Received GitHub event: {event_type}")
    
    # Handle PR events
    if event_type == "pull_request":
        action = payload.get("action", "")
        pr_number = payload.get("pull_request", {}).get("number")
        
        if action in ["opened", "synchronize", "reopened"]:
            logger.info(f"Processing PR #{pr_number} (action: {action})")
            
            # Process synchronously for now (will move to background later)
            session_id = await process_pr_event(payload)
            
            return {
                "status": "processing",
                "event": event_type,
                "action": action,
                "pr_number": pr_number,
                "session_id": session_id
            }
        else:
            logger.debug(f"Ignoring PR action: {action}")
    
    return {
        "status": "ignored",
        "event": event_type
    }


@router.post("/test-pr")
async def test_pr_review(owner: str, repo: str, pr_number: int):
    """
    Test endpoint to manually trigger a PR review.
    Usage: POST /webhook/test-pr?owner=acme&repo=backend&pr_number=123
    """
    db = get_db()
    
    # Fetch PR details
    pr_data = await github.get_pr_details(owner, repo, pr_number)
    
    # Fetch files
    files = await github.get_pr_files(owner, repo, pr_number)
    
    if not files:
        return {
            "status": "skipped",
            "reason": "No reviewable files found"
        }
    
    # Create session
    github_ctx = GitHubContext(
        repo_owner=owner,
        repo_name=repo,
        pr_number=pr_number,
        pr_title=pr_data["title"],
        pr_url=pr_data["html_url"],
        head_sha=pr_data["head"]["sha"],
        author=pr_data["user"]["login"]
    )
    
    session = ReviewSession(
        github=github_ctx,
        files=files,
        status="pending"
    )
    
    result = await db.review_sessions.insert_one(session.model_dump())
    session_id = str(result.inserted_id)
    
    return {
        "status": "created",
        "session_id": session_id,
        "pr_title": github_ctx.pr_title,
        "files_count": len(files),
        "files": [f.path for f in files]
    }


@router.get("/sessions")
async def list_sessions(limit: int = 10):
    """List recent review sessions."""
    db = get_db()
    
    cursor = db.review_sessions.find().sort("created_at", -1).limit(limit)
    sessions = await cursor.to_list(length=limit)
    
    # Convert ObjectId to string
    for s in sessions:
        s["_id"] = str(s["_id"])
    
    return {"sessions": sessions}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific session by ID."""
    from bson import ObjectId
    
    db = get_db()
    session = await db.review_sessions.find_one({"_id": ObjectId(session_id)})
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session["_id"] = str(session["_id"])
    return session
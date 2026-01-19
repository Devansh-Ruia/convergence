import json
import asyncio
import logging
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from bson import ObjectId

from app.integrations.mongodb import get_db
from app.metrics import get_metrics_summary, get_agent_performance

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/sessions/{session_id}/stream")
async def stream_session_updates(session_id: str):
    """
    Stream real-time updates for a session:
    - agent_started: {agent: "security"}
    - agent_completed: {agent: "security", findings_count: 3}
    - cross_reference: {source: "testing", target: "sec-001"}
    - convergence_started: {}
    - review_complete: {findings_count: 8}
    """
    try:
        # Validate session exists
        db = get_db()
        session_doc = await db.review_sessions.find_one({"_id": ObjectId(session_id)})
        if not session_doc:
            raise HTTPException(status_code=404, detail="Session not found")
        
        async def event_generator():
            """Generate SSE events for session updates."""
            # Track what we've already sent to avoid duplicates
            sent_agents = set()
            sent_cross_refs = set()
            convergence_started = False
            review_complete = False
            
            while True:
                try:
                    # Get current session state
                    current_session = await db.review_sessions.find_one(
                        {"_id": ObjectId(session_id)}
                    )
                    
                    if not current_session:
                        yield {
                            "event": "error",
                            "data": json.dumps({"error": "Session not found"})
                        }
                        break
                    
                    status = current_session.get("status", "pending")
                    
                    # Check for agent completions
                    agents_completed = current_session.get("agents_completed", [])
                    for agent in agents_completed:
                        if agent not in sent_agents:
                            # Get agent findings count
                            agent_doc = await db.agent_findings.find_one({
                                "session_id": ObjectId(session_id),
                                "agent_type": agent
                            })
                            
                            findings_count = len(agent_doc.get("findings", [])) if agent_doc else 0
                            latency_ms = agent_doc.get("latency_ms", 0) if agent_doc else 0
                            
                            yield {
                                "event": "agent_completed",
                                "data": json.dumps({
                                    "agent": agent,
                                    "findings_count": findings_count,
                                    "latency_ms": latency_ms
                                })
                            }
                            sent_agents.add(agent)
                    
                    # Check for cross-references
                    if status in ["converging", "complete"]:
                        cross_refs_cursor = await db.agent_cross_references.find({
                            "session_id": ObjectId(session_id)
                        }).to_list(length=None)
                        
                        for cross_ref in cross_refs_cursor:
                            cross_ref_id = str(cross_ref["_id"])
                            if cross_ref_id not in sent_cross_refs:
                                yield {
                                    "event": "cross_reference",
                                    "data": json.dumps({
                                        "source": cross_ref["source_agent"],
                                        "target": cross_ref["target_finding_id"],
                                        "relationship": cross_ref["relationship"],
                                        "comment": cross_ref["comment"][:100] + "..." if len(cross_ref["comment"]) > 100 else cross_ref["comment"]
                                    })
                                }
                                sent_cross_refs.add(cross_ref_id)
                    
                    # Check for convergence start
                    if status == "converging" and not convergence_started:
                        yield {
                            "event": "convergence_started",
                            "data": json.dumps({})
                        }
                        convergence_started = True
                    
                    # Check for review completion
                    if status == "complete" and not review_complete:
                        final_review = current_session.get("final_review", {})
                        yield {
                            "event": "review_complete",
                            "data": json.dumps({
                                "findings_count": final_review.get("findings_count", 0),
                                "critical_count": final_review.get("critical_count", 0),
                                "duration_ms": final_review.get("duration_ms", 0),
                                "github_review_id": final_review.get("github_review_id")
                            })
                        }
                        review_complete = True
                        
                        # Send final event and close
                        yield {
                            "event": "stream_complete",
                            "data": json.dumps({"message": "Review complete"})
                        }
                        break
                    
                    # If session is in error state
                    if status == "error":
                        yield {
                            "event": "error", 
                            "data": json.dumps({
                                "error": current_session.get("error", "Unknown error")
                            })
                        }
                        break
                    
                    # Send heartbeat every 10 seconds
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps({"timestamp": asyncio.get_event_loop().time()})
                    }
                    
                    # Wait before next check
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Error in event generator: {e}")
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": str(e)})
                    }
                    break
        
        return EventSourceResponse(event_generator())
        
    except Exception as e:
        logger.error(f"Error setting up SSE stream: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions/{session_id}/status")
async def get_session_status(session_id: str):
    """Get current session status without streaming."""
    try:
        db = get_db()
        session_doc = await db.review_sessions.find_one({"_id": ObjectId(session_id)})
        
        if not session_doc:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get agent statuses
        agents_completed = session_doc.get("agents_completed", [])
        agent_statuses = {}
        
        for agent in ["security", "performance", "testing", "architecture", "documentation"]:
            agent_doc = await db.agent_findings.find_one({
                "session_id": ObjectId(session_id),
                "agent_type": agent
            })
            
            if agent_doc:
                agent_statuses[agent] = {
                    "status": "completed",
                    "findings_count": len(agent_doc.get("findings", [])),
                    "latency_ms": agent_doc.get("latency_ms", 0)
                }
            elif agent in agents_completed:
                agent_statuses[agent] = {"status": "completed", "findings_count": 0}
            else:
                agent_statuses[agent] = {"status": "pending"}
        
        # Get cross-reference count
        cross_refs_count = await db.agent_cross_references.count_documents({
            "session_id": ObjectId(session_id)
        })
        
        return {
            "session_id": session_id,
            "status": session_doc.get("status", "pending"),
            "agents": agent_statuses,
            "cross_references_count": cross_refs_count,
            "final_review": session_doc.get("final_review"),
            "created_at": session_doc.get("created_at"),
            "updated_at": session_doc.get("updated_at")
        }
        
    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/metrics/summary")
async def get_metrics_summary_endpoint(hours: int = 24):
    """Get aggregated metrics for demo dashboard."""
    try:
        summary = await get_metrics_summary(hours)
        performance = await get_agent_performance(hours)
        
        return {
            "summary": summary,
            "agent_performance": performance,
            "hours": hours
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

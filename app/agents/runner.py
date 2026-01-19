import json
import time
import asyncio
import logging
from datetime import datetime
from bson import ObjectId

from app.integrations.gemini import get_model
from app.integrations.mongodb import get_db
from app.models.session import FileChange
from app.models.findings import Finding, AgentFindings
from app.agents.base import BaseAgent
from app.agents.security import SecurityAgent
from app.agents.performance import PerformanceAgent
from app.agents.testing import TestingAgent
from app.agents.architecture import ArchitectureAgent
from app.agents.documentation import DocumentationAgent

logger = logging.getLogger(__name__)

AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "security": SecurityAgent,
    "performance": PerformanceAgent,
    "testing": TestingAgent,
    "architecture": ArchitectureAgent,
    "documentation": DocumentationAgent
}


def parse_json_response(text: str) -> dict:
    """Parse JSON from model response, handling common issues."""
    # Remove markdown code blocks if present
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    return json.loads(text)


async def run_agent(
    agent_type: str,
    session_id: str,
    repo_owner: str,
    repo_name: str,
    pr_title: str,
    files: list[FileChange]
) -> dict:
    """
    Run a single agent and store results in MongoDB.
    
    Returns the parsed findings dict.
    """
    db = get_db()
    model = get_model()
    
    if agent_type not in AGENT_CLASSES:
        raise ValueError(f"Unknown agent type: {agent_type}")
    
    agent = AGENT_CLASSES[agent_type]()
    start_time = time.time()
    
    logger.info(f"[{agent_type}] Starting analysis for session {session_id}")
    
    # Build prompts
    system_prompt = agent.system_prompt
    user_prompt = agent.build_user_prompt(repo_owner, repo_name, pr_title, files)
    
    # Call Gemini
    try:
        response = await asyncio.to_thread(
            model.generate_content,
            [
                {"role": "user", "parts": [f"System instructions: {system_prompt}\n\n{user_prompt}"]}
            ],
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 4096,
            }
        )
        
        response_text = response.text
        
        # Parse response
        findings_data = parse_json_response(response_text)
        
    except json.JSONDecodeError as e:
        logger.error(f"[{agent_type}] Failed to parse JSON response: {e}")
        logger.error(f"[{agent_type}] Raw response: {response_text[:500]}")
        findings_data = {"findings": [], "summary": f"Error parsing response: {e}"}
    except Exception as e:
        logger.error(f"[{agent_type}] Error calling Gemini: {e}")
        findings_data = {"findings": [], "summary": f"Error: {e}"}
    
    # Ensure findings have IDs
    findings_list = findings_data.get("findings", [])
    for i, finding in enumerate(findings_list):
        if "id" not in finding:
            finding["id"] = f"{agent_type[:3]}-{i+1:03d}"
        # Ensure line_end exists
        if "line_end" not in finding:
            finding["line_end"] = finding.get("line_start", 0)
    
    latency_ms = int((time.time() - start_time) * 1000)
    
    # Build document for MongoDB
    agent_findings_doc = {
        "session_id": ObjectId(session_id),
        "agent_type": agent_type,
        "findings": findings_list,
        "summary": findings_data.get("summary", ""),
        "model_used": "gemini-1.5-flash",
        "latency_ms": latency_ms,
        "created_at": datetime.utcnow()
    }
    
    # Upsert to MongoDB (replace if exists for same session+agent)
    await db.agent_findings.update_one(
        {"session_id": ObjectId(session_id), "agent_type": agent_type},
        {"$set": agent_findings_doc},
        upsert=True
    )
    
    # Update session progress
    await db.review_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {
            "$addToSet": {"agents_completed": agent_type},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    
    logger.info(f"[{agent_type}] Completed in {latency_ms}ms, found {len(findings_list)} issues")
    
    return findings_data


async def run_all_agents(
    session_id: str,
    repo_owner: str,
    repo_name: str,
    pr_title: str,
    files: list[FileChange],
    agent_types: list[str] | None = None
) -> dict[str, dict]:
    """
    Run all specified agents in parallel.
    
    Returns dict mapping agent_type -> findings_data
    """
    if agent_types is None:
        agent_types = list(AGENT_CLASSES.keys())
    
    db = get_db()
    
    # Mark agents as dispatched
    await db.review_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {
            "$set": {
                "status": "analyzing",
                "agents_dispatched": agent_types,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    logger.info(f"Dispatching {len(agent_types)} agents for session {session_id}")
    
    # Run all agents in parallel
    tasks = [
        run_agent(agent_type, session_id, repo_owner, repo_name, pr_title, files)
        for agent_type in agent_types
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Collect results
    agent_results = {}
    for agent_type, result in zip(agent_types, results):
        if isinstance(result, Exception):
            logger.error(f"Agent {agent_type} failed: {result}")
            agent_results[agent_type] = {"findings": [], "summary": f"Error: {result}"}
        else:
            agent_results[agent_type] = result
    
    return agent_results
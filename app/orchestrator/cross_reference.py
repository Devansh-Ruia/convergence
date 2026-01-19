import json
import logging
from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Any

from app.integrations.gemini import get_model
from app.integrations.mongodb import get_db
from app.agents.runner import AGENT_CLASSES

logger = logging.getLogger(__name__)


async def run_cross_reference_round(session_id: str) -> Dict[str, Any]:
    """
    After initial analysis, agents review each other's findings
    and can add cross-references or reinforcements.
    
    Returns summary of cross-references created.
    """
    db = get_db()
    model = get_model()
    
    # Get all agent findings for this session
    agent_findings_cursor = await db.agent_findings.find({
        "session_id": ObjectId(session_id)
    }).to_list(length=None)
    
    if len(agent_findings_cursor) < 2:
        logger.info(f"Session {session_id}: Not enough agents for cross-reference")
        return {"cross_references": [], "summary": "Not enough agents for cross-reference"}
    
    # Build summary of all findings for each agent to review
    all_findings = {}
    for agent_doc in agent_findings_cursor:
        agent_type = agent_doc["agent_type"]
        findings = agent_doc.get("findings", [])
        all_findings[agent_type] = findings
    
    cross_references = []
    
    # Have each agent review findings from other agents
    for agent_doc in agent_findings_cursor:
        source_agent = agent_doc["agent_type"]
        source_findings = agent_doc.get("findings", [])
        
        # Build summary of other agents' findings
        other_agents_summary = []
        for other_agent, other_findings in all_findings.items():
            if other_agent == source_agent:
                continue
                
            summary = f"## {other_agent.title()} Agent Findings:\n"
            for finding in other_findings:
                summary += f"- **{finding['title']}** ({finding['severity']}/5) in {finding['file_path']}:{finding['line_start']}\n"
                summary += f"  Category: {finding['category']}\n"
                summary += f"  Description: {finding['description'][:200]}...\n"
                if finding.get('confidence'):
                    summary += f"  Confidence: {finding['confidence']}\n"
                summary += f"  ID: {finding['id']}\n\n"
            
            other_agents_summary.append(summary)
        
        if not other_agents_summary:
            continue
        
        # Get agent instance
        if source_agent not in AGENT_CLASSES:
            logger.warning(f"Unknown agent type: {source_agent}")
            continue
            
        agent = AGENT_CLASSES[source_agent]()
        
        # Build cross-reference prompt
        cross_ref_prompt = f"""You are a {source_agent} expert reviewing findings from other agents in this code review.

Your task: Review the findings below and provide cross-references when you can:
- **reinforce**: You agree with this finding and can add supporting evidence
- **extend**: You can add additional context or related concerns to this finding  
- **conflict**: You disagree with this finding based on your expertise

Findings from other agents:
{chr(10).join(other_agents_summary)}

Respond with JSON:
{{
  "cross_references": [
    {{
      "target_finding_id": "sec-001",
      "relationship": "reinforce|extend|conflict",
      "comment": "Detailed explanation of your position",
      "confidence": 0.9
    }}
  ]
}}

Guidelines:
- Only provide cross-references for findings you can meaningfully contribute to
- Be specific and provide technical reasoning
- confidence: 0.0-1.0 how confident you are in this cross-reference
- Return empty array if you don't have meaningful contributions
- Return ONLY valid JSON, no markdown"""

        try:
            # Call Gemini for cross-reference analysis
            response = await model.generate_content_async([
                {"role": "user", "parts": [cross_ref_prompt]}
            ])
            
            response_text = response.text.strip()
            
            # Parse JSON response
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            cross_ref_data = json.loads(response_text)
            cross_refs = cross_ref_data.get("cross_references", [])
            
            # Store cross-references in MongoDB
            for cross_ref in cross_refs:
                cross_ref_doc = {
                    "session_id": ObjectId(session_id),
                    "source_agent": source_agent,
                    "target_finding_id": cross_ref["target_finding_id"],
                    "relationship": cross_ref["relationship"],
                    "comment": cross_ref["comment"],
                    "confidence": cross_ref.get("confidence", 0.8),
                    "created_at": datetime.utcnow()
                }
                
                result = await db.agent_cross_references.insert_one(cross_ref_doc)
                cross_ref_doc["_id"] = str(result.inserted_id)
                cross_references.append(cross_ref_doc)
                
                logger.info(f"Cross-reference: {source_agent} -> {cross_ref['target_finding_id']} ({cross_ref['relationship']})")
            
        except json.JSONDecodeError as e:
            logger.error(f"[{source_agent}] Failed to parse cross-reference JSON: {e}")
        except Exception as e:
            logger.error(f"[{source_agent}] Error in cross-reference analysis: {e}")
    
    logger.info(f"Session {session_id}: Created {len(cross_references)} cross-references")
    
    return {
        "cross_references": cross_references,
        "summary": f"Generated {len(cross_references)} cross-references between agents"
    }


async def get_cross_references_for_session(session_id: str) -> List[Dict[str, Any]]:
    """Get all cross-references for a session."""
    db = get_db()
    
    cursor = await db.agent_cross_references.find({
        "session_id": ObjectId(session_id)
    }).to_list(length=None)
    
    # Convert ObjectId to string for JSON serialization
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["session_id"] = str(doc["session_id"])
    
    return cursor

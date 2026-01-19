import logging
from datetime import datetime
from typing import Dict, Any, Optional
from bson import ObjectId

from app.integrations.mongodb import get_db

logger = logging.getLogger(__name__)


async def record_metric(name: str, value: float, tags: Dict[str, Any] = None) -> None:
    """Store metrics in MongoDB for analysis."""
    db = get_db()
    
    metric_doc = {
        "name": name,
        "value": value,
        "tags": tags or {},
        "timestamp": datetime.utcnow()
    }
    
    await db.metrics.insert_one(metric_doc)
    logger.debug(f"Recorded metric: {name}={value} tags={tags}")


async def record_agent_latency(agent_type: str, session_id: str, latency_ms: int) -> None:
    """Record agent processing latency."""
    await record_metric(
        name="agent_latency_ms",
        value=latency_ms,
        tags={
            "agent_type": agent_type,
            "session_id": session_id
        }
    )


async def record_review_duration(session_id: str, duration_ms: int, findings_count: int) -> None:
    """Record total review duration and findings count."""
    await record_metric(
        name="total_review_time_ms",
        value=duration_ms,
        tags={
            "session_id": session_id,
            "findings_count": findings_count
        }
    )


async def record_findings_by_agent(session_id: str, agent_type: str, findings_count: int) -> None:
    """Record number of findings per agent."""
    await record_metric(
        name="findings_per_agent",
        value=findings_count,
        tags={
            "agent_type": agent_type,
            "session_id": session_id
        }
    )


async def record_cross_reference_count(session_id: str, cross_ref_count: int) -> None:
    """Record number of cross-references generated."""
    await record_metric(
        name="cross_reference_count",
        value=cross_ref_count,
        tags={
            "session_id": session_id
        }
    )


async def record_severity_distribution(session_id: str, severity_counts: Dict[int, int]) -> None:
    """Record distribution of finding severities."""
    for severity, count in severity_counts.items():
        await record_metric(
            name="severity_distribution",
            value=count,
            tags={
                "severity": severity,
                "session_id": session_id
            }
        )


async def record_confidence_distribution(session_id: str, confidence_values: list[float]) -> None:
    """Record distribution of confidence scores."""
    for confidence in confidence_values:
        await record_metric(
            name="confidence_distribution",
            value=confidence,
            tags={
                "session_id": session_id
            }
        )


async def get_metrics_summary(hours: int = 24) -> Dict[str, Any]:
    """Get aggregated metrics for demo dashboard."""
    db = get_db()
    
    # Calculate time threshold
    since = datetime.utcnow().timestamp() - (hours * 3600)
    
    # Aggregate metrics
    pipeline = [
        {"$match": {"timestamp": {"$gte": datetime.fromtimestamp(since)}}},
        {"$group": {
            "_id": "$name",
            "avg_value": {"$avg": "$value"},
            "min_value": {"$min": "$value"},
            "max_value": {"$max": "$value"},
            "count": {"$sum": 1},
            "latest": {"$max": "$timestamp"}
        }},
        {"$sort": {"latest": -1}}
    ]
    
    cursor = await db.metrics.aggregate(pipeline).to_list(length=None)
    
    # Convert to more readable format
    summary = {}
    for metric in cursor:
        name = metric["_id"]
        summary[name] = {
            "avg": round(metric["avg_value"], 2),
            "min": metric["min_value"],
            "max": metric["max_value"],
            "count": metric["count"]
        }
    
    # Add specific calculations
    summary["total_reviews"] = summary.get("total_review_time_ms", {}).get("count", 0)
    summary["avg_review_time_s"] = round(summary.get("total_review_time_ms", {}).get("avg", 0) / 1000, 1)
    summary["avg_agent_latency_ms"] = round(summary.get("agent_latency_ms", {}).get("avg", 0), 0)
    summary["avg_findings_per_review"] = round(summary.get("findings_per_agent", {}).get("avg", 0) * 5, 1)  # Assuming 5 agents
    
    return summary


async def get_agent_performance(hours: int = 24) -> Dict[str, Any]:
    """Get performance metrics broken down by agent type."""
    db = get_db()
    
    since = datetime.utcnow().timestamp() - (hours * 3600)
    
    # Agent latency breakdown
    latency_pipeline = [
        {"$match": {
            "name": "agent_latency_ms",
            "timestamp": {"$gte": datetime.fromtimestamp(since)}
        }},
        {"$group": {
            "_id": "$tags.agent_type",
            "avg_latency": {"$avg": "$value"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"avg_latency": 1}}
    ]
    
    agent_latency = await db.metrics.aggregate(latency_pipeline).to_list(length=None)
    
    # Findings per agent
    findings_pipeline = [
        {"$match": {
            "name": "findings_per_agent", 
            "timestamp": {"$gte": datetime.fromtimestamp(since)}
        }},
        {"$group": {
            "_id": "$tags.agent_type",
            "avg_findings": {"$avg": "$value"},
            "total_findings": {"$sum": "$value"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"avg_findings": -1}}
    ]
    
    agent_findings = await db.metrics.aggregate(findings_pipeline).to_list(length=None)
    
    # Combine results
    performance = {}
    for agent in ["security", "performance", "testing", "architecture", "documentation"]:
        latency_data = next((l for l in agent_latency if l["_id"] == agent), None)
        findings_data = next((f for f in agent_findings if f["_id"] == agent), None)
        
        performance[agent] = {
            "avg_latency_ms": round(latency_data["avg_latency"], 0) if latency_data else 0,
            "avg_findings": round(findings_data["avg_findings"], 1) if findings_data else 0,
            "total_findings": findings_data["total_findings"] if findings_data else 0,
            "review_count": findings_data["count"] if findings_data else 0
        }
    
    return performance


async def cleanup_old_metrics(days: int = 7) -> None:
    """Clean up old metrics to prevent database bloat."""
    db = get_db()
    
    cutoff = datetime.utcnow().timestamp() - (days * 24 * 3600)
    
    result = await db.metrics.delete_many({
        "timestamp": {"$lt": datetime.fromtimestamp(cutoff)}
    })
    
    logger.info(f"Cleaned up {result.deleted_count} old metric records")

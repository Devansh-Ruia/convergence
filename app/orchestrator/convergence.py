from collections import defaultdict
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def location_key(finding: dict) -> str:
    """Create a unique key for a code location."""
    file_path = finding.get("file_path", "unknown")
    line_start = finding.get("line_start", 0)
    line_end = finding.get("line_end", line_start)
    return f"{file_path}:{line_start}-{line_end}"


def findings_overlap(f1: dict, f2: dict) -> bool:
    """Check if two findings overlap in location."""
    if f1.get("file_path") != f2.get("file_path"):
        return False
    
    # Check line overlap
    s1, e1 = f1.get("line_start", 0), f1.get("line_end", f1.get("line_start", 0))
    s2, e2 = f2.get("line_start", 0), f2.get("line_end", f2.get("line_start", 0))
    
    return not (e1 < s2 or e2 < s1)


def merge_overlapping_findings(findings_by_agent: dict[str, list[dict]]) -> list[dict]:
    """
    Merge findings from all agents.
    - Group by file + line location
    - Boost severity when multiple agents flag same location
    - Deduplicate similar findings
    
    Returns sorted list of merged findings.
    """
    # Flatten all findings with source tracking
    all_findings = []
    for agent_type, findings in findings_by_agent.items():
        for f in findings:
            f_copy = f.copy()
            f_copy["_source"] = agent_type
            all_findings.append(f_copy)
    
    if not all_findings:
        return []
    
    # Group by location key
    grouped = defaultdict(list)
    for finding in all_findings:
        key = location_key(finding)
        grouped[key].append(finding)
    
    # Merge each group
    merged = []
    for location, findings_at_loc in grouped.items():
        if len(findings_at_loc) == 1:
            # Single finding - keep as is
            f = findings_at_loc[0]
            f["_sources"] = [f["_source"]]
            f["_merged"] = False
            merged.append(f)
        else:
            # Multiple agents flagged same location - merge and boost
            merged_finding = merge_finding_group(findings_at_loc)
            merged.append(merged_finding)
    
    # Sort by severity (desc), then by file path, then by line
    merged.sort(key=lambda f: (
        -f.get("severity", 0),
        f.get("file_path", ""),
        f.get("line_start", 0)
    ))
    
    logger.info(f"Merged {len(all_findings)} findings into {len(merged)} unique issues")
    return merged


def merge_finding_group(findings: list[dict]) -> dict:
    """
    Merge a group of findings at the same location.
    - Take highest severity and boost by 1 (max 5)
    - Combine descriptions
    - Track all sources
    """
    # Find highest severity finding as base
    base = max(findings, key=lambda f: f.get("severity", 0))
    
    # Collect all unique sources
    sources = list(set(f.get("_source", "unknown") for f in findings))
    sources.sort()
    
    # Boost severity for multi-agent agreement (max 5)
    original_severity = base.get("severity", 3)
    boosted_severity = min(original_severity + 1, 5)
    
    # Combine unique categories
    categories = list(set(f.get("category", "") for f in findings if f.get("category")))
    combined_category = "+".join(categories) if len(categories) > 1 else base.get("category", "")
    
    # Build merged title
    source_prefix = "+".join(s.upper()[:3] for s in sources)
    merged_title = f"[{source_prefix}] {base.get('title', 'Issue found')}"
    
    # Combine descriptions if different
    descriptions = []
    seen_desc = set()
    for f in findings:
        desc = f.get("description", "")
        if desc and desc not in seen_desc:
            source = f.get("_source", "unknown")
            descriptions.append(f"**[{source.title()}]** {desc}")
            seen_desc.add(desc)
    
    combined_description = "\n\n".join(descriptions)
    
    # Combine suggestions
    suggestions = list(set(f.get("suggestion", "") for f in findings if f.get("suggestion")))
    combined_suggestion = " | ".join(suggestions) if suggestions else base.get("suggestion", "")
    
    return {
        "id": f"merged-{base.get('id', 'unknown')}",
        "file_path": base.get("file_path", ""),
        "line_start": base.get("line_start", 0),
        "line_end": base.get("line_end", base.get("line_start", 0)),
        "severity": boosted_severity,
        "original_severity": original_severity,
        "category": combined_category,
        "title": merged_title,
        "description": combined_description,
        "suggestion": combined_suggestion,
        "code_snippet": base.get("code_snippet", ""),
        "_sources": sources,
        "_merged": True,
        "_finding_count": len(findings)
    }


def synthesize_markdown(
    pr_title: str,
    pr_url: str,
    findings: list[dict],
    agents_completed: list[str],
    duration_ms: int
) -> str:
    """
    Generate the final review markdown to post to GitHub.
    """
    lines = [
        "## 🔍 Convergence Code Review",
        "",
        f"**PR:** [{pr_title}]({pr_url})",
        f"**Analyzed by:** {len(agents_completed)} agents in {duration_ms/1000:.1f}s",
        "",
        "---",
        ""
    ]
    
    # Group by severity
    critical = [f for f in findings if f.get("severity", 0) >= 4]
    medium = [f for f in findings if 2 <= f.get("severity", 0) < 4]
    low = [f for f in findings if f.get("severity", 0) < 2]
    
    # Critical section
    if critical:
        lines.append(f"### 🚨 Critical Issues ({len(critical)})")
        lines.append("")
        for f in critical:
            lines.extend(format_finding_markdown(f))
    
    # Medium section
    if medium:
        lines.append(f"### ⚠️ Recommendations ({len(medium)})")
        lines.append("")
        for f in medium:
            lines.extend(format_finding_markdown(f))
    
    # Low section
    if low:
        lines.append(f"### 💡 Suggestions ({len(low)})")
        lines.append("")
        for f in low:
            lines.extend(format_finding_markdown(f))
    
    # No issues found
    if not findings:
        lines.extend([
            "### ✅ No Issues Found",
            "",
            "This PR looks good! No significant issues detected by our analysis.",
            "",
        ])
    
    # Summary table
    lines.extend([
        "---",
        "",
        "### 📊 Summary",
        "",
        "| Severity | Count |",
        "|----------|-------|",
        f"| 🚨 Critical/High | {len(critical)} |",
        f"| ⚠️ Medium | {len(medium)} |",
        f"| 💡 Low/Info | {len(low)} |",
        f"| **Total** | **{len(findings)}** |",
        "",
        "---",
        "",
        f"<sub>🤖 Reviewed by **Convergence** • Agents: [{', '.join(a.title() for a in agents_completed)}] • {duration_ms/1000:.1f}s</sub>"
    ])
    
    return "\n".join(lines)


def calculate_consensus_severity(finding: dict, cross_refs: List[Dict[str, Any]]) -> int:
    """
    Adjust severity based on agent consensus:
    - 3+ agents reinforce → severity +2 (max 5)
    - 2 agents reinforce → severity +1
    - Any agent conflicts → cap at original severity
    - All agents silent → no change
    """
    original_severity = finding.get("severity", 3)
    finding_id = finding.get("id", "")
    
    if not cross_refs:
        return original_severity
    
    # Count cross-references by relationship type
    reinforce_count = 0
    extend_count = 0
    conflict_count = 0
    
    for cross_ref in cross_refs:
        if cross_ref.get("target_finding_id") == finding_id:
            relationship = cross_ref.get("relationship", "")
            if relationship == "reinforce":
                reinforce_count += 1
            elif relationship == "extend":
                extend_count += 1
            elif relationship == "conflict":
                conflict_count += 1
    
    # If any conflicts, don't boost severity
    if conflict_count > 0:
        logger.info(f"Finding {finding_id}: {conflict_count} conflicts, keeping severity {original_severity}")
        return original_severity
    
    # Calculate severity boost based on reinforcements
    if reinforce_count >= 3:
        boosted_severity = min(original_severity + 2, 5)
        logger.info(f"Finding {finding_id}: {reinforce_count} reinforcements, boosting {original_severity} → {boosted_severity}")
        return boosted_severity
    elif reinforce_count >= 2:
        boosted_severity = min(original_severity + 1, 5)
        logger.info(f"Finding {finding_id}: {reinforce_count} reinforcements, boosting {original_severity} → {boosted_severity}")
        return boosted_severity
    elif extend_count >= 2:
        # Multiple extensions also get a small boost
        boosted_severity = min(original_severity + 1, 5)
        logger.info(f"Finding {finding_id}: {extend_count} extensions, boosting {original_severity} → {boosted_severity}")
        return boosted_severity
    
    # No significant consensus
    return original_severity


def apply_consensus_to_findings(findings: List[dict], cross_refs: List[Dict[str, Any]]) -> List[dict]:
    """
    Apply consensus severity adjustments to all findings.
    """
    adjusted_findings = []
    
    for finding in findings:
        adjusted_finding = finding.copy()
        original_severity = finding.get("severity", 3)
        consensus_severity = calculate_consensus_severity(finding, cross_refs)
        
        adjusted_finding["original_severity"] = original_severity
        adjusted_finding["severity"] = consensus_severity
        
        if consensus_severity != original_severity:
            adjusted_finding["consensus_adjusted"] = True
            logger.info(f"Consensus adjustment: {finding.get('id')} {original_severity} → {consensus_severity}")
        
        adjusted_findings.append(adjusted_finding)
    
    return adjusted_findings


def format_finding_markdown(finding: dict) -> list[str]:
    """Format a single finding as markdown lines."""
    # Build header with source info
    sources = finding.get("_sources", [finding.get("_source", "unknown")])
    source_str = "+".join(s.upper()[:3] for s in sources)
    
    severity = finding.get("severity", 3)
    severity_emoji = {5: "🔴", 4: "🟠", 3: "🟡", 2: "🔵", 1: "⚪"}.get(severity, "⚪")
    
    title = finding.get("title", "Issue")
    # Remove source prefix if already in title to avoid duplication
    if title.startswith("["):
        display_title = title
    else:
        display_title = f"[{source_str}] {title}"
    
    # Add confidence if available
    confidence = finding.get("confidence", 0.8)
    if confidence >= 0.9:
        confidence_str = f" ({confidence*100:.0f}% confidence)"
    elif confidence >= 0.7:
        confidence_str = f" ({confidence*100:.0f}% confidence)"
    else:
        confidence_str = f" ({confidence*100:.0f}% confidence)"
    
    # Add consensus adjustment indicator
    consensus_indicator = " ⚡" if finding.get("consensus_adjusted") else ""
    
    file_path = finding.get("file_path", "unknown")
    line_start = finding.get("line_start", 0)
    line_end = finding.get("line_end", line_start)
    
    line_info = f"Line {line_start}" if line_start == line_end else f"Lines {line_start}-{line_end}"
    
    lines = [
        f"#### {severity_emoji} {display_title}{confidence_str}{consensus_indicator}",
        f"📁 `{file_path}` • {line_info}",
        "",
    ]
    
    # Description
    description = finding.get("description", "")
    if description:
        lines.append(description)
        lines.append("")
    
    # Reasoning if available
    reasoning = finding.get("reasoning", "")
    if reasoning:
        lines.extend([
            f"**🧠 Reasoning:** {reasoning}",
            ""
        ])
    
    # Code snippet
    code_snippet = finding.get("code_snippet", "")
    if code_snippet:
        lines.extend([
            "```",
            code_snippet,
            "```",
            ""
        ])
    
    # Suggestion
    suggestion = finding.get("suggestion", "")
    if suggestion:
        lines.extend([
            f"**💡 Suggestion:** {suggestion}",
            ""
        ])
    
    # Multi-agent badge
    if finding.get("_merged"):
        count = finding.get("_finding_count", len(sources))
        lines.append(f"*⚡ Flagged by {count} agents: {', '.join(sources)}*")
        lines.append("")
    
    # Consensus adjustment info
    if finding.get("consensus_adjusted"):
        original = finding.get("original_severity", severity)
        lines.append(f"*📈 Severity adjusted by consensus: {original} → {severity}*")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    return lines
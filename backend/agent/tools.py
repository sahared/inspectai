"""
InspectAI Agent Tools
Functions the agent can call during an inspection.
"""

import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Standard areas for a property inspection
STANDARD_INSPECTION_AREAS = [
    "exterior_roof",
    "exterior_walls",
    "exterior_foundation",
    "exterior_windows",
    "kitchen",
    "living_room",
    "dining_room",
    "master_bedroom",
    "bedroom_2",
    "bedroom_3",
    "master_bathroom",
    "bathroom_2",
    "basement",
    "attic",
    "garage",
    "laundry_room",
    "hallways_stairs",
]

DAMAGE_TYPES = [
    "water_damage",
    "fire_damage",
    "structural_crack",
    "mold",
    "impact_damage",
    "wind_damage",
    "hail_damage",
    "foundation_issue",
    "electrical",
    "plumbing",
    "roof_damage",
    "flooring_damage",
    "other",
]

SEVERITY_LEVELS = ["minor", "moderate", "severe", "critical"]


def get_tool_declarations():
    """
    Return tool declarations in the format Gemini API expects.
    These define what tools the agent can call.
    """
    return [
        {
            "name": "capture_evidence",
            "description": (
                "Log an inspection finding as evidence. Call this EVERY time you "
                "identify damage or a notable condition during the inspection. "
                "Be specific and detailed in the description."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "evidence_number": {
                        "type": "integer",
                        "description": "Sequential evidence number (1, 2, 3, ...)",
                    },
                    "room": {
                        "type": "string",
                        "description": (
                            "Room or area where damage was found. "
                            "Examples: kitchen, master_bedroom, exterior_roof"
                        ),
                    },
                    "damage_type": {
                        "type": "string",
                        "description": "Type of damage identified",
                        "enum": DAMAGE_TYPES,
                    },
                    "severity": {
                        "type": "string",
                        "description": (
                            "Severity level: minor (cosmetic only), "
                            "moderate (functional impact), "
                            "severe (structural/safety concern), "
                            "critical (immediate safety hazard)"
                        ),
                        "enum": SEVERITY_LEVELS,
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "Detailed description of the finding. Include: "
                            "location within room, approximate size, visual characteristics, "
                            "and any relevant observations about cause or progression."
                        ),
                    },
                    "recommended_action": {
                        "type": "string",
                        "description": (
                            "Recommended next step for this finding. "
                            "Examples: 'Professional mold remediation', "
                            "'Structural engineer assessment', 'Monitor for changes'"
                        ),
                    },
                },
                "required": [
                    "evidence_number",
                    "room",
                    "damage_type",
                    "severity",
                    "description",
                ],
            },
        },
        {
            "name": "check_progress",
            "description": (
                "Check which areas of the property have been inspected and "
                "which still need to be covered. Call this periodically to "
                "ensure thorough coverage and before ending the inspection."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "areas_inspected": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of areas that have been inspected so far. "
                            "Use standardized names like: kitchen, living_room, "
                            "master_bedroom, exterior_roof, etc."
                        ),
                    },
                },
                "required": ["areas_inspected"],
            },
        },
        {
            "name": "generate_report",
            "description": (
                "Generate the final inspection report PDF. Call this when the "
                "inspection is complete and the user is ready for their report. "
                "This compiles all evidence, findings, and photos into a "
                "professional document."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": (
                            "Executive summary of the inspection findings. "
                            "2-3 paragraphs covering: what was inspected, "
                            "key findings, overall severity assessment, "
                            "and priority recommendations."
                        ),
                    },
                    "overall_severity": {
                        "type": "string",
                        "description": "Overall property damage severity assessment",
                        "enum": SEVERITY_LEVELS,
                    },
                },
                "required": ["summary", "overall_severity"],
            },
        },
        {
            "name": "flag_safety_concern",
            "description": (
                "Flag an immediate safety concern that requires urgent attention. "
                "Use this for exposed wiring, gas leaks, structural instability, "
                "or any condition that poses immediate risk."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "concern": {
                        "type": "string",
                        "description": "Description of the safety concern",
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["high", "critical"],
                        "description": "Urgency level of the safety concern",
                    },
                    "recommended_action": {
                        "type": "string",
                        "description": (
                            "Immediate action the user should take. "
                            "Examples: 'Evacuate the area', 'Turn off main water valve', "
                            "'Contact electrician immediately'"
                        ),
                    },
                },
                "required": ["concern", "urgency", "recommended_action"],
            },
        },
    ]


class InspectionToolHandler:
    """
    Handles tool calls from the Gemini agent during inspection.
    Processes each tool call and returns results.
    """

    def __init__(self, session_id: str, firestore_service, storage_service):
        self.session_id = session_id
        self.firestore = firestore_service
        self.storage = storage_service
        self.findings = []
        self.areas_inspected = set()
        self.evidence_count = 0
        self.safety_concerns = []

    async def handle_tool_call(self, tool_name: str, tool_args: dict) -> dict:
        """Route a tool call to the appropriate handler."""
        handlers = {
            "capture_evidence": self._handle_capture_evidence,
            "check_progress": self._handle_check_progress,
            "generate_report": self._handle_generate_report,
            "flag_safety_concern": self._handle_flag_safety_concern,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            result = await handler(tool_args)
            logger.info(f"Tool {tool_name} executed successfully for session {self.session_id}")
            return result
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {"error": str(e)}

    async def _handle_capture_evidence(self, args: dict) -> dict:
        """Capture and store an inspection finding."""
        self.evidence_count += 1

        finding = {
            "evidence_number": args.get("evidence_number", self.evidence_count),
            "room": args["room"],
            "damage_type": args["damage_type"],
            "severity": args["severity"],
            "description": args["description"],
            "recommended_action": args.get("recommended_action", ""),
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": self.session_id,
        }

        self.findings.append(finding)
        self.areas_inspected.add(args["room"])

        # Save to Firestore
        await self.firestore.add_finding(self.session_id, finding)

        # Update session areas
        await self.firestore.update_session(self.session_id, {
            "areas_inspected": list(self.areas_inspected),
            "finding_count": len(self.findings),
        })

        return {
            "status": "captured",
            "evidence_number": finding["evidence_number"],
            "message": (
                f"Evidence #{finding['evidence_number']} logged: "
                f"{args['damage_type']} in {args['room']} ({args['severity']})"
            ),
            "total_findings": len(self.findings),
        }

    async def _handle_check_progress(self, args: dict) -> dict:
        """Check inspection progress and identify gaps."""
        inspected = set(args.get("areas_inspected", []))
        self.areas_inspected.update(inspected)

        # Determine relevant areas (not every property has all areas)
        all_areas = set(STANDARD_INSPECTION_AREAS)
        remaining = all_areas - self.areas_inspected
        completion = (len(self.areas_inspected) / len(all_areas)) * 100

        return {
            "areas_inspected": sorted(list(self.areas_inspected)),
            "areas_remaining": sorted(list(remaining)),
            "completion_percentage": round(completion, 1),
            "total_findings_so_far": len(self.findings),
            "suggestion": (
                f"You've covered {len(self.areas_inspected)} of {len(all_areas)} "
                f"standard areas ({completion:.0f}%). "
                f"Key areas remaining: {', '.join(sorted(remaining)[:5])}"
                if remaining
                else "All standard areas have been covered. Great job!"
            ),
        }

    async def _handle_generate_report(self, args: dict) -> dict:
        """Generate the final inspection report."""
        report_data = {
            "session_id": self.session_id,
            "summary": args["summary"],
            "overall_severity": args["overall_severity"],
            "findings": self.findings,
            "areas_inspected": sorted(list(self.areas_inspected)),
            "safety_concerns": self.safety_concerns,
            "generated_at": datetime.utcnow().isoformat(),
        }

        return {
            "status": "report_generation_requested",
            "finding_count": len(self.findings),
            "areas_covered": len(self.areas_inspected),
            "overall_severity": args["overall_severity"],
            "message": "Report generation initiated. The PDF will be ready shortly.",
        }

    async def _handle_flag_safety_concern(self, args: dict) -> dict:
        """Flag an immediate safety concern."""
        concern = {
            "concern": args["concern"],
            "urgency": args["urgency"],
            "recommended_action": args["recommended_action"],
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.safety_concerns.append(concern)

        await self.firestore.update_session(self.session_id, {
            "safety_concerns": self.safety_concerns,
        })

        return {
            "status": "safety_concern_flagged",
            "urgency": args["urgency"],
            "message": (
                f"⚠️ SAFETY CONCERN FLAGGED ({args['urgency'].upper()}): "
                f"{args['concern']}. Action: {args['recommended_action']}"
            ),
        }

    def get_findings_summary(self) -> dict:
        """Get a summary of all findings for the current session."""
        severity_counts = {}
        for f in self.findings:
            sev = f["severity"]
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        return {
            "total_findings": len(self.findings),
            "severity_breakdown": severity_counts,
            "areas_covered": len(self.areas_inspected),
            "safety_concerns": len(self.safety_concerns),
        }

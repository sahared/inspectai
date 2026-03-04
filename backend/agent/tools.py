import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

STANDARD_INSPECTION_AREAS = [
    "exterior_roof", "exterior_walls", "exterior_foundation", "exterior_windows",
    "kitchen", "living_room", "dining_room", "master_bedroom", "bedroom_2",
    "bedroom_3", "master_bathroom", "bathroom_2", "basement", "attic",
    "garage", "laundry_room", "hallways_stairs",
]

DAMAGE_TYPES = [
    "water_damage", "fire_damage", "structural_crack", "mold", "impact_damage",
    "wind_damage", "hail_damage", "foundation_issue", "electrical", "plumbing",
    "roof_damage", "flooring_damage", "other",
]

SEVERITY_LEVELS = ["minor", "moderate", "severe", "critical"]


def get_tool_declarations():
    return [
        {
            "name": "capture_evidence",
            "description": "Log an inspection finding as evidence. Call this EVERY time you identify damage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "evidence_number": {"type": "integer", "description": "Sequential evidence number (1, 2, 3...)"},
                    "room": {"type": "string", "description": "Room or area where damage was found"},
                    "damage_type": {"type": "string", "description": "Type of damage identified", "enum": DAMAGE_TYPES},
                    "severity": {"type": "string", "description": "Severity level", "enum": SEVERITY_LEVELS},
                    "description": {"type": "string", "description": "Detailed description of the finding"},
                    "recommended_action": {"type": "string", "description": "Recommended next step"},
                },
                "required": ["evidence_number", "room", "damage_type", "severity", "description"],
            },
        },
        {
            "name": "check_progress",
            "description": "Check which areas have been inspected and which remain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "areas_inspected": {"type": "array", "items": {"type": "string"}, "description": "Areas inspected so far"},
                },
                "required": ["areas_inspected"],
            },
        },
        {
            "name": "flag_safety_concern",
            "description": "Flag an immediate safety concern requiring urgent attention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "concern": {"type": "string", "description": "Description of the safety concern"},
                    "urgency": {"type": "string", "enum": ["high", "critical"]},
                    "recommended_action": {"type": "string", "description": "Immediate action to take"},
                },
                "required": ["concern", "urgency", "recommended_action"],
            },
        },
    ]


class InspectionToolHandler:
    def __init__(self, session_id, firestore_service, storage_service):
        self.session_id = session_id
        self.firestore = firestore_service
        self.storage = storage_service
        self.findings = []
        self.areas_inspected = set()
        self.evidence_count = 0
        self.safety_concerns = []

    async def handle_tool_call(self, tool_name, tool_args):
        handlers = {
            "capture_evidence": self._handle_capture_evidence,
            "check_progress": self._handle_check_progress,
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

    async def _handle_capture_evidence(self, args):
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
            "photo_path": "",  # Will be filled by websocket handler if camera frame available
        }

        self.findings.append(finding)
        self.areas_inspected.add(args["room"])

        await self.firestore.add_finding(self.session_id, finding)
        await self.firestore.update_session(self.session_id, {
            "areas_inspected": list(self.areas_inspected),
            "finding_count": len(self.findings),
        })

        # Return full finding data so frontend can display it
        return {
            "status": "captured",
            "evidence_number": finding["evidence_number"],
            "room": finding["room"],
            "damage_type": finding["damage_type"],
            "severity": finding["severity"],
            "description": finding["description"],
            "recommended_action": finding.get("recommended_action", ""),
            "photo_path": finding["photo_path"],
            "message": f"Evidence #{finding['evidence_number']} logged: {args['damage_type']} in {args['room']} ({args['severity']})",
            "total_findings": len(self.findings),
        }

    async def _handle_check_progress(self, args):
        inspected = set(args.get("areas_inspected", []))
        self.areas_inspected.update(inspected)
        all_areas = set(STANDARD_INSPECTION_AREAS)
        remaining = all_areas - self.areas_inspected
        completion = (len(self.areas_inspected) / len(all_areas)) * 100
        return {
            "areas_inspected": sorted(list(self.areas_inspected)),
            "areas_remaining": sorted(list(remaining)),
            "completion_percentage": round(completion, 1),
            "total_findings_so_far": len(self.findings),
            "suggestion": f"Covered {len(self.areas_inspected)}/{len(all_areas)} areas. Remaining: {', '.join(sorted(remaining)[:5])}" if remaining else "All areas covered.",
        }

    async def _handle_flag_safety_concern(self, args):
        concern = {
            "concern": args["concern"],
            "urgency": args["urgency"],
            "recommended_action": args["recommended_action"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.safety_concerns.append(concern)
        await self.firestore.update_session(self.session_id, {"safety_concerns": self.safety_concerns})
        return {
            "status": "safety_concern_flagged",
            "urgency": args["urgency"],
            "message": f"SAFETY CONCERN ({args['urgency'].upper()}): {args['concern']}. Action: {args['recommended_action']}",
        }

    def get_findings_summary(self):
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

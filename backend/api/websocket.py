import os
import json
import re
import base64
import asyncio
import logging
from datetime import datetime
from fastapi import WebSocket
from services.gemini_live import GeminiLiveSession
from agent.tools import InspectionToolHandler

logger = logging.getLogger(__name__)


class InspectionWebSocketHandler:
    def __init__(self, websocket, session_id, firestore_service, storage_service, report_generator):
        self.ws = websocket
        self.session_id = session_id
        self.firestore = firestore_service
        self.storage = storage_service
        self.report_generator = report_generator
        self.tool_handler = InspectionToolHandler(
            session_id=session_id,
            firestore_service=firestore_service,
            storage_service=storage_service,
        )
        self.gemini_session = None
        self._receive_task = None
        self._frame_count = 0
        self._text_buffer = ""
        self._latest_frame = None  # Store latest camera frame for evidence photos

    async def connect(self):
        await self.ws.accept()
        logger.info(f"WebSocket connected: {self.session_id}")
        await self._send({"type": "status", "status": "connecting", "message": "Connecting to InspectAI..."})

        self.gemini_session = GeminiLiveSession(
            session_id=self.session_id,
            tool_handler=self.tool_handler,
            on_text=self._on_agent_text_chunk,
            on_turn_complete=self._on_turn_complete,
            on_finding=self._on_finding,
            on_tool_result=self._on_tool_result,
        )

        try:
            await self.gemini_session.connect()
            self._receive_task = asyncio.create_task(self.gemini_session.receive_responses())
            await self._send({"type": "status", "status": "connected", "message": "InspectAI is ready. Point your camera and start talking."})
            await self.firestore.update_session(self.session_id, {"status": "active", "started_at": datetime.utcnow().isoformat()})
        except Exception as e:
            logger.error(f"Gemini init failed: {e}")
            await self._send({"type": "error", "message": f"Failed to connect: {str(e)}"})
            raise

    async def run(self):
        try:
            while True:
                raw = await self.ws.receive_text()
                msg = json.loads(raw)
                t = msg.get("type", "")
                if t == "frame":
                    await self._handle_frame(msg)
                elif t == "frame_with_text":
                    await self._handle_frame_with_text(msg)
                elif t == "text":
                    await self._handle_text(msg)
                elif t == "end_inspection":
                    await self._handle_end_inspection()
                    break
                elif t == "ping":
                    await self._send({"type": "pong"})
        except Exception as e:
            logger.error(f"WebSocket run error: {e}")
            raise

    async def disconnect(self):
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self.gemini_session:
            await self.gemini_session.disconnect()
        try:
            await self.firestore.update_session(self.session_id, {
                "status": "completed",
                "ended_at": datetime.utcnow().isoformat(),
                "total_frames": self._frame_count,
            })
        except:
            pass

    # ── Handle incoming messages ─────────────────────────────────────

    async def _handle_frame(self, msg):
        """Process camera frame — store latest and send every Nth to Gemini."""
        try:
            frame_bytes = base64.b64decode(msg["data"])
            self._frame_count += 1
            # Always store latest frame for evidence photos
            self._latest_frame = frame_bytes

            # Only send every 10th frame to Gemini for analysis
            if self._frame_count % 10 == 0:
                await self.gemini_session.send_frame(frame_bytes)
                await self._send({"type": "frame_analyzed", "frame_number": self._frame_count})
                logger.info(f"Frame #{self._frame_count} sent to Gemini")
        except Exception as e:
            logger.error(f"Frame error: {e}")

    async def _handle_frame_with_text(self, msg):
        """Process camera frame + user question — always sends to Gemini."""
        try:
            frame_bytes = base64.b64decode(msg["data"])
            text = msg.get("text", "What do you see? Log any damage.")
            self._frame_count += 1
            self._latest_frame = frame_bytes

            await self._send({"type": "transcript", "text": text, "speaker": "user", "timestamp": datetime.utcnow().isoformat()})
            await self.gemini_session.send_frame_and_text(frame_bytes, text)
            await self._send({"type": "frame_analyzed", "frame_number": self._frame_count})
        except Exception as e:
            logger.error(f"Frame+text error: {e}")

    async def _handle_text(self, msg):
        """Process text message."""
        text = msg.get("data", "")
        if text:
            await self._send({"type": "transcript", "text": text, "speaker": "user", "timestamp": datetime.utcnow().isoformat()})
            await self.gemini_session.send_text(text)

    async def _handle_end_inspection(self):
        """End inspection and generate report."""
        await self._send({"type": "status", "status": "generating_report", "message": "Generating report..."})
        try:
            findings = self.tool_handler.findings
            session = await self.firestore.get_session(self.session_id)
            report_url = await self.report_generator.generate(
                session_id=self.session_id,
                session_data=session or {},
                findings=findings,
            )
            await self.firestore.update_session(self.session_id, {"status": "report_generated", "report_url": report_url})
            await self._send({
                "type": "report_ready",
                "url": f"/api/reports/{self.session_id}",
                "summary": self.tool_handler.get_findings_summary(),
            })
        except Exception as e:
            logger.error(f"Report error: {e}")
            await self._send({"type": "error", "message": str(e)})

    # ── Callbacks from Gemini ────────────────────────────────────────

    async def _on_agent_text_chunk(self, text):
        """Accumulate text chunks into buffer."""
        self._text_buffer += text

    async def _on_turn_complete(self):
        """Agent finished one complete response — send as ONE chat bubble."""
        if self._text_buffer.strip():
            clean = self._text_buffer.strip()
            # Remove thinking blocks like **Bold Headers**
            clean = re.sub(r'\*\*[^*]+\*\*\n?', '', clean).strip()
            if clean:
                await self._send({
                    "type": "transcript",
                    "text": clean,
                    "speaker": "agent",
                    "timestamp": datetime.utcnow().isoformat(),
                })
        self._text_buffer = ""

    async def _on_finding(self, finding):
        """Called when agent captures evidence — save photo and notify frontend."""
        # Save latest camera frame as evidence photo
        if self._latest_frame and finding.get("evidence_number"):
            try:
                photo_dir = f"local_storage/sessions/{self.session_id}/evidence"
                os.makedirs(photo_dir, exist_ok=True)
                photo_path = f"{photo_dir}/photo_{finding['evidence_number']}.jpg"
                with open(photo_path, "wb") as f:
                    f.write(self._latest_frame)
                finding["photo_path"] = photo_path
                logger.info(f"Evidence photo saved: {photo_path}")

                # Also update the finding in the tool handler so report includes it
                for stored_finding in self.tool_handler.findings:
                    if stored_finding.get("evidence_number") == finding.get("evidence_number"):
                        stored_finding["photo_path"] = photo_path
                        break
            except Exception as e:
                logger.warning(f"Failed to save evidence photo: {e}")

        await self._send({"type": "finding", "finding": finding})

        summary = self.tool_handler.get_findings_summary()
        await self._send({
            "type": "progress",
            "total_findings": summary["total_findings"],
            "severity_breakdown": summary["severity_breakdown"],
            "areas_covered": summary["areas_covered"],
        })

    async def _on_tool_result(self, tool_name, result):
        """Handle non-evidence tool results."""
        if tool_name == "check_progress":
            await self._send({
                "type": "progress",
                "areas_inspected": result.get("areas_inspected", []),
                "areas_remaining": result.get("areas_remaining", []),
                "completion": result.get("completion_percentage", 0),
            })
        elif tool_name == "flag_safety_concern":
            await self._send({"type": "safety_alert", "concern": result})

    # ── Utility ──────────────────────────────────────────────────────

    async def _send(self, data):
        """Send JSON message to frontend."""
        try:
            await self.ws.send_text(json.dumps(data))
        except Exception as e:
            logger.error(f"Send error: {e}")

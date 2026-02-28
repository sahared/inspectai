"""
WebSocket Handler for Real-Time Inspection
Bridges the frontend (camera + audio) with the Gemini Live API.
"""

import json
import base64
import asyncio
import logging
from datetime import datetime

from fastapi import WebSocket

from services.gemini_live import GeminiLiveSession
from agent.tools import InspectionToolHandler

logger = logging.getLogger(__name__)


class InspectionWebSocketHandler:
    """
    Manages a single WebSocket connection for a real-time inspection.
    
    Data flow:
    Frontend → WebSocket → This Handler → Gemini Live API → This Handler → WebSocket → Frontend
    
    Client sends:
      {"type": "frame", "data": "<base64_jpeg>"}    → Camera frame
      {"type": "audio", "data": "<base64_pcm>"}     → Audio chunk  
      {"type": "text", "data": "user message"}      → Text input
      {"type": "end_inspection"}                      → End session
    
    Server sends:
      {"type": "transcript", "text": "...", "speaker": "agent"}
      {"type": "audio", "data": "<base64_pcm>"}
      {"type": "finding", "finding": {...}}
      {"type": "progress", ...}
      {"type": "status", "status": "..."}
      {"type": "report_ready", "url": "..."}
      {"type": "error", "message": "..."}
    """

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        firestore_service,
        storage_service,
        report_generator,
    ):
        self.ws = websocket
        self.session_id = session_id
        self.firestore = firestore_service
        self.storage = storage_service
        self.report_generator = report_generator

        # Tool handler for this session
        self.tool_handler = InspectionToolHandler(
            session_id=session_id,
            firestore_service=firestore_service,
            storage_service=storage_service,
        )

        # Gemini Live session
        self.gemini_session = None
        self._receive_task = None
        self._frame_count = 0

    async def connect(self):
        """Accept WebSocket connection and initialize Gemini session."""
        await self.ws.accept()
        logger.info(f"WebSocket connected for session {self.session_id}")

        # Send status to client
        await self._send_to_client({
            "type": "status",
            "status": "connecting",
            "message": "Connecting to InspectAI...",
        })

        # Initialize Gemini Live session
        self.gemini_session = GeminiLiveSession(
            session_id=self.session_id,
            tool_handler=self.tool_handler,
            on_text=self._on_agent_text,
            on_audio=self._on_agent_audio,
            on_finding=self._on_finding,
            on_tool_result=self._on_tool_result,
        )

        try:
            await self.gemini_session.connect()

            # Start receiving responses from Gemini in background
            self._receive_task = asyncio.create_task(
                self.gemini_session.receive_responses()
            )

            await self._send_to_client({
                "type": "status",
                "status": "connected",
                "message": "InspectAI is ready. Point your camera and start talking.",
            })

            # Update session status in Firestore
            await self.firestore.update_session(self.session_id, {
                "status": "active",
                "started_at": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            logger.error(f"Failed to initialize Gemini session: {e}")
            await self._send_to_client({
                "type": "error",
                "message": f"Failed to connect to AI service: {str(e)}",
            })
            raise

    async def run(self):
        """Main loop — receive messages from client and forward to Gemini."""
        try:
            while True:
                # Receive message from frontend
                raw_data = await self.ws.receive_text()
                message = json.loads(raw_data)
                msg_type = message.get("type", "")

                if msg_type == "frame":
                    await self._handle_frame(message)
                elif msg_type == "audio":
                    await self._handle_audio(message)
                elif msg_type == "text":
                    await self._handle_text(message)
                elif msg_type == "end_inspection":
                    await self._handle_end_inspection()
                    break
                elif msg_type == "ping":
                    await self._send_to_client({"type": "pong"})
                else:
                    logger.warning(f"Unknown message type: {msg_type}")

        except Exception as e:
            logger.error(f"Error in WebSocket run loop: {e}")
            raise

    async def disconnect(self):
        """Clean up resources."""
        # Cancel the Gemini receive task
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # Disconnect from Gemini
        if self.gemini_session:
            await self.gemini_session.disconnect()

        # Update session status
        try:
            await self.firestore.update_session(self.session_id, {
                "status": "completed",
                "ended_at": datetime.utcnow().isoformat(),
                "total_frames_processed": self._frame_count,
            })
        except Exception:
            pass

        logger.info(f"WebSocket handler cleaned up for session {self.session_id}")

    # =========================================================================
    # Handle incoming messages from frontend
    # =========================================================================

    async def _handle_frame(self, message: dict):
        """Process a camera frame from the frontend."""
        try:
            frame_b64 = message["data"]
            frame_bytes = base64.b64decode(frame_b64)
            self._frame_count += 1

            # Send frame to Gemini
            await self.gemini_session.send_frame(frame_bytes)

            # Every 10th frame, optionally save a snapshot for evidence
            if self._frame_count % 30 == 0:
                logger.debug(
                    f"Session {self.session_id}: "
                    f"Processed {self._frame_count} frames"
                )

        except Exception as e:
            logger.error(f"Error handling frame: {e}")

    async def _handle_audio(self, message: dict):
        """Process an audio chunk from the frontend."""
        try:
            audio_b64 = message["data"]
            audio_bytes = base64.b64decode(audio_b64)

            # Send audio to Gemini
            await self.gemini_session.send_audio(audio_bytes)

        except Exception as e:
            logger.error(f"Error handling audio: {e}")

    async def _handle_text(self, message: dict):
        """Process a text message from the frontend."""
        text = message.get("data", "")
        if text:
            # Send user text to client for display
            await self._send_to_client({
                "type": "transcript",
                "text": text,
                "speaker": "user",
                "timestamp": datetime.utcnow().isoformat(),
            })

            # Forward to Gemini
            await self.gemini_session.send_text(text)

    async def _handle_end_inspection(self):
        """Handle end of inspection — generate report."""
        await self._send_to_client({
            "type": "status",
            "status": "generating_report",
            "message": "Generating your inspection report...",
        })

        try:
            # Get findings
            findings = self.tool_handler.findings
            summary = self.tool_handler.get_findings_summary()

            # Get session data
            session = await self.firestore.get_session(self.session_id)

            # Generate report
            report_url = await self.report_generator.generate(
                session_id=self.session_id,
                session_data=session or {},
                findings=findings,
            )

            # Update session
            await self.firestore.update_session(self.session_id, {
                "status": "report_generated",
                "report_url": report_url,
            })

            # Notify client
            await self._send_to_client({
                "type": "report_ready",
                "url": report_url,
                "summary": summary,
            })

        except Exception as e:
            logger.error(f"Error generating report: {e}")
            await self._send_to_client({
                "type": "error",
                "message": f"Error generating report: {str(e)}",
            })

    # =========================================================================
    # Callbacks from Gemini Live session
    # =========================================================================

    async def _on_agent_text(self, text: str):
        """Called when Gemini produces text output."""
        await self._send_to_client({
            "type": "transcript",
            "text": text,
            "speaker": "agent",
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def _on_agent_audio(self, audio_data: bytes):
        """Called when Gemini produces audio output."""
        await self._send_to_client({
            "type": "audio",
            "data": base64.b64encode(audio_data).decode("utf-8"),
        })

    async def _on_finding(self, finding: dict):
        """Called when agent captures a new finding."""
        await self._send_to_client({
            "type": "finding",
            "finding": finding,
        })

        # Send progress update
        summary = self.tool_handler.get_findings_summary()
        await self._send_to_client({
            "type": "progress",
            "total_findings": summary["total_findings"],
            "severity_breakdown": summary["severity_breakdown"],
            "areas_covered": summary["areas_covered"],
        })

    async def _on_tool_result(self, tool_name: str, result: dict):
        """Called when any tool execution completes."""
        if tool_name == "check_progress":
            await self._send_to_client({
                "type": "progress",
                "areas_inspected": result.get("areas_inspected", []),
                "areas_remaining": result.get("areas_remaining", []),
                "completion": result.get("completion_percentage", 0),
            })
        elif tool_name == "flag_safety_concern":
            await self._send_to_client({
                "type": "safety_alert",
                "concern": result,
            })

    # =========================================================================
    # Utility
    # =========================================================================

    async def _send_to_client(self, data: dict):
        """Send a JSON message to the frontend via WebSocket."""
        try:
            await self.ws.send_text(json.dumps(data))
        except Exception as e:
            logger.error(f"Error sending to client: {e}")

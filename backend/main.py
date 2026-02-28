"""
InspectAI Backend — FastAPI Server
Real-time AI-powered property inspection agent using Gemini Live API
"""

import os
import uuid
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.websocket import InspectionWebSocketHandler
from services.firestore_service import FirestoreService
from services.storage_service import StorageService
from services.report_generator import ReportGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize services
firestore_service = FirestoreService()
storage_service = StorageService()
report_generator = ReportGenerator(storage_service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info("🔍 InspectAI Backend starting up...")
    logger.info(f"📅 Server time: {datetime.utcnow().isoformat()}")
    yield
    logger.info("InspectAI Backend shutting down...")


app = FastAPI(
    title="InspectAI",
    description="Real-time AI-powered property inspection agent",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", ""),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# REST ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    return {"service": "InspectAI", "status": "running", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/sessions")
async def create_session(claim_type: str = "property_damage"):
    """Create a new inspection session."""
    session_id = str(uuid.uuid4())
    session_data = {
        "session_id": session_id,
        "claim_type": claim_type,
        "status": "created",
        "created_at": datetime.utcnow().isoformat(),
        "findings": [],
        "areas_inspected": [],
    }
    await firestore_service.create_session(session_id, session_data)
    logger.info(f"Created session: {session_id}")
    return session_data


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get inspection session details."""
    session = await firestore_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/api/sessions/{session_id}/findings")
async def get_findings(session_id: str):
    """Get all findings for a session."""
    findings = await firestore_service.get_findings(session_id)
    return {"session_id": session_id, "findings": findings, "count": len(findings)}


@app.post("/api/sessions/{session_id}/report")
async def generate_report(session_id: str):
    """Generate inspection report PDF for a session."""
    session = await firestore_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    findings = await firestore_service.get_findings(session_id)
    report_url = await report_generator.generate(session_id, session, findings)

    # Update session status
    await firestore_service.update_session(session_id, {
        "status": "report_generated",
        "report_url": report_url,
        "completed_at": datetime.utcnow().isoformat(),
    })

    return {"session_id": session_id, "report_url": report_url}


# =============================================================================
# WEBSOCKET — Real-time Inspection
# =============================================================================

@app.websocket("/ws/inspect/{session_id}")
async def websocket_inspection(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time inspection.
    
    Client sends:
      - {"type": "frame", "data": "<base64_jpeg>"}    → Camera frame
      - {"type": "audio", "data": "<base64_pcm>"}     → Audio chunk
      - {"type": "text", "data": "user message"}      → Text input
      - {"type": "end_inspection"}                      → End session
    
    Server sends:
      - {"type": "transcript", "text": "...", "speaker": "agent|user"}
      - {"type": "audio", "data": "<base64_pcm>"}     → Agent voice
      - {"type": "finding", "finding": {...}}          → New finding detected
      - {"type": "progress", "areas": [...], "completion": 45.0}
      - {"type": "report_ready", "url": "..."}
      - {"type": "error", "message": "..."}
    """
    handler = InspectionWebSocketHandler(
        websocket=websocket,
        session_id=session_id,
        firestore_service=firestore_service,
        storage_service=storage_service,
        report_generator=report_generator,
    )

    try:
        await handler.connect()
        await handler.run()
    except WebSocketDisconnect:
        logger.info(f"Client disconnected from session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error in session {session_id}: {e}")
    finally:
        await handler.disconnect()


# =============================================================================
# ERROR HANDLING
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

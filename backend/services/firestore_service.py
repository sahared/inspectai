"""
Firestore Service
Manages inspection sessions, findings, and data persistence.
"""

import os
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Flag to use in-memory store for local dev without Firestore
USE_MEMORY_STORE = os.getenv("USE_MEMORY_STORE", "false").lower() == "true"


class FirestoreService:
    """
    Handles all Firestore operations for InspectAI.
    
    Collections:
    - sessions/{session_id}           → Session metadata
    - sessions/{session_id}/findings  → Individual findings
    """

    def __init__(self):
        if USE_MEMORY_STORE:
            logger.info("Using in-memory store (Firestore disabled)")
            self.db = None
            self._memory_store = {}  # session_id -> session_data
            self._findings_store = {}  # session_id -> [findings]
        else:
            try:
                from google.cloud import firestore
                self.db = firestore.AsyncClient()
                self._memory_store = None
                self._findings_store = None
                logger.info("Firestore client initialized")
            except Exception as e:
                logger.warning(
                    f"Firestore unavailable ({e}), falling back to in-memory store"
                )
                self.db = None
                self._memory_store = {}
                self._findings_store = {}

    # =========================================================================
    # Sessions
    # =========================================================================

    async def create_session(self, session_id: str, data: dict):
        """Create a new inspection session."""
        if self.db:
            doc_ref = self.db.collection("sessions").document(session_id)
            await doc_ref.set(data)
        else:
            self._memory_store[session_id] = data
            self._findings_store[session_id] = []
        logger.info(f"Session created: {session_id}")

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get session by ID."""
        if self.db:
            doc_ref = self.db.collection("sessions").document(session_id)
            doc = await doc_ref.get()
            return doc.to_dict() if doc.exists else None
        else:
            return self._memory_store.get(session_id)

    async def update_session(self, session_id: str, updates: dict):
        """Update session fields."""
        if self.db:
            doc_ref = self.db.collection("sessions").document(session_id)
            await doc_ref.update(updates)
        else:
            if session_id in self._memory_store:
                self._memory_store[session_id].update(updates)
        logger.debug(f"Session updated: {session_id}")

    async def delete_session(self, session_id: str):
        """Delete a session and all its findings."""
        if self.db:
            # Delete findings subcollection
            findings_ref = (
                self.db.collection("sessions")
                .document(session_id)
                .collection("findings")
            )
            async for doc in findings_ref.stream():
                await doc.reference.delete()
            # Delete session
            await self.db.collection("sessions").document(session_id).delete()
        else:
            self._memory_store.pop(session_id, None)
            self._findings_store.pop(session_id, None)

    # =========================================================================
    # Findings
    # =========================================================================

    async def add_finding(self, session_id: str, finding: dict):
        """Add a finding to a session."""
        if self.db:
            findings_ref = (
                self.db.collection("sessions")
                .document(session_id)
                .collection("findings")
            )
            await findings_ref.add(finding)
        else:
            if session_id not in self._findings_store:
                self._findings_store[session_id] = []
            self._findings_store[session_id].append(finding)
        logger.info(
            f"Finding added to session {session_id}: "
            f"#{finding.get('evidence_number')} - {finding.get('damage_type')}"
        )

    async def get_findings(self, session_id: str) -> list:
        """Get all findings for a session."""
        if self.db:
            findings_ref = (
                self.db.collection("sessions")
                .document(session_id)
                .collection("findings")
            )
            findings = []
            async for doc in findings_ref.stream():
                findings.append(doc.to_dict())
            # Sort by evidence number
            findings.sort(key=lambda f: f.get("evidence_number", 0))
            return findings
        else:
            findings = self._findings_store.get(session_id, [])
            findings.sort(key=lambda f: f.get("evidence_number", 0))
            return findings

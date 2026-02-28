"""
Gemini Live API Service
Manages real-time bidirectional streaming with Gemini 2.0 Flash.
"""

import os
import json
import asyncio
import base64
import logging
from typing import AsyncGenerator, Callable, Optional

from google import genai
from google.genai import types

from agent.prompts import INSPECTOR_SYSTEM_PROMPT
from agent.tools import get_tool_declarations, InspectionToolHandler

logger = logging.getLogger(__name__)

# Model configuration
MODEL_ID = "gemini-2.0-flash-live"


def get_client():
    """Initialize the Gemini client."""
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    if api_key:
        # Using API key (Google AI Studio)
        return genai.Client(api_key=api_key)
    else:
        # Using Vertex AI (Google Cloud) — auto-detects credentials
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        return genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )


def get_live_config():
    """Build the Live API configuration."""
    return types.LiveConnectConfig(
        response_modalities=["AUDIO", "TEXT"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Aoede"  # Professional, calm voice
                )
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part(text=INSPECTOR_SYSTEM_PROMPT)]
        ),
        tools=[{"function_declarations": get_tool_declarations()}],
    )


class GeminiLiveSession:
    """
    Manages a single Gemini Live API session for an inspection.
    
    Handles:
    - Sending camera frames (vision)
    - Sending audio chunks (speech)
    - Receiving text transcripts
    - Receiving audio responses
    - Processing tool calls (evidence capture, etc.)
    """

    def __init__(
        self,
        session_id: str,
        tool_handler: InspectionToolHandler,
        on_text: Optional[Callable] = None,
        on_audio: Optional[Callable] = None,
        on_finding: Optional[Callable] = None,
        on_tool_result: Optional[Callable] = None,
    ):
        self.session_id = session_id
        self.tool_handler = tool_handler
        self.on_text = on_text
        self.on_audio = on_audio
        self.on_finding = on_finding
        self.on_tool_result = on_tool_result

        self.client = get_client()
        self.config = get_live_config()
        self.session = None
        self.is_connected = False
        self._receive_task = None

    async def connect(self):
        """Establish connection to Gemini Live API."""
        try:
            self.session = self.client.aio.live.connect(
                model=MODEL_ID,
                config=self.config,
            )
            # Enter the async context manager
            self._live_session = await self.session.__aenter__()
            self.is_connected = True
            logger.info(f"Gemini Live session connected for {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to connect to Gemini Live API: {e}")
            raise

    async def disconnect(self):
        """Close the Gemini Live API session."""
        self.is_connected = False
        if self.session:
            try:
                await self.session.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing Gemini session: {e}")
        logger.info(f"Gemini Live session disconnected for {self.session_id}")

    async def send_frame(self, frame_data: bytes):
        """
        Send a camera frame to the Gemini Live API.
        
        Args:
            frame_data: JPEG image bytes
        """
        if not self.is_connected:
            return

        try:
            await self._live_session.send(
                input=types.LiveClientContent(
                    turns=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    inline_data=types.Blob(
                                        mime_type="image/jpeg",
                                        data=frame_data,
                                    )
                                )
                            ],
                        )
                    ]
                )
            )
        except Exception as e:
            logger.error(f"Error sending frame: {e}")

    async def send_audio(self, audio_data: bytes):
        """
        Send an audio chunk to the Gemini Live API.
        
        Args:
            audio_data: Raw PCM audio bytes (16kHz, 16-bit, mono)
        """
        if not self.is_connected:
            return

        try:
            await self._live_session.send(
                input=types.LiveClientRealtimeInput(
                    media_chunks=[
                        types.Blob(
                            mime_type="audio/pcm;rate=16000",
                            data=audio_data,
                        )
                    ]
                )
            )
        except Exception as e:
            logger.error(f"Error sending audio: {e}")

    async def send_text(self, text: str):
        """
        Send a text message to the Gemini Live API.
        
        Args:
            text: User's text message
        """
        if not self.is_connected:
            return

        try:
            await self._live_session.send(
                input=types.LiveClientContent(
                    turns=[
                        types.Content(
                            role="user",
                            parts=[types.Part(text=text)],
                        )
                    ]
                )
            )
        except Exception as e:
            logger.error(f"Error sending text: {e}")

    async def receive_responses(self):
        """
        Continuously receive and process responses from Gemini.
        This runs as a long-lived async task.
        """
        try:
            async for response in self._live_session.receive():
                await self._process_response(response)
        except Exception as e:
            if self.is_connected:
                logger.error(f"Error receiving responses: {e}")

    async def _process_response(self, response):
        """Process a single response from the Gemini Live API."""
        try:
            # Handle server content (text and audio)
            if hasattr(response, 'server_content') and response.server_content:
                content = response.server_content
                if hasattr(content, 'model_turn') and content.model_turn:
                    for part in content.model_turn.parts:
                        # Text response
                        if hasattr(part, 'text') and part.text:
                            if self.on_text:
                                await self.on_text(part.text)

                        # Audio response
                        if hasattr(part, 'inline_data') and part.inline_data:
                            if self.on_audio:
                                await self.on_audio(part.inline_data.data)

            # Handle tool calls
            if hasattr(response, 'tool_call') and response.tool_call:
                await self._handle_tool_calls(response.tool_call)

        except Exception as e:
            logger.error(f"Error processing response: {e}")

    async def _handle_tool_calls(self, tool_call):
        """Process tool calls from the agent and send results back."""
        function_responses = []

        for fc in tool_call.function_calls:
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}

            logger.info(f"Agent calling tool: {tool_name} with args: {tool_args}")

            # Execute the tool
            result = await self.tool_handler.handle_tool_call(tool_name, tool_args)

            # Notify about findings
            if tool_name == "capture_evidence" and self.on_finding:
                await self.on_finding(result)

            # Notify about tool results
            if self.on_tool_result:
                await self.on_tool_result(tool_name, result)

            function_responses.append(
                types.FunctionResponse(
                    name=tool_name,
                    response=result,
                )
            )

        # Send tool results back to Gemini
        if function_responses:
            try:
                await self._live_session.send(
                    input=types.LiveClientToolResponse(
                        function_responses=function_responses
                    )
                )
            except Exception as e:
                logger.error(f"Error sending tool responses: {e}")

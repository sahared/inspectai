import os
import asyncio
import logging
from google import genai
from google.genai import types
from agent.prompts import INSPECTOR_SYSTEM_PROMPT
from agent.tools import get_tool_declarations, InspectionToolHandler

logger = logging.getLogger(__name__)
MODEL_ID = "gemini-2.0-flash-exp-image-generation"

def get_client():
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    else:
        return genai.Client(vertexai=True, project=os.getenv("GOOGLE_CLOUD_PROJECT"), location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))

def get_live_config():
    return types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=types.Content(parts=[types.Part(text=INSPECTOR_SYSTEM_PROMPT)]),
        tools=[{"function_declarations": get_tool_declarations()}],
    )

class GeminiLiveSession:
    def __init__(self, session_id, tool_handler, on_text=None, on_turn_complete=None, on_finding=None, on_tool_result=None):
        self.session_id = session_id
        self.tool_handler = tool_handler
        self.on_text = on_text
        self.on_turn_complete = on_turn_complete
        self.on_finding = on_finding
        self.on_tool_result = on_tool_result
        self.client = get_client()
        self.config = get_live_config()
        self._ctx = None
        self._live_session = None
        self.is_connected = False

    async def connect(self):
        try:
            self._ctx = self.client.aio.live.connect(model=MODEL_ID, config=self.config)
            self._live_session = await self._ctx.__aenter__()
            self.is_connected = True
            logger.info(f"Gemini Live connected for {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise

    async def disconnect(self):
        self.is_connected = False
        if self._ctx:
            try:
                await self._ctx.__aexit__(None, None, None)
            except:
                pass
        logger.info(f"Gemini Live disconnected for {self.session_id}")

    async def send_frame(self, frame_data):
        if not self.is_connected or not self._live_session:
            return
        try:
            await self._live_session.send_client_content(
                turns=types.Content(role="user", parts=[
                    types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=frame_data)),
                    types.Part(text="Analyze this camera frame. If you see any damage, log it with capture_evidence. Be brief."),
                ])
            )
        except Exception as e:
            logger.error(f"Error sending frame: {e}")

    async def send_text(self, text):
        if not self.is_connected or not self._live_session:
            return
        try:
            await self._live_session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=text)])
            )
        except Exception as e:
            logger.error(f"Error sending text: {e}")

    async def send_frame_and_text(self, frame_data, text):
        if not self.is_connected or not self._live_session:
            return
        try:
            await self._live_session.send_client_content(
                turns=types.Content(role="user", parts=[
                    types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=frame_data)),
                    types.Part(text=text),
                ])
            )
        except Exception as e:
            logger.error(f"Error sending frame+text: {e}")

    async def receive_responses(self):
        if not self._live_session:
            return
        try:
            while self.is_connected:
                async for response in self._live_session.receive():
                    await self._process_response(response)
        except Exception as e:
            if self.is_connected:
                logger.error(f"Error receiving: {e}")

    async def _process_response(self, response):
        try:
            if response.server_content:
                if response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.text and self.on_text:
                            await self.on_text(part.text)
                if response.server_content.turn_complete:
                    if self.on_turn_complete:
                        await self.on_turn_complete()
            if response.tool_call:
                await self._handle_tool_calls(response.tool_call)
        except Exception as e:
            logger.error(f"Error processing response: {e}")

    async def _handle_tool_calls(self, tool_call):
        function_responses = []
        for fc in tool_call.function_calls:
            tool_args = dict(fc.args) if fc.args else {}
            logger.info(f"Tool call: {fc.name} args: {tool_args}")
            result = await self.tool_handler.handle_tool_call(fc.name, tool_args)
            if fc.name == "capture_evidence" and self.on_finding:
                await self.on_finding(result)
            if self.on_tool_result:
                await self.on_tool_result(fc.name, result)
            function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
        if function_responses and self._live_session:
            try:
                await self._live_session.send_tool_response(function_responses=function_responses)
            except Exception as e:
                logger.error(f"Error sending tool response: {e}")

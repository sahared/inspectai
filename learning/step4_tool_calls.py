import asyncio
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL = "gemini-2.5-flash-native-audio-latest"

TOOLS = [{"function_declarations": [
    {
        "name": "capture_evidence",
        "description": "Log an inspection finding. Call this for EVERY piece of damage identified.",
        "parameters": {
            "type": "object",
            "properties": {
                "evidence_number": {"type": "integer", "description": "Sequential number"},
                "room": {"type": "string", "description": "Room where damage was found"},
                "damage_type": {"type": "string", "description": "Type of damage"},
                "severity": {"type": "string", "enum": ["minor", "moderate", "severe", "critical"]},
                "description": {"type": "string", "description": "Detailed description"},
            },
            "required": ["evidence_number", "room", "damage_type", "severity", "description"],
        },
    },
]}]

findings = []

def handle_capture(args):
    findings.append({**args, "timestamp": datetime.utcnow().isoformat()})
    sev = args.get("severity", "?").upper()
    print(f"\n   EVIDENCE #{args.get('evidence_number','?')} [{sev}]")
    print(f"   Room: {args.get('room','?')}")
    print(f"   Type: {args.get('damage_type','?')}")
    print(f"   Desc: {args.get('description','')[:120]}")
    return {"status": "captured", "evidence_number": args.get("evidence_number"), "total": len(findings)}

SYSTEM_PROMPT = """You are InspectAI, a professional property damage inspector.
You have a tool called capture_evidence. You MUST call it for every piece of damage the user describes.
Never use markdown. Keep spoken responses under 3 sentences."""

async def main():
    print("Connecting with tools enabled...")
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
            )
        ),
        system_instruction=types.Content(parts=[types.Part(text=SYSTEM_PROMPT)]),
        tools=TOOLS,
    )

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("Connected!\n")

        messages = [
            "Hi, inspect my kitchen. There is a large brown water stain on the ceiling, about 2 feet wide, with bubbling paint.",
            "I also see dark spots near the baseboard under the sink. It smells musty, could be mold.",
            "That is all in the kitchen. Give me a summary of what you found.",
        ]

        for msg in messages:
            print(f"\n{'='*60}")
            print(f"You: {msg}")
            print(f"{'='*60}")

            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=msg)])
            )

            done = False
            while not done:
                async for response in session.receive():
                    if response.server_content:
                        if response.server_content.model_turn:
                            for part in response.server_content.model_turn.parts:
                                if part.text:
                                    print(f"\nAgent: {part.text}")
                        if response.server_content.turn_complete:
                            done = True
                            break

                    if response.tool_call:
                        print("\nTOOL CALL DETECTED!")
                        func_responses = []
                        for fc in response.tool_call.function_calls:
                            args = dict(fc.args) if fc.args else {}
                            result = handle_capture(args)
                            func_responses.append(
                                types.FunctionResponse(
                                    id=fc.id,
                                    name=fc.name,
                                    response=result,
                                )
                            )
                        await session.send_tool_response(function_responses=func_responses)
                        break

        print(f"\n{'='*60}")
        print(f"RESULTS: {len(findings)} findings captured")
        print(f"{'='*60}")
        for f in findings:
            print(f"  #{f.get('evidence_number','?')} [{f.get('severity','?').upper()}] {f.get('damage_type','?')} in {f.get('room','?')}")
        print(f"\nStep 4 done! Tool calling works!")

if __name__ == "__main__":
    asyncio.run(main())

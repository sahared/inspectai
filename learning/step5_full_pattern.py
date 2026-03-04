import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# This model supports bidi + vision + tools together
MODEL = "gemini-2.0-flash-exp-image-generation"

TOOLS = [{"function_declarations": [{
    "name": "capture_evidence",
    "description": "Log an inspection finding. Call for EVERY piece of damage you see.",
    "parameters": {
        "type": "object",
        "properties": {
            "evidence_number": {"type": "integer", "description": "Sequential number"},
            "room": {"type": "string", "description": "Room/area name"},
            "damage_type": {"type": "string", "description": "Type of damage"},
            "severity": {"type": "string", "enum": ["minor", "moderate", "severe", "critical"]},
            "description": {"type": "string", "description": "Detailed description"},
        },
        "required": ["evidence_number", "room", "damage_type", "severity", "description"],
    },
}]}]

findings = []

def handle_tool(name, args):
    if name == "capture_evidence":
        findings.append({**args, "timestamp": datetime.utcnow().isoformat()})
        sev = args.get("severity", "?").upper()
        print(f"\n   EVIDENCE #{args.get('evidence_number','?')} [{sev}]: {args.get('description','')[:100]}")
        return {"status": "captured", "evidence_number": args.get("evidence_number"), "total": len(findings)}
    return {"error": f"Unknown tool: {name}"}

SYSTEM_PROMPT = """You are InspectAI, a professional AI property damage inspector.
When you receive images or damage descriptions:
1. Identify ALL damage visible
2. For EACH piece of damage, call capture_evidence to log it
3. Describe what you see concisely
4. Ask what to inspect next
Keep responses under 3 sentences. Be specific about damage type and severity."""

async def send_and_process(session, parts, label=""):
    if label:
        print(f"\n{'='*60}")
        print(f"You: {label}")
        print(f"{'='*60}")

    await session.send_client_content(turns=types.Content(role="user", parts=parts))

    done = False
    while not done:
        async for response in session.receive():
            if response.server_content:
                if response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.text:
                            print(f"\nInspectAI: {part.text}")
                if response.server_content.turn_complete:
                    done = True
                    break

            if response.tool_call:
                print("\nTOOL CALL!")
                func_responses = []
                for fc in response.tool_call.function_calls:
                    args = dict(fc.args) if fc.args else {}
                    result = handle_tool(fc.name, args)
                    func_responses.append(
                        types.FunctionResponse(id=fc.id, name=fc.name, response=result)
                    )
                await session.send_tool_response(function_responses=func_responses)
                break

async def main():
    print("InspectAI — FULL PATTERN TEST")
    print("Vision + Conversation + Tool Calls")
    print("="*60)

    config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=types.Content(parts=[types.Part(text=SYSTEM_PROMPT)]),
        tools=TOOLS,
    )

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("Connected!\n")

        # A: Start inspection
        await send_and_process(session, [
            types.Part(text="Hi InspectAI, I need to inspect water damage from a storm in my kitchen and bathroom.")
        ], label="Starting inspection")

        # B: Send image + tools
        image_path = "test_damage.jpg"
        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                image_data = f.read()
            await send_and_process(session, [
                types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=image_data)),
                types.Part(text="Here is the kitchen ceiling. What damage do you see? Log everything with capture_evidence."),
            ], label=f"Sending kitchen image ({len(image_data):,} bytes)")
        else:
            await send_and_process(session, [
                types.Part(text="Kitchen ceiling: large circular brown water stain, 2 feet wide, paint bubbling, slow drip.")
            ], label="Describing kitchen ceiling")

        # C: Interrupt with new finding
        await send_and_process(session, [
            types.Part(text="Wait, there is also a diagonal crack along the wall near the window. About 6 inches long.")
        ], label="Interrupting with new finding")

        # D: Move to bathroom
        await send_and_process(session, [
            types.Part(text="Moving to the bathroom. Dark spots on the wall near the tub. Smells musty.")
        ], label="Moving to bathroom")

        # E: Summary
        await send_and_process(session, [
            types.Part(text="That is everything. Summarize all findings.")
        ], label="Requesting summary")

    # Results
    print(f"\n{'='*60}")
    print(f"FULL INSPECTION RESULTS")
    print(f"{'='*60}")
    print(f"Total evidence items: {len(findings)}\n")
    for f in findings:
        sev = f.get("severity", "?").upper()
        room = f.get("room", "?")
        dtype = f.get("damage_type", "?")
        desc = f.get("description", "")[:120]
        print(f"  #{f.get('evidence_number','?')} [{sev}] {dtype} in {room}")
        print(f"     {desc}\n")

    print("FULL PATTERN TEST COMPLETE!")
    print("\nDay 2 Summary — Models for InspectAI:")
    print("  Voice conversations: gemini-2.5-flash-native-audio-latest")
    print("  Vision + Tools:      gemini-2.0-flash-exp-image-generation")
    print("\nReady for Day 3!")

if __name__ == "__main__":
    asyncio.run(main())

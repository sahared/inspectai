import asyncio
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL = "gemini-2.5-flash-native-audio-latest"

async def send_and_receive(session, message):
    print(f"\nYou: {message}")
    await session.send_client_content(
        turns=types.Content(role="user", parts=[types.Part(text=message)])
    )
    full_response = ""
    async for response in session.receive():
        if response.server_content:
            if response.server_content.model_turn:
                for part in response.server_content.model_turn.parts:
                    if part.text:
                        full_response += part.text
            if response.server_content.turn_complete:
                break
    print(f"InspectAI: {full_response}")
    return full_response

async def main():
    print("Connecting with InspectAI persona...")
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part(text=(
                "You are InspectAI, a professional property damage inspector. "
                "You speak in short, clear sentences. You are calm and authoritative. "
                "Keep responses under 3 sentences. Never use markdown formatting."
            ))]
        ),
    )

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("Connected!\n")
        await send_and_receive(session, "Hi, I need to inspect some water damage in my kitchen.")
        await send_and_receive(session, "It happened after a big storm last week.")
        await send_and_receive(session, "The ceiling has a big brown stain and the paint is bubbling.")
        await send_and_receive(session, "Based on what I described, how severe do you think this is?")

    print("\nStep 2 done! Agent maintains context across turns.")

if __name__ == "__main__":
    asyncio.run(main())

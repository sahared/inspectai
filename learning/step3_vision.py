import asyncio
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL = "gemini-2.5-flash-native-audio-latest"

SYSTEM_PROMPT = """You are InspectAI, a professional property damage inspector.
When you see an image, identify all damage: type, location, severity.
Ask what to inspect next. Never use markdown. Keep it concise."""

async def main():
    print("Connecting with vision enabled...")
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
            )
        ),
        system_instruction=types.Content(parts=[types.Part(text=SYSTEM_PROMPT)]),
    )

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("Connected!\n")

        image_path = "test_damage.jpg"
        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                image_data = f.read()
            print(f"Sending image: {image_path} ({len(image_data):,} bytes)\n")

            await session.send_client_content(
                turns=types.Content(role="user", parts=[
                    types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=image_data)),
                    types.Part(text="I just pointed my camera at this area. What damage do you see?"),
                ])
            )
        else:
            print("No test_damage.jpg found. Using text description instead.\n")
            await session.send_client_content(
                turns=types.Content(role="user", parts=[
                    types.Part(text="I see a large circular brown water stain on my kitchen ceiling, about 2 feet wide. Paint is bubbling in the center.")
                ])
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

        # Follow-up
        print("\nYou: Rate the severity and tell me what to show you next.")
        await session.send_client_content(
            turns=types.Content(role="user", parts=[
                types.Part(text="Rate the severity as minor, moderate, or severe. What should I show you next?")
            ])
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

    print("\nStep 3 done! Agent can analyze images!")

if __name__ == "__main__":
    asyncio.run(main())

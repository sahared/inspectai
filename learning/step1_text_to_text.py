import asyncio
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL = "gemini-2.5-flash-native-audio-latest"

async def main():
    print("Connecting to Gemini Live API...")
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Aoede"
                )
            )
        ),
    )

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("Connected!\n")
        message = "Hello! Say one sentence about what you can do."
        print(f"You: {message}\n")

        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=message)])
        )

        print("Waiting for response...")
        audio_chunks = 0
        text_parts = []
        async for response in session.receive():
            if response.server_content:
                if response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.text:
                            text_parts.append(part.text)
                            print(f"Text: {part.text}")
                        if part.inline_data:
                            audio_chunks += 1
                if response.server_content.turn_complete:
                    break

        print(f"\nReceived {audio_chunks} audio chunks")
        if text_parts:
            print(f"Text response: {''.join(text_parts)}")
        else:
            print("(Audio-only response - agent spoke but text not included)")
        print("\nStep 1 COMPLETE! The Live API works!")

if __name__ == "__main__":
    asyncio.run(main())

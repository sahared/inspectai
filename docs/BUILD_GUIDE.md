# InspectAI — Baby Step-by-Step Build Guide

This guide walks you through every single step to go from zero to a deployed,
working InspectAI submission. Follow in order.

---

## 🗓️ DAY 1: Setup Everything

### Step 1.1: Create Accounts (15 min)

1. **Devpost**: Go to https://geminiliveagentchallenge.devpost.com
   - Create account if you don't have one
   - Click "Register" for the hackathon

2. **Google Cloud**: Go to https://cloud.google.com/free
   - Sign up for free tier OR use existing account
   - Request $100 hackathon credits: https://forms.gle/rKNPXA1o6XADvQGb7
   - Credits take up to 72 business hours — request NOW

3. **Google Developer Group** (bonus points):
   - Go to https://developers.google.com/community/gdg
   - Find and join a local chapter
   - Save your public profile link

### Step 1.2: Get Your API Key (10 min)

1. Go to https://aistudio.google.com/apikey
2. Click "Create API key"
3. Select or create a Google Cloud project
4. Copy the key — save it somewhere safe
5. Test it works:
   ```bash
   curl "https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_API_KEY"
   ```
   You should see a JSON list of models.

### Step 1.3: Set Up GitHub Repo (10 min)

1. Create a new public repo: `inspectai`
2. Clone it locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/inspectai.git
   cd inspectai
   ```
3. Copy ALL the project files I've provided into this repo
4. Initial commit:
   ```bash
   git add .
   git commit -m "Initial project structure"
   git push
   ```

### Step 1.4: Set Up Local Development (20 min)

```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
# Edit .env:
#   GOOGLE_API_KEY=your-key-here
#   USE_MEMORY_STORE=true

# Test the backend starts
uvicorn main:app --reload --port 8080
# Visit http://localhost:8080 — should see {"service":"InspectAI","status":"running"}
# Ctrl+C to stop

# Frontend setup (new terminal)
cd frontend
npm install

# Test the frontend starts
npm run dev
# Visit http://localhost:5173 — should see the InspectAI welcome screen
```

**✅ Day 1 Checkpoint**: Both backend and frontend run locally. API key works.

---

## 🗓️ DAY 2: Learn the Gemini Live API

### Step 2.1: Read the Documentation (1 hour)

Go through these resources from the hackathon page:
1. **ADK Bidi-streaming in 5 minutes** — essential starting point
2. **A Visual Guide to Real-Time Multimodal AI Agent Development**
3. **ADK Bidi-streaming development guide**

### Step 2.2: Run a Basic Test (30 min)

Create a simple test script to verify the Live API works:

```python
# test_gemini_live.py
import asyncio
from google import genai
from google.genai import types

client = genai.Client(api_key="YOUR_API_KEY")

async def test():
    config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=types.Content(
            parts=[types.Part(text="You are a helpful assistant. Keep responses short.")]
        ),
    )

    async with client.aio.live.connect(
        model="gemini-2.0-flash-live",
        config=config,
    ) as session:
        # Send a text message
        await session.send(
            input=types.LiveClientContent(
                turns=[types.Content(
                    role="user",
                    parts=[types.Part(text="Hello! Describe what you can do.")]
                )]
            )
        )

        # Receive response
        async for response in session.receive():
            if hasattr(response, 'server_content') and response.server_content:
                content = response.server_content
                if hasattr(content, 'model_turn') and content.model_turn:
                    for part in content.model_turn.parts:
                        if hasattr(part, 'text') and part.text:
                            print(f"Agent: {part.text}")
                # Check if turn is complete
                if hasattr(content, 'turn_complete') and content.turn_complete:
                    break

asyncio.run(test())
```

Run it:
```bash
python test_gemini_live.py
```

### Step 2.3: Test with an Image (30 min)

```python
# test_gemini_vision.py
import asyncio
import base64
from google import genai
from google.genai import types

client = genai.Client(api_key="YOUR_API_KEY")

async def test_vision():
    config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=types.Content(
            parts=[types.Part(text="You are a property inspector. Describe any damage you see.")]
        ),
    )

    # Load a test image (use any image of property damage)
    with open("test_damage.jpg", "rb") as f:
        image_data = f.read()

    async with client.aio.live.connect(
        model="gemini-2.0-flash-live",
        config=config,
    ) as session:
        # Send image
        await session.send(
            input=types.LiveClientContent(
                turns=[types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="image/jpeg",
                                data=image_data,
                            )
                        ),
                        types.Part(text="What damage do you see in this image?")
                    ]
                )]
            )
        )

        async for response in session.receive():
            if hasattr(response, 'server_content') and response.server_content:
                content = response.server_content
                if hasattr(content, 'model_turn') and content.model_turn:
                    for part in content.model_turn.parts:
                        if hasattr(part, 'text') and part.text:
                            print(f"Inspector: {part.text}")
                if hasattr(content, 'turn_complete') and content.turn_complete:
                    break

asyncio.run(test_vision())
```

Find a test image: search Google Images for "water damage ceiling" and save one.

**✅ Day 2 Checkpoint**: You can send text and images to Gemini Live API and get responses.

---

## 🗓️ DAY 3-4: Build the Backend

### Step 3.1: Test the Agent System Prompt (Day 3, 1 hour)

The system prompt in `backend/agent/prompts.py` is already written. Test it:

1. Modify your test script to use the full `INSPECTOR_SYSTEM_PROMPT`
2. Send a few test images and verify the agent:
   - Introduces itself professionally
   - Identifies damage accurately
   - Asks follow-up questions
   - Uses the right tone

3. **Iterate on the prompt** until it feels right. This is the most important tuning.

### Step 3.2: Test Tool Calls (Day 3, 1 hour)

Add the tools to your test:

```python
from agent.tools import get_tool_declarations

config = types.LiveConnectConfig(
    response_modalities=["TEXT"],
    system_instruction=types.Content(
        parts=[types.Part(text=INSPECTOR_SYSTEM_PROMPT)]
    ),
    tools=[{"function_declarations": get_tool_declarations()}],
)
```

Verify the agent calls `capture_evidence` when it identifies damage.

### Step 3.3: Run the Full Backend (Day 4, 2 hours)

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8080
```

Test the REST endpoints:
```bash
# Create a session
curl -X POST http://localhost:8080/api/sessions?claim_type=property_damage

# Health check
curl http://localhost:8080/health
```

Test the WebSocket with a simple client (wscat or browser console):
```bash
npm install -g wscat
wscat -c ws://localhost:8080/ws/inspect/test-session-123
```

Send a test message:
```json
{"type": "text", "data": "Hello, I need to inspect water damage in my kitchen"}
```

**✅ Day 3-4 Checkpoint**: Backend WebSocket works. Agent responds to text and images via API.

---

## 🗓️ DAY 5-6: Build the Frontend

### Step 5.1: Get Camera Working (Day 5, 1 hour)

The React app in `frontend/src/App.jsx` is complete. Start it:

```bash
cd frontend
npm run dev
```

1. Open http://localhost:5173
2. Click "Start Inspection"
3. Allow camera and microphone permissions
4. Verify you see the camera feed full-screen

### Step 5.2: Connect Frontend to Backend (Day 5, 2 hours)

1. Make sure backend is running on port 8080
2. Frontend should auto-connect via WebSocket
3. Verify in browser console: no WebSocket errors
4. You should see "Connected to InspectAI" status

If the WebSocket connection fails, check:
- Backend is running on the right port
- CORS settings in `backend/main.py` include `http://localhost:5173`
- No firewall blocking WebSocket connections

### Step 5.3: Test Full Flow (Day 6, 2 hours)

1. Start backend: `uvicorn main:app --reload --port 8080`
2. Start frontend: `cd frontend && npm run dev`
3. Open on your phone (use your computer's IP: `http://192.168.x.x:5173`)
4. Start an inspection
5. Point camera at something and talk
6. Verify:
   - Agent responds (voice and/or text)
   - Findings appear in the overlay
   - Interrupting the agent works
   - End inspection generates a report

### Troubleshooting Common Issues

| Issue | Fix |
|-------|-----|
| Camera doesn't start | Check HTTPS (Chrome requires HTTPS for camera on non-localhost) |
| No audio from agent | Check AudioContext autoplay policy — user needs to interact first |
| WebSocket drops | Add reconnection logic, check timeout settings |
| Agent doesn't see images | Verify frame capture is sending base64 JPEG, check frame size |
| Agent responses are slow | Reduce frame rate (1 FPS), reduce image quality |

**✅ Day 5-6 Checkpoint**: Full end-to-end flow works locally. Camera + voice + agent + findings.

---

## 🗓️ DAY 7-8: Polish & Edge Cases

### Day 7: Improve the Experience

- [ ] Test with different types of "damage" (use printed photos, images on a tablet, etc.)
- [ ] Test barge-in: interrupt the agent mid-sentence, verify it handles gracefully
- [ ] Test poor lighting: does the agent ask you to adjust?
- [ ] Test shaky camera: does the agent ask you to hold steady?
- [ ] Test long inspection (10+ minutes): does connection stay stable?
- [ ] Verify findings are saved correctly (check Firestore or in-memory store)
- [ ] Verify report PDF generates correctly

### Day 8: Frontend Polish

- [ ] Ensure mobile responsiveness (test on actual phone)
- [ ] Smooth transitions between screens
- [ ] Clear error messages
- [ ] Loading states
- [ ] Findings panel animation
- [ ] Safety alert visibility

**✅ Day 7-8 Checkpoint**: App is polished and handles edge cases.

---

## 🗓️ DAY 9-10: Deploy to Google Cloud

### Step 9.1: Quick Deployment (Day 9)

**Option A: Use the deploy script** (recommended):
```bash
chmod +x deploy.sh
./deploy.sh
```
Follow the prompts.

**Option B: Manual deployment**:
```bash
# 1. Build Docker image
docker build -t inspectai-backend .

# 2. Tag for Google Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev
docker tag inspectai-backend us-central1-docker.pkg.dev/YOUR_PROJECT/inspectai/backend:latest

# 3. Push
docker push us-central1-docker.pkg.dev/YOUR_PROJECT/inspectai/backend:latest

# 4. Deploy to Cloud Run
gcloud run deploy inspectai-backend \
  --image=us-central1-docker.pkg.dev/YOUR_PROJECT/inspectai/backend:latest \
  --region=us-central1 \
  --allow-unauthenticated \
  --port=8080 \
  --set-env-vars="GOOGLE_API_KEY=YOUR_KEY,USE_MEMORY_STORE=false"
```

### Step 9.2: Verify Deployment (Day 9)

```bash
# Get your Cloud Run URL
gcloud run services describe inspectai-backend --region=us-central1 --format='value(status.url)'

# Test health endpoint
curl https://YOUR-CLOUD-RUN-URL/health
```

### Step 9.3: Deploy Frontend (Day 10)

Option A: Deploy to Firebase Hosting:
```bash
cd frontend
npm run build
firebase deploy --only hosting
```

Option B: Deploy to Cloud Run as well (as a static site container).

### Step 9.4: Record GCP Proof (Day 10, 15 min)

Open Google Cloud Console → Cloud Run → Show your service running.
Screen record:
1. The Cloud Run service page showing the backend is deployed
2. The service URL and status "Active"
3. The logs showing requests being processed
4. Firestore showing sessions collection
5. Cloud Storage showing evidence bucket

Save this recording — it's a required submission item.

**✅ Day 9-10 Checkpoint**: App is live on Google Cloud. GCP proof recorded.

---

## 🗓️ DAY 11-12: Submission Materials

### Step 11.1: Architecture Diagram (Day 11, 30 min)

1. Go to https://excalidraw.com
2. Create the architecture diagram showing:
   - User's Phone → WebSocket → Cloud Run → Gemini Live API
   - Cloud Run → Firestore (sessions)
   - Cloud Run → Cloud Storage (evidence)
   - Include logos for each GCP service
3. Export as PNG
4. Save to `docs/architecture.png`
5. Also add to your Devpost submission images

### Step 11.2: Demo Video Script & Recording (Day 11-12)

**Video Structure** (under 4 minutes):

| Timestamp | Content |
|-----------|---------|
| 0:00-0:30 | Hook + Problem statement |
| 0:30-0:45 | Solution overview |
| 0:45-3:15 | LIVE DEMO — real software working |
| 3:15-3:45 | Architecture diagram walkthrough |
| 3:45-4:00 | Closing + value proposition |

**Recording tips:**
- Use OBS Studio or screen recording
- Show REAL interactions, not mockups
- Demonstrate: damage detection, voice conversation, interruption handling, report generation
- Speak clearly and confidently
- Upload to YouTube (public or unlisted)

### Step 11.3: Blog Post (Day 12, 1 hour) — BONUS POINTS

Write a post on Medium or Dev.to covering:
- What you built and why
- How Gemini Live API works
- Architecture decisions
- Challenges and learnings
- Include: "This content was created for the Gemini Live Agent Challenge hackathon"
- Include #GeminiLiveAgentChallenge
- Share on Twitter/LinkedIn with the hashtag

**✅ Day 11-12 Checkpoint**: All submission materials ready.

---

## 🗓️ DAY 13-14: Submit

### Step 13.1: Write Devpost Description (Day 13)

Fill in all required fields on Devpost:
- **Summary**: 2-3 paragraphs about what InspectAI does
- **Technologies used**: Gemini 2.0 Flash, Live API, Google ADK, Cloud Run, Firestore, Cloud Storage
- **Features**: List all features
- **Learnings**: What you learned building this
- **Category**: Live Agents

### Step 13.2: Final Checklist (Day 14)

- [ ] Text description ✍️
- [ ] Category selected: Live Agents
- [ ] Public GitHub repo URL 🔗
- [ ] README has spin-up instructions
- [ ] Proof of GCP deployment video/screenshot 🖥️
- [ ] Architecture diagram (in images section) 🏗️
- [ ] Demo video URL (YouTube, under 4 min) 📹
- [ ] Blog post URL (bonus) 📝
- [ ] Terraform/deploy scripts in repo (bonus) 🚀
- [ ] GDG profile link (bonus) 👥

### Step 13.3: SUBMIT! 🎉

Go to https://geminiliveagentchallenge.devpost.com
Click "Enter a Submission"
Fill everything in
**Submit before March 16, 5:00 PM Pacific Time**

---

## 💡 Pro Tips

1. **Submit early, iterate later** — You can update until the deadline
2. **Test on mobile** — Judges may test on phones. Camera must work.
3. **The demo video matters enormously** — Spend real time on it
4. **Show barge-in explicitly** — Judges specifically look for interruption handling
5. **Show the agent being proactive** — Having the agent spot something the user didn't mention is the "wow" moment
6. **Keep the README clean** — First impressions count
7. **The system prompt is your secret weapon** — Iterate on it more than anything else

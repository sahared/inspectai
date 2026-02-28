# 🔍 InspectAI — Real-Time AI Property Inspection Agent

> **See More. Miss Nothing.**

InspectAI is a real-time AI agent that conducts property damage inspections through your phone camera. Point your camera at damage, have a natural conversation with your AI inspector, and receive a professional inspection report — all in minutes instead of days.

Built for the **Gemini Live Agent Challenge 2026** using Gemini 2.0 Flash Live API, Google ADK, and Google Cloud.

---

## 🎯 The Problem

Every year, millions of property damage claims are filed. The inspection process is broken:

- **Slow**: Average wait time for an insurance adjuster is 5-14 days
- **Expensive**: Each human inspection costs $500-$10,000
- **Inconsistent**: Two inspectors at the same property produce wildly different reports
- **Fraud-prone**: 10% of insurance claims involve some level of fraud

The US insurance industry spends **$40 billion annually** on claims processing, yet the core inspection process hasn't changed since the 1980s.

## 💡 The Solution

InspectAI turns any smartphone into a professional inspection tool:

1. **📹 SEES** — Analyzes your camera feed in real-time, identifying damage types, severity, and patterns
2. **🎤 SPEAKS** — Guides you conversationally through a thorough inspection, asking targeted questions
3. **🧠 THINKS** — Cross-references findings, connects damage across rooms, spots issues you'd miss
4. **📋 DOCUMENTS** — Automatically captures evidence, timestamps findings, generates a professional PDF report

**Result**: What takes 14 days and $2,000 now takes 15 minutes and costs under $5.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| **Real-Time Vision** | Continuous camera analysis via Gemini Live API — not photo uploads |
| **Voice Conversation** | Natural speech interaction with barge-in (interruption) support |
| **Proactive Detection** | Agent spots damage you haven't mentioned and flags it |
| **Cross-Room Intelligence** | Connects findings across areas ("This leak may be related to the ceiling stain downstairs") |
| **Smart Checklist** | Tracks inspection progress, prompts for missed areas |
| **Safety Alerts** | Flags hazards (exposed wiring, mold, structural concerns) in real-time |
| **Auto Report Generation** | Professional PDF with findings, severity ratings, evidence, and recommendations |

---

## 🏗️ Architecture

```
┌──────────────────────────────┐
│     User's Phone / Browser   │
│  Camera + Mic + React PWA    │
└──────────┬───────────────────┘
           │ WebSocket (frames + audio)
           ▼
┌──────────────────────────────────────────────┐
│              Google Cloud Run                 │
│  ┌─────────────────────────────────────────┐ │
│  │  FastAPI Backend                        │ │
│  │  ├── WebSocket Handler                  │ │
│  │  ├── Session Manager                    │ │
│  │  └── Report Generator                   │ │
│  └────────────┬────────────────────────────┘ │
│               │                              │
│  ┌────────────▼────────────────────────────┐ │
│  │     Gemini 2.0 Flash (Live API)         │ │
│  │  • Real-time vision analysis            │ │
│  │  • Conversational audio (barge-in)      │ │
│  │  • Tool calls (evidence, progress)      │ │
│  └─────────────────────────────────────────┘ │
│               │                              │
│  ┌────────────┼────────────────────────────┐ │
│  │ Firestore  │  Cloud Storage  │ Secrets  │ │
│  │ (sessions  │  (photos,       │ (API     │ │
│  │  findings) │   reports)      │  keys)   │ │
│  └────────────┴─────────────────┴──────────┘ │
└──────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| AI Model | **Gemini 2.0 Flash** (Live API) | Real-time vision + audio understanding |
| Agent | **Google GenAI SDK** | Agent tools, function calling, streaming |
| Backend | **Python + FastAPI** | WebSocket server, API endpoints |
| Frontend | **React + Vite + Tailwind** | Camera capture, audio streaming, UI |
| Database | **Cloud Firestore** | Session state, findings persistence |
| Storage | **Cloud Storage** | Evidence photos, generated reports |
| Hosting | **Cloud Run** | Serverless backend deployment |
| Secrets | **Secret Manager** | Secure API key storage |
| IaC | **Terraform** | Automated infrastructure deployment |
| Container | **Docker** | Reproducible builds |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Google Cloud account with Gemini API access
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

### Option 1: Local Development (Fastest)

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/inspectai.git
cd inspectai

# 2. Set up the backend
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env: add your GOOGLE_API_KEY and set USE_MEMORY_STORE=true

# 3. Start the backend
uvicorn main:app --reload --port 8080

# 4. In a new terminal, set up the frontend
cd frontend
npm install

# 5. Start the frontend
npm run dev

# 6. Open http://localhost:5173 in your browser
#    (For phone testing: use your computer's local IP)
```

### Option 2: Docker Compose

```bash
# 1. Clone and configure
git clone https://github.com/YOUR_USERNAME/inspectai.git
cd inspectai
cp backend/.env.example backend/.env
# Edit backend/.env with your API key

# 2. Run everything
docker-compose up

# 3. Open http://localhost:5173
```

### Option 3: Deploy to Google Cloud (Production)

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/inspectai.git
cd inspectai

# 2. Make the deploy script executable
chmod +x deploy.sh

# 3. Run one-click deployment
./deploy.sh
# Follow the prompts for project ID and API key
```

Or use Terraform:

```bash
cd terraform
terraform init
terraform apply -var="project_id=YOUR_PROJECT_ID"
```

---

## 📹 Demo

[▶️ Watch the demo video on YouTube](YOUR_YOUTUBE_LINK)

The demo shows:
1. Starting a real-time inspection of storm damage
2. The agent identifying water damage, guiding camera angles, and logging evidence
3. Barge-in handling — interrupting the agent mid-sentence
4. Proactive detection — agent spots damage the user didn't mention
5. Cross-room intelligence — connecting findings between areas
6. Automatic report generation with all findings

---

## 📂 Project Structure

```
inspectai/
├── backend/
│   ├── main.py                  # FastAPI server
│   ├── agent/
│   │   ├── prompts.py           # System prompt (agent personality)
│   │   └── tools.py             # Agent tools (evidence, progress, report)
│   ├── api/
│   │   └── websocket.py         # WebSocket handler
│   └── services/
│       ├── gemini_live.py       # Gemini Live API integration
│       ├── firestore_service.py # Database operations
│       ├── storage_service.py   # Cloud Storage operations
│       └── report_generator.py  # PDF report generation
├── frontend/
│   └── src/
│       └── App.jsx              # Full React application
├── terraform/                   # Infrastructure as Code
├── deploy.sh                    # One-click deployment
├── Dockerfile                   # Container build
└── docker-compose.yml           # Local development
```

---

## 🧪 How It Works

### 1. Real-Time Streaming
The frontend captures camera frames at 2 FPS and audio at 16kHz, streaming both over WebSocket to the backend. The backend forwards these to the Gemini Live API, which processes vision and audio simultaneously.

### 2. Agent Intelligence
The agent operates with a detailed system prompt that defines its inspection protocol: systematic room-by-room coverage, proactive damage detection, severity assessment, and evidence documentation. It uses function calling (tools) to log findings, track progress, and generate reports.

### 3. Barge-In Support
The Gemini Live API natively supports interruption. When the user speaks while the agent is responding, the agent stops, acknowledges the interruption, and pivots to the user's new focus.

### 4. Tool Calls
The agent has 4 tools:
- `capture_evidence` — Log a finding with room, type, severity, description
- `check_progress` — Review inspection coverage and identify gaps
- `generate_report` — Create the final PDF report
- `flag_safety_concern` — Alert the user to immediate hazards

### 5. Report Generation
When the inspection ends, findings are compiled into a professional PDF with severity breakdown, detailed evidence items, and recommended actions — ready for insurance submission.

---

## 🎓 Learnings & Challenges

### What Worked Well
- **Gemini Live API** handles multimodal streaming remarkably well — vision + audio in a single session is seamless
- **Function calling** during live sessions enables structured data capture without breaking conversation flow
- **The system prompt** is critical — the difference between a good and great agent is 90% prompt engineering

### Challenges Overcome
- **Frame rate tuning**: Too many frames overwhelm the API; too few miss damage. 2 FPS with 640x480 JPEG is the sweet spot
- **Audio echo**: Had to implement echo cancellation on the client side to prevent the agent's voice from being re-captured by the mic
- **WebSocket stability**: Long inspection sessions (10+ minutes) required keepalive pings and reconnection logic

### What We'd Improve
- Add OCR for reading serial numbers, labels, and model information
- Implement blueprint/floor plan comparison
- Add multi-user support (adjuster + homeowner in same session)
- Train a fine-tuned damage classification model for higher accuracy

---

## 📜 License

MIT License — see [LICENSE](LICENSE)

---

## 🏷️ Hackathon Info

- **Hackathon**: Gemini Live Agent Challenge 2026
- **Category**: Live Agents
- **Team**: [Your Name]
- **Blog Post**: [Link to your blog post] #GeminiLiveAgentChallenge

---

<p align="center">
  <b>InspectAI — See More. Miss Nothing.</b><br/>
  Built with Gemini 2.0 Flash, Google Cloud, and ☕
</p>

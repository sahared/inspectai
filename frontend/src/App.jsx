import React, { useState, useRef, useCallback, useEffect } from "react";
import {
  Camera, Mic, MicOff, Play, Square,
  FileText, ChevronUp, ChevronDown, Shield, Eye, Send, Volume2, VolumeX
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "ws://localhost:8080";
const FRAME_INTERVAL_MS = 2000;
const FRAME_QUALITY = 0.6;

const SEV = {
  minor: { bg: "bg-green-500/20", text: "text-green-400", border: "border-green-500/40" },
  moderate: { bg: "bg-amber-500/20", text: "text-amber-400", border: "border-amber-500/40" },
  severe: { bg: "bg-red-500/20", text: "text-red-400", border: "border-red-500/40" },
  critical: { bg: "bg-purple-500/20", text: "text-purple-400", border: "border-purple-500/40" },
};

// ─── VOICE HELPERS ──────────────────────────────────────────────

// Text-to-Speech: Make the agent SPEAK
function speakText(text, onEnd) {
  if (!window.speechSynthesis || !text) return;
  // Cancel any ongoing speech
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.0;
  utterance.pitch = 1.0;
  utterance.volume = 1.0;

  // Try to pick a professional-sounding voice
  const voices = window.speechSynthesis.getVoices();
  const preferred = voices.find(v =>
    v.name.includes("Samantha") || v.name.includes("Daniel") ||
    v.name.includes("Google") || v.name.includes("English")
  );
  if (preferred) utterance.voice = preferred;

  utterance.onend = onEnd;
  window.speechSynthesis.speak(utterance);
}

// Load voices (they load async in some browsers)
if (typeof window !== "undefined" && window.speechSynthesis) {
  window.speechSynthesis.getVoices();
  window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
}

// ─── MAIN APP ───────────────────────────────────────────────────

export default function App() {
  const [phase, setPhase] = useState("welcome");
  const [isConnected, setIsConnected] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [findings, setFindings] = useState([]);
  const [messages, setMessages] = useState([]);
  const [showFindings, setShowFindings] = useState(false);
  const [error, setError] = useState(null);
  const [statusMsg, setStatusMsg] = useState("");
  const [frameCount, setFrameCount] = useState(0);
  const [textInput, setTextInput] = useState("");
  const [reportUrl, setReportUrl] = useState(null);
  const [cameraReady, setCameraReady] = useState(false);

  // Voice state
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [interimTranscript, setInterimTranscript] = useState("");

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const frameIntervalRef = useRef(null);
  const msgEndRef = useRef(null);
  const recognitionRef = useRef(null);

  // Auto-scroll messages
  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Speech Recognition (STT) Setup ─────────────────────────────

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn("Speech Recognition not supported in this browser");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event) => {
      let interim = "";
      let final = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          final += transcript;
        } else {
          interim += transcript;
        }
      }

      setInterimTranscript(interim);

      if (final.trim()) {
        // Send the final transcript as a message
        sendTextMessage(final.trim());
        setInterimTranscript("");
      }
    };

    recognition.onerror = (event) => {
      console.error("Speech recognition error:", event.error);
      if (event.error === "not-allowed") {
        setError("Microphone access denied. Use text input instead.");
      }
      setIsListening(false);
    };

    recognition.onend = () => {
      // Auto-restart if still supposed to be listening
      if (isListening && recognitionRef.current) {
        try {
          recognitionRef.current.start();
        } catch (e) {
          // Already started
        }
      }
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.stop();
    };
  }, []);

  // Update the restart behavior when isListening changes
  useEffect(() => {
    if (!recognitionRef.current) return;
    if (isListening) {
      try {
        recognitionRef.current.start();
      } catch (e) {
        // Already started
      }
    } else {
      try {
        recognitionRef.current.stop();
      } catch (e) {
        // Already stopped
      }
      setInterimTranscript("");
    }
  }, [isListening]);

  // ── Camera Setup ───────────────────────────────────────────────

  useEffect(() => {
    if (phase === "inspecting" && !cameraReady) {
      const initCamera = async () => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: "environment" }, width: 640, height: 480 },
            audio: false,
          });
          streamRef.current = stream;
          setTimeout(() => {
            if (videoRef.current) {
              videoRef.current.srcObject = stream;
              setCameraReady(true);
              // Start frame capture
              const canvas = canvasRef.current;
              if (canvas) {
                const ctx = canvas.getContext("2d");
                canvas.width = 640;
                canvas.height = 480;
                frameIntervalRef.current = setInterval(() => {
                  if (videoRef.current?.readyState >= 2 && wsRef.current?.readyState === WebSocket.OPEN) {
                    ctx.drawImage(videoRef.current, 0, 0, 640, 480);
                    canvas.toBlob(blob => {
                      if (blob) {
                        const reader = new FileReader();
                        reader.onload = () => {
                          wsRef.current.send(JSON.stringify({ type: "frame", data: reader.result.split(",")[1] }));
                          setFrameCount(c => c + 1);
                        };
                        reader.readAsDataURL(blob);
                      }
                    }, "image/jpeg", FRAME_QUALITY);
                  }
                }, FRAME_INTERVAL_MS);
              }
            }
          }, 500);
        } catch (e) {
          console.error("Camera error:", e);
          setError("Camera denied. You can still type or use voice.");
        }
      };
      initCamera();
    }
    return () => { if (frameIntervalRef.current) clearInterval(frameIntervalRef.current); };
  }, [phase, cameraReady]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
      if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
      window.speechSynthesis?.cancel();
    };
  }, []);

  // ── Send text helper (used by both typing and voice) ───────────

  const sendTextMessage = useCallback((text) => {
    if (!text.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "text", data: text.trim() }));
    setMessages(prev => [...prev, { text: text.trim(), speaker: "user" }]);
  }, []);

  // ── WebSocket ──────────────────────────────────────────────────

  const connectWS = useCallback((sid) => {
    const ws = new WebSocket(`${API_BASE}/ws/inspect/${sid}`);
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      switch (msg.type) {
        case "status":
          setStatusMsg(msg.message || msg.status);
          if (msg.status === "connected") setPhase("inspecting");
          break;
        case "transcript":
          if (msg.speaker === "agent" && msg.text) {
            setMessages(prev => [...prev, { text: msg.text, speaker: "agent" }]);
            // Agent SPEAKS the response aloud
            if (voiceEnabled) {
              setIsSpeaking(true);
              // Pause listening while agent speaks to avoid echo
              if (isListening && recognitionRef.current) {
                try { recognitionRef.current.stop(); } catch(e) {}
              }
              speakText(msg.text, () => {
                setIsSpeaking(false);
                // Resume listening after agent finishes speaking
                if (isListening && recognitionRef.current) {
                  try { recognitionRef.current.start(); } catch(e) {}
                }
              });
            }
          }
          break;
        case "finding":
          setFindings(prev => [...prev, msg.finding]);
          setShowFindings(true);
          break;
        case "frame_analyzed":
          break;
        case "report_ready":
          const httpBase = API_BASE.replace("ws://", "http://").replace("wss://", "https://");
          setReportUrl(`${httpBase}${msg.url}`);
          setPhase("report");
          window.speechSynthesis?.cancel();
          break;
        case "error":
          setError(msg.message);
          break;
      }
    };

    ws.onclose = () => { setIsConnected(false); setStatusMsg("Disconnected"); };
    ws.onerror = () => setError("Connection error. Is the backend running?");

    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
    }, 30000);
    return () => clearInterval(ping);
  }, [voiceEnabled, isListening]);

  // ── Actions ────────────────────────────────────────────────────

  const startInspection = useCallback(async () => {
    setError(null);
    setPhase("connecting");
    try {
      const httpBase = API_BASE.replace("ws://", "http://").replace("wss://", "https://");
      const res = await fetch(`${httpBase}/api/sessions?claim_type=property_damage`, { method: "POST" });
      const session = await res.json();
      setSessionId(session.session_id);
      connectWS(session.session_id);
    } catch (e) {
      setError(e.message || "Failed to start");
      setPhase("welcome");
    }
  }, [connectWS]);

  const sendText = useCallback(() => {
    if (!textInput.trim()) return;
    sendTextMessage(textInput.trim());
    setTextInput("");
  }, [textInput, sendTextMessage]);

  const sendFrameWithText = useCallback(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!video || video.readyState < 2 || !wsRef.current) return;
    const ctx = canvas.getContext("2d");
    canvas.width = 640; canvas.height = 480;
    ctx.drawImage(video, 0, 0, 640, 480);
    canvas.toBlob(blob => {
      const reader = new FileReader();
      reader.onload = () => {
        const b64 = reader.result.split(",")[1];
        const text = textInput.trim() || "What damage do you see here? Log everything with capture_evidence.";
        wsRef.current.send(JSON.stringify({ type: "frame_with_text", data: b64, text }));
        setMessages(prev => [...prev, { text: "📷 " + text, speaker: "user" }]);
        setTextInput("");
      };
      reader.readAsDataURL(blob);
    }, "image/jpeg", 0.7);
  }, [textInput]);

  const toggleListening = useCallback(() => {
    if (isSpeaking) {
      // Stop agent from speaking so user can talk
      window.speechSynthesis?.cancel();
      setIsSpeaking(false);
    }
    setIsListening(prev => !prev);
  }, [isSpeaking]);

  const endInspection = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "end_inspection" }));
    }
    if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
    if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
    setIsListening(false);
    window.speechSynthesis?.cancel();
  }, []);

  const resetInspection = useCallback(() => {
    if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
    if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
    if (wsRef.current) wsRef.current.close();
    window.speechSynthesis?.cancel();
    setPhase("welcome"); setFindings([]); setMessages([]);
    setReportUrl(null); setError(null); setFrameCount(0);
    setCameraReady(false); setIsListening(false); setIsSpeaking(false);
    setInterimTranscript("");
  }, []);

  // ── RENDER ─────────────────────────────────────────────────────

  return (
    <div className="relative h-screen w-full overflow-hidden bg-black" style={{ fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      <canvas ref={canvasRef} className="hidden" />

      {/* ── WELCOME ──────────────────────────────────────────── */}
      {phase === "welcome" && (
        <div className="flex flex-col items-center justify-center h-full px-6" style={{ animation: "fadeIn 0.5s" }}>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center">
              <Eye className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-3xl font-bold text-white">InspectAI</h1>
          </div>
          <p className="text-white/50 text-sm mb-10">See More. Miss Nothing.</p>
          <p className="text-white/60 text-sm text-center max-w-sm mb-4 leading-relaxed">
            Point your camera at property damage and talk to your AI inspector.
            Speak naturally — the agent sees, hears, and responds in real-time.
          </p>
          <div className="flex gap-4 mb-10">
            {[
              { icon: Camera, label: "Sees Damage" },
              { icon: Mic, label: "Hears You" },
              { icon: Volume2, label: "Speaks Back" },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="flex flex-col items-center gap-2 px-4 py-3 rounded-xl bg-white/5 border border-white/10">
                <Icon className="w-5 h-5 text-blue-400" />
                <span className="text-[11px] text-white/60">{label}</span>
              </div>
            ))}
          </div>
          <button onClick={startInspection}
            className="w-full max-w-sm py-4 rounded-2xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-lg flex items-center justify-center gap-2">
            <Play className="w-5 h-5" /> Start Inspection
          </button>
          {error && <p className="text-red-400 text-sm mt-4 text-center">{error}</p>}
        </div>
      )}

      {/* ── CONNECTING ───────────────────────────────────────── */}
      {phase === "connecting" && (
        <div className="flex flex-col items-center justify-center h-full">
          <div className="w-16 h-16 rounded-full border-4 border-blue-600 border-t-transparent animate-spin mb-6" />
          <p className="text-white/70 text-sm">{statusMsg || "Connecting..."}</p>
        </div>
      )}

      {/* ── INSPECTING ───────────────────────────────────────── */}
      {phase === "inspecting" && (
        <div className="flex h-full">

          {/* LEFT: Camera */}
          <div className="w-2/5 relative bg-gray-900">
            <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" style={{ minHeight: "100%" }} />

            {!cameraReady && (
              <div className="absolute inset-0 flex items-center justify-center bg-gray-900">
                <div className="text-center">
                  <Camera className="w-10 h-10 text-white/30 mx-auto mb-2" />
                  <p className="text-white/40 text-sm">Starting camera...</p>
                </div>
              </div>
            )}

            {/* LIVE + Speaking indicator */}
            <div className="absolute top-3 left-3 flex items-center gap-2">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/70">
                <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                <span className="text-[11px] text-green-400 font-medium">LIVE</span>
              </div>
              {isSpeaking && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-blue-600/80 animate-pulse">
                  <Volume2 className="w-3 h-3 text-white" />
                  <span className="text-[11px] text-white font-medium">Speaking...</span>
                </div>
              )}
              {isListening && !isSpeaking && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-red-600/80 animate-pulse">
                  <Mic className="w-3 h-3 text-white" />
                  <span className="text-[11px] text-white font-medium">Listening...</span>
                </div>
              )}
            </div>

            <div className="absolute bottom-14 left-3 px-3 py-1 rounded-full bg-black/70 text-[11px] text-white/50">
              Frames: {frameCount}
            </div>

            <button onClick={sendFrameWithText}
              className="absolute bottom-3 left-3 right-3 py-2.5 rounded-lg bg-blue-600/90 hover:bg-blue-700 text-white text-sm font-medium flex items-center justify-center gap-2">
              <Camera className="w-4 h-4" /> Capture & Ask AI
            </button>
          </div>

          {/* RIGHT: Chat */}
          <div className="w-3/5 flex flex-col bg-gray-950">

            {/* Top bar */}
            <div className="flex items-center justify-between px-4 py-2.5 bg-gray-900 border-b border-gray-800">
              <div className="flex items-center gap-3">
                <span className="text-[12px] text-green-400 font-medium flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-green-400" />
                  {isConnected ? "Connected" : "Disconnected"}
                </span>
                {/* Voice toggle */}
                <button onClick={() => setVoiceEnabled(v => !v)}
                  className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] ${voiceEnabled ? "bg-blue-600/30 text-blue-400" : "bg-gray-800 text-gray-500"}`}>
                  {voiceEnabled ? <Volume2 className="w-3 h-3" /> : <VolumeX className="w-3 h-3" />}
                  {voiceEnabled ? "Voice On" : "Voice Off"}
                </button>
              </div>
              <button onClick={() => setShowFindings(!showFindings)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-[12px] font-medium text-white/80">
                <Shield className="w-3.5 h-3.5 text-blue-400" />
                {findings.length} Finding{findings.length !== 1 ? "s" : ""}
                {showFindings ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
            </div>

            {/* Findings panel */}
            {showFindings && findings.length > 0 && (
              <div className="max-h-48 overflow-y-auto bg-gray-900/80 border-b border-gray-800 p-3 space-y-2">
                {findings.map((f, i) => {
                  const sev = f.severity || "minor";
                  const c = SEV[sev] || SEV.minor;
                  return (
                    <div key={i} className={`p-2.5 rounded-lg ${c.bg} border ${c.border}`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[11px] font-bold text-white/90">#{f.evidence_number || i + 1} — {(f.damage_type || "").replace(/_/g, " ")}</span>
                        <span className={`text-[10px] font-bold uppercase ${c.text}`}>{sev}</span>
                      </div>
                      <p className="text-[11px] text-white/60">{(f.room || "").replace(/_/g, " ")} — {(f.description || "").substring(0, 80)}</p>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.length === 0 && (
                <div className="text-center text-white/30 mt-20">
                  <Mic className="w-8 h-8 mx-auto mb-3 text-white/20" />
                  <p className="text-sm">Tap the mic button and describe damage, or type below</p>
                </div>
              )}
              {messages.map((m, i) => (
                <div key={i} className={`flex ${m.speaker === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[85%] px-3.5 py-2.5 rounded-2xl text-[13px] leading-relaxed ${
                    m.speaker === "user"
                      ? "bg-white/15 text-white/90 rounded-br-sm"
                      : "bg-blue-600/80 text-white rounded-bl-sm"
                  }`}>
                    {m.text}
                  </div>
                </div>
              ))}

              {/* Show interim speech-to-text as user is talking */}
              {interimTranscript && (
                <div className="flex justify-end">
                  <div className="max-w-[85%] px-3.5 py-2.5 rounded-2xl text-[13px] bg-white/10 text-white/50 italic rounded-br-sm">
                    {interimTranscript}...
                  </div>
                </div>
              )}

              <div ref={msgEndRef} />
            </div>

            {/* Input bar */}
            <div className="p-3 bg-gray-900 border-t border-gray-800">
              <div className="flex gap-2 mb-2">
                {/* Mic button — BIG and prominent */}
                <button onClick={toggleListening}
                  className={`w-11 h-11 flex-shrink-0 rounded-xl flex items-center justify-center transition-all ${
                    isListening
                      ? "bg-red-600 animate-pulse shadow-lg shadow-red-600/30"
                      : "bg-gray-800 hover:bg-gray-700"
                  }`}
                  title={isListening ? "Stop listening" : "Start speaking"}>
                  {isListening ? <MicOff className="w-5 h-5 text-white" /> : <Mic className="w-5 h-5 text-white/70" />}
                </button>

                <input
                  type="text"
                  value={textInput}
                  onChange={e => setTextInput(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && sendText()}
                  placeholder={isListening ? "Listening... speak now" : "Type or tap mic to speak..."}
                  className="flex-1 px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white placeholder-white/30 outline-none focus:border-blue-500"
                />
                <button onClick={sendText} className="px-4 rounded-xl bg-blue-600 hover:bg-blue-700 text-white">
                  <Send className="w-4 h-4" />
                </button>
              </div>
              <button onClick={endInspection}
                className="w-full py-2.5 rounded-xl bg-red-600/80 hover:bg-red-600 text-white text-sm font-medium flex items-center justify-center gap-2">
                <Square className="w-3.5 h-3.5" /> End Inspection & Generate Report
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── REPORT ───────────────────────────────────────────── */}
      {phase === "report" && (
        <div className="flex flex-col items-center justify-center h-full px-6">
          <div className="w-16 h-16 rounded-full bg-green-600/20 flex items-center justify-center mb-6">
            <FileText className="w-8 h-8 text-green-400" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Inspection Complete</h2>
          <p className="text-white/50 text-sm mb-6">{findings.length} finding{findings.length !== 1 ? "s" : ""} documented</p>

          <div className="w-full max-w-md mb-6 space-y-2">
            {findings.map((f, i) => {
              const sev = f.severity || "minor";
              const c = SEV[sev] || SEV.minor;
              return (
                <div key={i} className={`flex items-center gap-3 p-3 rounded-xl ${c.bg} border ${c.border}`}>
                  <span className="text-xs font-bold text-white/80">#{f.evidence_number || i + 1}</span>
                  <div className="flex-1">
                    <p className="text-xs text-white/80">{(f.damage_type || "").replace(/_/g, " ")} in {(f.room || "").replace(/_/g, " ")}</p>
                  </div>
                  <span className={`text-[10px] font-bold uppercase ${c.text}`}>{sev}</span>
                </div>
              );
            })}
          </div>

          {reportUrl && (
            <a href={reportUrl} target="_blank" rel="noopener noreferrer"
              className="w-full max-w-md py-4 rounded-2xl bg-blue-600 hover:bg-blue-700 text-white text-center font-semibold mb-3 block">
              Download Report PDF
            </a>
          )}
          <button onClick={resetInspection}
            className="w-full max-w-md py-4 rounded-2xl bg-white/10 hover:bg-white/15 text-white text-center font-medium">
            New Inspection
          </button>
        </div>
      )}

      {error && phase === "inspecting" && (
        <div className="absolute top-12 left-1/2 -translate-x-1/2 px-4 py-2 rounded-lg bg-red-900/80 text-red-200 text-xs z-50">
          {error}
        </div>
      )}

      <style>{`@keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }`}</style>
    </div>
  );
}

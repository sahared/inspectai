import React, { useState, useRef, useCallback, useEffect } from "react";
import {
  Camera, Mic, MicOff, Play, Square, AlertTriangle,
  FileText, ChevronUp, ChevronDown, Shield, Eye, Wifi, WifiOff
} from "lucide-react";

// =============================================================================
// CONFIGURATION
// =============================================================================

const API_BASE = import.meta.env.VITE_API_URL || "ws://localhost:8080";
const FRAME_INTERVAL_MS = 500; // Send 2 frames per second
const FRAME_QUALITY = 0.7;    // JPEG quality
const FRAME_WIDTH = 640;
const FRAME_HEIGHT = 480;

// Severity colors
const SEVERITY_COLORS = {
  minor: { bg: "bg-green-500/20", text: "text-green-400", border: "border-green-500/40" },
  moderate: { bg: "bg-amber-500/20", text: "text-amber-400", border: "border-amber-500/40" },
  severe: { bg: "bg-red-500/20", text: "text-red-400", border: "border-red-500/40" },
  critical: { bg: "bg-purple-500/20", text: "text-purple-400", border: "border-purple-500/40" },
};

// =============================================================================
// MAIN APP
// =============================================================================

export default function App() {
  // State
  const [phase, setPhase] = useState("welcome"); // welcome | connecting | inspecting | report
  const [isConnected, setIsConnected] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [findings, setFindings] = useState([]);
  const [transcript, setTranscript] = useState([]);
  const [progress, setProgress] = useState({ areas: 0, completion: 0 });
  const [reportUrl, setReportUrl] = useState(null);
  const [error, setError] = useState(null);
  const [showFindings, setShowFindings] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [safetyAlerts, setSafetyAlerts] = useState([]);

  // Refs
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const frameIntervalRef = useRef(null);
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);
  const transcriptEndRef = useRef(null);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript]);

  // =========================================================================
  // CAMERA & AUDIO SETUP
  // =========================================================================

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" }, // Back camera on mobile
          width: { ideal: FRAME_WIDTH },
          height: { ideal: FRAME_HEIGHT },
        },
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        },
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      return stream;
    } catch (err) {
      console.error("Camera/mic access error:", err);
      setError("Please allow camera and microphone access to start an inspection.");
      throw err;
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current);
      frameIntervalRef.current = null;
    }
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
  }, []);

  // =========================================================================
  // FRAME CAPTURE — Send camera frames to backend
  // =========================================================================

  const startFrameCapture = useCallback(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;

    const ctx = canvas.getContext("2d");
    canvas.width = FRAME_WIDTH;
    canvas.height = FRAME_HEIGHT;

    frameIntervalRef.current = setInterval(() => {
      if (video.readyState >= 2 && wsRef.current?.readyState === WebSocket.OPEN) {
        ctx.drawImage(video, 0, 0, FRAME_WIDTH, FRAME_HEIGHT);
        canvas.toBlob(
          (blob) => {
            if (blob) {
              const reader = new FileReader();
              reader.onload = () => {
                const base64 = reader.result.split(",")[1];
                wsRef.current?.send(JSON.stringify({ type: "frame", data: base64 }));
              };
              reader.readAsDataURL(blob);
            }
          },
          "image/jpeg",
          FRAME_QUALITY
        );
      }
    }, FRAME_INTERVAL_MS);
  }, []);

  // =========================================================================
  // AUDIO CAPTURE — Send audio chunks to backend
  // =========================================================================

  const startAudioCapture = useCallback((stream) => {
    try {
      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (event) => {
        if (wsRef.current?.readyState === WebSocket.OPEN && !isMuted) {
          const inputData = event.inputBuffer.getChannelData(0);
          // Convert float32 to int16 PCM
          const pcm16 = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            pcm16[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
          }
          // Base64 encode
          const base64 = btoa(
            String.fromCharCode(...new Uint8Array(pcm16.buffer))
          );
          wsRef.current.send(JSON.stringify({ type: "audio", data: base64 }));
        }
      };

      source.connect(processor);
      processor.connect(audioContext.destination);
    } catch (err) {
      console.error("Audio capture error:", err);
    }
  }, [isMuted]);

  // =========================================================================
  // AUDIO PLAYBACK — Play agent's voice responses
  // =========================================================================

  const playAudioResponse = useCallback(async (base64Audio) => {
    try {
      const audioContext = audioContextRef.current || new AudioContext({ sampleRate: 24000 });
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      
      // Convert PCM bytes to AudioBuffer
      const float32 = new Float32Array(bytes.length / 2);
      const dataView = new DataView(bytes.buffer);
      for (let i = 0; i < float32.length; i++) {
        float32[i] = dataView.getInt16(i * 2, true) / 32768;
      }
      
      const audioBuffer = audioContext.createBuffer(1, float32.length, 24000);
      audioBuffer.copyToChannel(float32, 0);
      
      const source = audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContext.destination);
      source.start();
    } catch (err) {
      console.error("Audio playback error:", err);
    }
  }, []);

  // =========================================================================
  // WEBSOCKET — Connect to backend
  // =========================================================================

  const connectWebSocket = useCallback((sessionId) => {
    const wsUrl = `${API_BASE}/ws/inspect/${sessionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setStatusMessage("Connected to InspectAI");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case "status":
            setStatusMessage(data.message || data.status);
            if (data.status === "connected") {
              setPhase("inspecting");
            }
            break;

          case "transcript":
            setTranscript((prev) => [
              ...prev,
              {
                text: data.text,
                speaker: data.speaker,
                timestamp: data.timestamp || new Date().toISOString(),
              },
            ]);
            break;

          case "audio":
            playAudioResponse(data.data);
            break;

          case "finding":
            setFindings((prev) => [...prev, data.finding]);
            // Briefly show findings panel
            setShowFindings(true);
            setTimeout(() => setShowFindings(false), 3000);
            break;

          case "progress":
            setProgress({
              areas: data.areas_covered || data.areas_inspected?.length || 0,
              completion: data.completion || 0,
              remaining: data.areas_remaining || [],
            });
            break;

          case "safety_alert":
            setSafetyAlerts((prev) => [...prev, data.concern]);
            break;

          case "report_ready":
            setReportUrl(data.url);
            setPhase("report");
            break;

          case "error":
            setError(data.message);
            break;

          case "pong":
            break;

          default:
            console.log("Unknown message type:", data.type);
        }
      } catch (err) {
        console.error("Error parsing WebSocket message:", err);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      setStatusMessage("Disconnected");
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
      setError("Connection error. Please check your backend is running.");
    };

    // Keepalive ping every 30s
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      ws.close();
    };
  }, [playAudioResponse]);

  // =========================================================================
  // INSPECTION LIFECYCLE
  // =========================================================================

  const startInspection = useCallback(async () => {
    setError(null);
    setPhase("connecting");
    setStatusMessage("Initializing camera...");

    try {
      // 1. Start camera and audio
      const stream = await startCamera();

      // 2. Create session via REST API
      setStatusMessage("Creating inspection session...");
      const httpBase = API_BASE.replace("ws://", "http://").replace("wss://", "https://");
      const res = await fetch(`${httpBase}/api/sessions?claim_type=property_damage`, {
        method: "POST",
      });
      const session = await res.json();
      setSessionId(session.session_id);

      // 3. Connect WebSocket
      setStatusMessage("Connecting to InspectAI...");
      connectWebSocket(session.session_id);

      // 4. Start streaming frames and audio
      startFrameCapture();
      startAudioCapture(stream);

    } catch (err) {
      console.error("Failed to start inspection:", err);
      setError(err.message || "Failed to start inspection");
      setPhase("welcome");
    }
  }, [startCamera, connectWebSocket, startFrameCapture, startAudioCapture]);

  const endInspection = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "end_inspection" }));
    }
    setStatusMessage("Generating report...");
  }, []);

  const resetInspection = useCallback(() => {
    stopCamera();
    if (wsRef.current) wsRef.current.close();
    setPhase("welcome");
    setFindings([]);
    setTranscript([]);
    setProgress({ areas: 0, completion: 0 });
    setReportUrl(null);
    setError(null);
    setSafetyAlerts([]);
    setSessionId(null);
  }, [stopCamera]);

  const toggleMute = useCallback(() => {
    setIsMuted((prev) => {
      const newMuted = !prev;
      // Mute/unmute the audio track
      if (streamRef.current) {
        streamRef.current.getAudioTracks().forEach((track) => {
          track.enabled = !newMuted;
        });
      }
      return newMuted;
    });
  }, []);

  const sendTextMessage = useCallback((text) => {
    if (wsRef.current?.readyState === WebSocket.OPEN && text.trim()) {
      wsRef.current.send(JSON.stringify({ type: "text", data: text }));
    }
  }, []);

  // =========================================================================
  // RENDER
  // =========================================================================

  return (
    <div className="relative h-full w-full overflow-hidden bg-black">
      {/* Hidden canvas for frame capture */}
      <canvas ref={canvasRef} className="hidden" />

      {/* ================================================================= */}
      {/* WELCOME SCREEN */}
      {/* ================================================================= */}
      {phase === "welcome" && (
        <div className="flex flex-col items-center justify-center h-full px-6 fade-in">
          {/* Logo */}
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center">
              <Eye className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-3xl font-bold tracking-tight">InspectAI</h1>
          </div>
          <p className="text-white/50 text-sm mb-10">See More. Miss Nothing.</p>

          {/* Description */}
          <div className="max-w-sm text-center mb-10">
            <p className="text-white/70 text-sm leading-relaxed">
              Point your camera at property damage and have a natural conversation 
              with your AI inspector. I'll guide you through a thorough assessment 
              and generate a professional report.
            </p>
          </div>

          {/* Features */}
          <div className="grid grid-cols-3 gap-4 mb-10 max-w-sm w-full">
            {[
              { icon: Camera, label: "Real-Time Vision" },
              { icon: Mic, label: "Voice Guided" },
              { icon: FileText, label: "Auto Reports" },
            ].map(({ icon: Icon, label }) => (
              <div
                key={label}
                className="flex flex-col items-center gap-2 p-3 rounded-xl bg-white/5 border border-white/10"
              >
                <Icon className="w-5 h-5 text-blue-400" />
                <span className="text-[11px] text-white/60">{label}</span>
              </div>
            ))}
          </div>

          {/* Start Button */}
          <button
            onClick={startInspection}
            className="w-full max-w-sm py-4 rounded-2xl bg-blue-600 hover:bg-blue-700 
                       active:scale-[0.98] transition-all font-semibold text-lg
                       flex items-center justify-center gap-2"
          >
            <Play className="w-5 h-5" />
            Start Inspection
          </button>

          {error && (
            <p className="text-red-400 text-sm mt-4 text-center max-w-sm">{error}</p>
          )}
        </div>
      )}

      {/* ================================================================= */}
      {/* CONNECTING SCREEN */}
      {/* ================================================================= */}
      {phase === "connecting" && (
        <div className="flex flex-col items-center justify-center h-full px-6 fade-in">
          <div className="w-16 h-16 rounded-full border-4 border-blue-600 border-t-transparent animate-spin mb-6" />
          <p className="text-white/70 text-sm">{statusMessage}</p>
        </div>
      )}

      {/* ================================================================= */}
      {/* INSPECTION SCREEN — Main Experience */}
      {/* ================================================================= */}
      {phase === "inspecting" && (
        <>
          {/* Camera Feed — Full Screen Background */}
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="absolute inset-0 w-full h-full object-cover"
          />

          {/* Dark overlay gradient for readability */}
          <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-transparent to-black/80 pointer-events-none" />

          {/* ── TOP BAR ── */}
          <div className="absolute top-0 left-0 right-0 p-4 flex items-center justify-between z-10">
            {/* Connection Status */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/50 backdrop-blur-sm">
              {isConnected ? (
                <>
                  <div className="relative">
                    <div className="w-2 h-2 rounded-full bg-green-400" />
                    <div className="absolute inset-0 w-2 h-2 rounded-full bg-green-400 pulse-ring" />
                  </div>
                  <span className="text-[11px] text-green-400 font-medium">LIVE</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-3 h-3 text-red-400" />
                  <span className="text-[11px] text-red-400">Disconnected</span>
                </>
              )}
            </div>

            {/* Findings Counter */}
            <button
              onClick={() => setShowFindings(!showFindings)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/50 backdrop-blur-sm"
            >
              <Shield className="w-3.5 h-3.5 text-blue-400" />
              <span className="text-[11px] font-medium">
                {findings.length} Finding{findings.length !== 1 ? "s" : ""}
              </span>
              {showFindings ? (
                <ChevronUp className="w-3 h-3" />
              ) : (
                <ChevronDown className="w-3 h-3" />
              )}
            </button>
          </div>

          {/* ── SAFETY ALERTS ── */}
          {safetyAlerts.length > 0 && (
            <div className="absolute top-14 left-4 right-4 z-20">
              {safetyAlerts.slice(-1).map((alert, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 p-3 rounded-xl bg-red-900/80 backdrop-blur-sm border border-red-500/50 slide-up"
                >
                  <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs font-bold text-red-300">SAFETY CONCERN</p>
                    <p className="text-xs text-red-200 mt-0.5">{alert.concern}</p>
                    <p className="text-[10px] text-red-300 mt-1">{alert.recommended_action}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* ── FINDINGS PANEL (expandable) ── */}
          {showFindings && findings.length > 0 && (
            <div className="absolute top-14 right-4 w-64 max-h-[40vh] overflow-y-auto rounded-xl bg-black/70 backdrop-blur-md border border-white/10 z-10 custom-scrollbar slide-up">
              <div className="p-3">
                <h3 className="text-xs font-bold text-white/80 mb-2">Evidence Log</h3>
                {findings.map((f, i) => {
                  const colors = SEVERITY_COLORS[f.severity] || SEVERITY_COLORS.minor;
                  return (
                    <div
                      key={i}
                      className={`mb-2 p-2 rounded-lg ${colors.bg} border ${colors.border}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold text-white/80">
                          #{f.evidence_number}
                        </span>
                        <span className={`text-[9px] font-bold uppercase ${colors.text}`}>
                          {f.severity}
                        </span>
                      </div>
                      <p className="text-[10px] text-white/60 mt-1">
                        {f.room?.replace(/_/g, " ")} — {f.damage_type?.replace(/_/g, " ")}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── TRANSCRIPT OVERLAY ── */}
          <div className="absolute bottom-28 left-0 right-0 px-4 max-h-[30vh] overflow-y-auto custom-scrollbar">
            {transcript.slice(-6).map((entry, i) => (
              <div
                key={i}
                className={`mb-2 slide-up ${
                  entry.speaker === "agent"
                    ? "mr-8"
                    : "ml-8 text-right"
                }`}
              >
                <div
                  className={`inline-block px-3 py-2 rounded-xl text-sm leading-relaxed ${
                    entry.speaker === "agent"
                      ? "bg-blue-600/80 backdrop-blur-sm"
                      : "bg-white/20 backdrop-blur-sm"
                  }`}
                >
                  {entry.text}
                </div>
              </div>
            ))}
            <div ref={transcriptEndRef} />
          </div>

          {/* ── BOTTOM CONTROLS ── */}
          <div className="absolute bottom-0 left-0 right-0 p-4 pb-8 flex items-center justify-center gap-6 z-10">
            {/* Mute Toggle */}
            <button
              onClick={toggleMute}
              className={`w-14 h-14 rounded-full flex items-center justify-center transition-all ${
                isMuted
                  ? "bg-red-600/80 backdrop-blur-sm"
                  : "bg-white/10 backdrop-blur-sm border border-white/20"
              }`}
            >
              {isMuted ? (
                <MicOff className="w-6 h-6" />
              ) : (
                <Mic className="w-6 h-6" />
              )}
            </button>

            {/* End Inspection */}
            <button
              onClick={endInspection}
              className="w-16 h-16 rounded-full bg-red-600 hover:bg-red-700 
                         flex items-center justify-center transition-all
                         active:scale-95 shadow-lg shadow-red-600/30"
            >
              <Square className="w-6 h-6" />
            </button>

            {/* Text Input Toggle (for typing instead of speaking) */}
            <TextInput onSend={sendTextMessage} />
          </div>
        </>
      )}

      {/* ================================================================= */}
      {/* REPORT SCREEN */}
      {/* ================================================================= */}
      {phase === "report" && (
        <div className="flex flex-col items-center justify-center h-full px-6 fade-in">
          <div className="w-16 h-16 rounded-full bg-green-600/20 flex items-center justify-center mb-6">
            <FileText className="w-8 h-8 text-green-400" />
          </div>

          <h2 className="text-2xl font-bold mb-2">Inspection Complete</h2>
          <p className="text-white/50 text-sm mb-8 text-center">
            {findings.length} findings documented across {progress.areas || "multiple"} areas
          </p>

          {/* Findings Summary */}
          <div className="w-full max-w-sm mb-8">
            <h3 className="text-xs font-bold text-white/50 uppercase tracking-wider mb-3">
              Summary
            </h3>
            {findings.map((f, i) => {
              const colors = SEVERITY_COLORS[f.severity] || SEVERITY_COLORS.minor;
              return (
                <div
                  key={i}
                  className={`flex items-center gap-3 p-3 mb-2 rounded-xl ${colors.bg} border ${colors.border}`}
                >
                  <span className="text-xs font-bold text-white/80">#{f.evidence_number}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-white/80 truncate">
                      {f.damage_type?.replace(/_/g, " ")} in {f.room?.replace(/_/g, " ")}
                    </p>
                  </div>
                  <span className={`text-[10px] font-bold uppercase ${colors.text}`}>
                    {f.severity}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Actions */}
          {reportUrl && (
            <a
              href={reportUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full max-w-sm py-4 rounded-2xl bg-blue-600 hover:bg-blue-700 
                         text-center font-semibold transition-all mb-3 block"
            >
              Download Report PDF
            </a>
          )}

          <button
            onClick={resetInspection}
            className="w-full max-w-sm py-4 rounded-2xl bg-white/10 hover:bg-white/15 
                       text-center font-medium transition-all"
          >
            New Inspection
          </button>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// TEXT INPUT COMPONENT (for typing messages instead of speaking)
// =============================================================================

function TextInput({ onSend }) {
  const [isOpen, setIsOpen] = useState(false);
  const [text, setText] = useState("");
  const inputRef = useRef(null);

  const handleSend = () => {
    if (text.trim()) {
      onSend(text.trim());
      setText("");
      setIsOpen(false);
    }
  };

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="w-14 h-14 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 
                   flex items-center justify-center transition-all"
      >
        <FileText className="w-5 h-5" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 left-4 right-4 flex gap-2 z-50">
      <input
        ref={inputRef}
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSend()}
        placeholder="Type a message..."
        className="flex-1 px-4 py-3 rounded-xl bg-black/80 backdrop-blur-sm border border-white/20 
                   text-sm text-white placeholder-white/40 outline-none focus:border-blue-500"
      />
      <button
        onClick={handleSend}
        className="px-4 py-3 rounded-xl bg-blue-600 font-medium text-sm"
      >
        Send
      </button>
      <button
        onClick={() => setIsOpen(false)}
        className="px-3 py-3 rounded-xl bg-white/10 text-sm"
      >
        ✕
      </button>
    </div>
  );
}

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Mic,
  MicOff,
  Send,
  Settings,
  Database,
  Shield,
  Activity,
  Trash2,
} from "lucide-react";

/**
 * Echo Clean UI — offline-first frontend shell.
 *
 * This is a UI-only build: it includes a thin API adapter you can connect to your local
 * orchestrator (FastAPI/Flask) later. Right now it runs with a local mock.
 *
 * Suggested API endpoints (local-only):
 *  - GET  /health
 *  - POST /chat { message, options }
 *  - POST /stt/start
 *  - POST /stt/stop
 *  - GET  /memory
 *  - POST /memory { enabled }
 */

function useAutoScroll(dep: any) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [dep]);
  return ref;
}

type Msg = {
  id: string;
  role: "user" | "echo" | "system";
  text: string;
  ts: number;
};

function uid() {
  return Math.random().toString(16).slice(2) + Date.now().toString(16);
}

const api = {
  // Replace these with real fetch calls when your local backend is ready.
  async health() {
    await new Promise((r) => setTimeout(r, 150));
    return {
      ok: true,
      llm: "llama.cpp",
      stt: "vosk",
      tts: "piper",
      model: "local",
      device: "termux/desktop",
    };
  },
  async chat(message: string, options: { memory: boolean; safety: boolean }) {
    await new Promise((r) => setTimeout(r, 350));
    // Mock response that feels like Echo.
    const prefix = options.safety
      ? "(Safety on) "
      : options.memory
        ? "(Memory on) "
        : "";
    return {
      text:
        prefix +
        "I heard you. Give me a second to think like a machine with feelings.\n\n" +
        "If you wire me to your orchestrator, this is where the real response will land.",
    };
  },
};

function Bubble({ msg }: { msg: Msg }) {
  const isUser = msg.role === "user";
  const isSystem = msg.role === "system";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={
          "max-w-[84%] rounded-2xl px-4 py-3 shadow-sm text-sm leading-relaxed " +
          (isSystem
            ? "bg-muted text-muted-foreground"
            : isUser
              ? "bg-primary text-primary-foreground"
              : "bg-card border")
        }
      >
        <div className="whitespace-pre-wrap">{msg.text}</div>
        <div className="mt-2 text-[11px] opacity-70">
          {new Date(msg.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </div>
      </div>
    </div>
  );
}

function StatusPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <Badge variant="secondary" className="rounded-full">
        {label}
      </Badge>
      <span className="text-sm text-muted-foreground">{value}</span>
    </div>
  );
}

export default function EchoCleanUI() {
  const [msgs, setMsgs] = useState<Msg[]>(() => [
    {
      id: uid(),
      role: "system",
      text: "Echo UI online. Connect your local orchestrator when ready.",
      ts: Date.now(),
    },
  ]);

  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [micOn, setMicOn] = useState(false);

  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [safetyEnabled, setSafetyEnabled] = useState(true);

  const [health, setHealth] = useState<any>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);

  const scrollerRef = useAutoScroll(msgs.length);

  useEffect(() => {
    let mounted = true;
    api
      .health()
      .then((h) => {
        if (!mounted) return;
        setHealth(h);
        setHealthErr(null);
      })
      .catch((e) => {
        if (!mounted) return;
        setHealth(null);
        setHealthErr(String(e?.message || e));
      });
    return () => {
      mounted = false;
    };
  }, []);

  const canSend = useMemo(() => input.trim().length > 0 && !isSending, [input, isSending]);

  async function send() {
    if (!canSend) return;
    const text = input.trim();
    setInput("");

    const userMsg: Msg = { id: uid(), role: "user", text, ts: Date.now() };
    setMsgs((m) => [...m, userMsg]);

    setIsSending(true);
    try {
      const res = await api.chat(text, { memory: memoryEnabled, safety: safetyEnabled });
      const echoMsg: Msg = { id: uid(), role: "echo", text: res.text, ts: Date.now() };
      setMsgs((m) => [...m, echoMsg]);
    } catch (e: any) {
      setMsgs((m) => [
        ...m,
        {
          id: uid(),
          role: "system",
          text: "Error talking to Echo backend: " + String(e?.message || e),
          ts: Date.now(),
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  function clearChat() {
    setMsgs([
      {
        id: uid(),
        role: "system",
        text: "Chat cleared.",
        ts: Date.now(),
      },
    ]);
  }

  function toggleMic() {
    // Wire these to /stt/start and /stt/stop when available.
    setMicOn((v) => !v);
    setMsgs((m) => [
      ...m,
      {
        id: uid(),
        role: "system",
        text: !micOn
          ? "Listening… (mock). Hook this to Vosk streaming later."
          : "Stopped listening.",
        ts: Date.now(),
      },
    ]);
  }

  return (
    <div className="min-h-screen w-full bg-background text-foreground">
      <div className="mx-auto max-w-5xl p-4 md:p-6">
        <div className="flex flex-col gap-4">
          {/* Header */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-2xl md:text-3xl font-semibold tracking-tight">Echo</div>
              <div className="text-sm text-muted-foreground">
                Offline-first assistant shell · clean, minimal, and ready to wire to your orchestrator
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button variant="outline" className="rounded-2xl" onClick={clearChat}>
                <Trash2 className="h-4 w-4 mr-2" />
                Clear
              </Button>
              <Button
                className="rounded-2xl"
                onClick={toggleMic}
                variant={micOn ? "default" : "secondary"}
              >
                {micOn ? (
                  <>
                    <MicOff className="h-4 w-4 mr-2" /> Stop
                  </>
                ) : (
                  <>
                    <Mic className="h-4 w-4 mr-2" /> Listen
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Status */}
          <Card className="rounded-2xl shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Activity className="h-4 w-4" />
                System Status
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              {health ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <StatusPill label="LLM" value={health.llm} />
                  <StatusPill label="STT" value={health.stt} />
                  <StatusPill label="TTS" value={health.tts} />
                  <StatusPill label="Mode" value={health.model} />
                  <StatusPill label="Runtime" value={health.device} />
                  <StatusPill label="Backend" value={health.ok ? "Online" : "Offline"} />
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">
                  Backend not connected. {healthErr ? `(${healthErr})` : ""}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Main */}
          <div className="grid grid-cols-1 md:grid-cols-[1fr_360px] gap-4">
            {/* Chat */}
            <Card className="rounded-2xl shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Conversation</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div
                  ref={scrollerRef}
                  className="h-[52vh] md:h-[60vh] overflow-y-auto pr-2 flex flex-col gap-3"
                >
                  {msgs.map((m) => (
                    <Bubble key={m.id} msg={m} />
                  ))}
                </div>

                <Separator className="my-4" />

                <div className="flex items-center gap-2">
                  <Input
                    className="rounded-2xl"
                    placeholder="Say something that changes Echo." 
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        send();
                      }
                    }}
                  />
                  <Button className="rounded-2xl" onClick={send} disabled={!canSend}>
                    <Send className="h-4 w-4 mr-2" />
                    Send
                  </Button>
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  Tip: Enter to send · Shift+Enter for a newline (if you make the input a textarea later)
                </div>
              </CardContent>
            </Card>

            {/* Side panel */}
            <Card className="rounded-2xl shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Settings className="h-4 w-4" />
                  Controls
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <Tabs defaultValue="modes" className="w-full">
                  <TabsList className="w-full grid grid-cols-2 rounded-2xl">
                    <TabsTrigger value="modes">Modes</TabsTrigger>
                    <TabsTrigger value="privacy">Privacy</TabsTrigger>
                  </TabsList>

                  <TabsContent value="modes" className="mt-4 space-y-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <Database className="h-4 w-4" />
                        <div>
                          <div className="text-sm font-medium">Memory</div>
                          <div className="text-xs text-muted-foreground">Allow long-term recall</div>
                        </div>
                      </div>
                      <Switch checked={memoryEnabled} onCheckedChange={setMemoryEnabled} />
                    </div>

                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <Shield className="h-4 w-4" />
                        <div>
                          <div className="text-sm font-medium">Safety</div>
                          <div className="text-xs text-muted-foreground">Constrain risky actions</div>
                        </div>
                      </div>
                      <Switch checked={safetyEnabled} onCheckedChange={setSafetyEnabled} />
                    </div>

                    <Separator />

                    <div className="space-y-2">
                      <div className="text-sm font-medium">Voice</div>
                      <div className="text-xs text-muted-foreground">
                        Hook this panel to Piper voices, speed, and device output later.
                      </div>
                      <Button variant="outline" className="w-full rounded-2xl" disabled>
                        Voice settings (coming soon)
                      </Button>
                    </div>
                  </TabsContent>

                  <TabsContent value="privacy" className="mt-4 space-y-4">
                    <div className="text-sm text-muted-foreground leading-relaxed">
                      This UI is designed for local-only use. When you wire a backend, bind it to
                      <span className="font-medium"> 127.0.0.1 </span>
                      or your LAN only, and keep persistence explicit.
                    </div>
                    <Separator />
                    <div className="space-y-2">
                      <div className="text-sm font-medium">Hard rules worth keeping</div>
                      <ul className="text-sm text-muted-foreground list-disc pl-5 space-y-1">
                        <li>No remote telemetry</li>
                        <li>User-editable memory store</li>
                        <li>Clear “what Echo knows” surface</li>
                        <li>Export/import everything</li>
                      </ul>
                    </div>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

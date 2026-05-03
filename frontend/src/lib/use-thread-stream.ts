/**
 * useThreadStream — SSE streaming hook for a BnK thread run.
 *
 * SSE events received:
 *   metadata      → {run_id, thread_id}
 *   messages      → {id, role, content, delta}
 *   tool_calls    → {id, name, args, status}
 *   tool_results  → {id, content, status}
 *   values        → {messages, artifacts, step}
 *   hitl          → {tool, question, args, run_id}
 *   end           → {usage, run_id}
 *   error         → {message}
 */
"use client";

import { useCallback, useRef, useState } from "react";

const BASE = "/api";

export interface StreamMessage {
  id: string;
  role: string;
  content: string;
}

export interface ToolCallItem {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: "running" | "done" | "error";
  result?: string;
}

export interface HitlPayload {
  tool: string;
  question: string;
  args: Record<string, unknown>;
  run_id: string;
}

export interface ThreadStreamState {
  messages: StreamMessage[];
  toolCalls: ToolCallItem[];
  artifacts: string[];
  step: string;
  agentsMd: string;
  hitl: HitlPayload | null;
  isStreaming: boolean;
  error: string | null;
}

// Tool name → step mapping for pipeline progress bar
const STEP_MAP: Record<string, string> = {
  read_pdf: "intake", read_docx: "intake", read_pptx: "intake",
  read_xlsx: "intake", read_txt: "intake", list_files: "intake",
  save_technical_design_md: "solution", save_drawio_xml: "solution",
  run_wbs_workflow: "wbs", validate_wbs: "wbs",
  run_brd_workflow: "brd", validate_brd: "brd", validate_traceability: "brd",
  render_wbs: "export", render_brd: "export",
};

export function useThreadStream(threadId: string) {
  const [state, setState] = useState<ThreadStreamState>({
    messages: [],
    toolCalls: [],
    artifacts: [],
    step: "",
    agentsMd: "",
    hitl: null,
    isStreaming: false,
    error: null,
  });

  const abortRef = useRef<AbortController | null>(null);
  const msgMapRef = useRef<Map<string, StreamMessage>>(new Map());

  const handleEvent = (event: string, payload: Record<string, unknown>) => {
    switch (event) {
      case "messages": {
        const { id, role, content } = payload as {
          id: string; role: string; content: string; delta?: boolean;
        };
        setState((s) => {
          const existing = msgMapRef.current.get(id);
          if (existing) {
            const updated = { ...existing, content: existing.content + content };
            msgMapRef.current.set(id, updated);
            return { ...s, messages: s.messages.map((m) => (m.id === id ? updated : m)) };
          }
          const newMsg: StreamMessage = { id, role, content };
          msgMapRef.current.set(id, newMsg);
          return { ...s, messages: [...s.messages, newMsg] };
        });
        break;
      }
      case "tool_calls": {
        const { id, name, args } = payload as { id: string; name: string; args: Record<string, unknown> };
        const inferred = STEP_MAP[name];
        setState((s) => {
          const existing = s.toolCalls.find((t) => t.id === id);
          const updated: ToolCallItem = existing
            ? { ...existing, name: name || existing.name, status: "running" }
            : { id, name, args: args ?? {}, status: "running" };
          const toolCalls = existing
            ? s.toolCalls.map((t) => (t.id === id ? updated : t))
            : [...s.toolCalls, updated];
          return { ...s, toolCalls, step: inferred || s.step };
        });
        break;
      }
      case "tool_results": {
        const { id, content } = payload as { id: string; content: string; status: string };
        setState((s) => ({
          ...s,
          toolCalls: s.toolCalls.map((t) =>
            t.id === id ? { ...t, status: "done", result: content } : t
          ),
        }));
        break;
      }
      case "values": {
        const { artifacts, step, agents_md } = payload as {
          artifacts?: string[]; step?: string; agents_md?: string;
        };
        setState((s) => ({
          ...s,
          artifacts: artifacts ?? s.artifacts,
          step: step || s.step,
          agentsMd: agents_md ?? s.agentsMd,
        }));
        break;
      }
      case "hitl": {
        setState((s) => ({ ...s, isStreaming: false, hitl: payload as unknown as HitlPayload }));
        break;
      }
      case "end": {
        setState((s) => ({ ...s, isStreaming: false }));
        break;
      }
      case "error": {
        setState((s) => ({
          ...s,
          isStreaming: false,
          error: (payload as { message: string }).message,
        }));
        break;
      }
    }
  };

  const _consumeStream = useCallback(async (res: Response, signal: AbortSignal) => {
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let eventName = "";
    let dataLines: string[] = [];

    const flush = () => {
      if (!dataLines.length) return;
      const raw = dataLines.join("\n");
      try { handleEvent(eventName, JSON.parse(raw)); } catch { /* ignore */ }
      eventName = "";
      dataLines = [];
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done || signal.aborted) break;
      for (const line of value.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        else if (line === "") flush();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  const sendMessage = useCallback(async (message: string) => {
    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;

    msgMapRef.current.clear();
    setState((s) => ({
      ...s,
      isStreaming: true,
      error: null,
      hitl: null,
      toolCalls: [],
      messages: [...s.messages, { id: crypto.randomUUID(), role: "human", content: message }],
    }));

    try {
      const res = await fetch(`${BASE}/threads/${threadId}/runs/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
        signal: abort.signal,
      });
      await _consumeStream(res, abort.signal);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      setState((s) => ({ ...s, isStreaming: false, error: err instanceof Error ? err.message : String(err) }));
    }
  }, [threadId, _consumeStream]);

  const resumeRun = useCallback(async (
    decision: "approve" | "reject" | "edit",
    editedArgs?: Record<string, unknown>
  ) => {
    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;

    setState((s) => ({ ...s, isStreaming: true, error: null, hitl: null, toolCalls: [] }));

    try {
      const res = await fetch(`${BASE}/threads/${threadId}/runs/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, edited_args: editedArgs }),
        signal: abort.signal,
      });
      await _consumeStream(res, abort.signal);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      setState((s) => ({ ...s, isStreaming: false, error: err instanceof Error ? err.message : String(err) }));
    }
  }, [threadId, _consumeStream]);

  const clearHitl = useCallback(() => setState((s) => ({ ...s, hitl: null })), []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setState((s) => ({ ...s, isStreaming: false }));
  }, []);

  return { state, sendMessage, resumeRun, clearHitl, stop };
}

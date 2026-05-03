"use client";

import { use, useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft, FileText, AlertCircle, CheckCircle2,
  XCircle, Loader2, StopCircle, Layout,
} from "lucide-react";
import { useThreadStream } from "@/lib/use-thread-stream";
import { getThread, cancelRun, type ThreadDetail } from "@/lib/api";
import { MessageList } from "@/components/message-list";
import { HitlCard } from "@/components/hitl-card";
import { ArtifactsPanel } from "@/components/artifacts-panel";
import { InputBox } from "@/components/input-box";
import { AgentPlan } from "@/components/agent-plan";

interface PageProps {
  params: Promise<{ id: string }>;
}

// ── Thread status badge ───────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const cfg = {
    idle: {
      cls: "text-gray-400 bg-gray-800/60 border-gray-700",
      icon: <CheckCircle2 size={12} />,
      label: "Sẵn sàng",
    },
    busy: {
      cls: "text-blue-300 bg-blue-900/40 border-blue-700",
      icon: <Loader2 size={12} className="animate-spin" />,
      label: "Đang xử lý",
    },
    interrupted: {
      cls: "text-purple-300 bg-purple-900/40 border-purple-700",
      icon: <AlertCircle size={12} />,
      label: "Chờ xác nhận",
    },
    error: {
      cls: "text-red-300 bg-red-900/40 border-red-700",
      icon: <XCircle size={12} />,
      label: "Lỗi",
    },
  }[status] ?? {
    cls: "text-gray-400 bg-gray-800 border-gray-700",
    icon: null,
    label: status,
  };

  return (
    <span
      className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${cfg.cls}`}
    >
      {cfg.icon}
      {cfg.label}
    </span>
  );
}

// ── Pipeline progress bar ─────────────────────────────────────────────────────

const PIPELINE_STEPS = [
  { id: "intake",   label: "Phân tích" },
  { id: "solution", label: "Giải pháp" },
  { id: "wbs",      label: "WBS" },
  { id: "brd",      label: "BRD" },
  { id: "export",   label: "Xuất file" },
];

function PipelineBar({ step, isStreaming }: { step: string; isStreaming: boolean }) {
  if (!isStreaming && !step) return null;
  const activeIdx = PIPELINE_STEPS.findIndex((s) => s.id === step);
  return (
    <div className="flex items-center gap-1 px-4 py-2 border-b border-[var(--border)] bg-[var(--surface)] flex-shrink-0">
      {PIPELINE_STEPS.map((s, i) => {
        const done = activeIdx > i;
        const active = activeIdx === i;
        return (
          <div key={s.id} className="flex items-center gap-1 flex-1">
            <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors ${
              active  ? "bg-blue-600/30 text-blue-300 border border-blue-600/50" :
              done    ? "text-green-400" :
                        "text-gray-600"
            }`}>
              {done && <span className="text-green-400">✓</span>}
              {active && isStreaming && <Loader2 size={10} className="animate-spin" />}
              {s.label}
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <div className={`h-px flex-1 ${done || active ? "bg-blue-700" : "bg-gray-700"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ThreadPage({ params }: PageProps) {
  const { id: threadId } = use(params);
  const router = useRouter();

  const [threadDetail, setThreadDetail] = useState<ThreadDetail | null>(null);
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [artifactsRefreshKey, setArtifactsRefreshKey] = useState(0);

  const { state, sendMessage, resumeRun, clearHitl, stop } = useThreadStream(threadId);

  // ── Fetch thread detail (metadata + status from checkpointer) ───────────
  const refreshThread = useCallback(async () => {
    try {
      const detail = await getThread(threadId);
      setThreadDetail(detail);
      // If the backend reports interrupted but we don't have a local HITL payload yet,
      // the user may have refreshed the page — show a generic HITL prompt so they
      // can resume via the hitl-card.
    } catch {
      // non-fatal
    }
  }, [threadId]);

  // Poll on mount and after each stream completes
  useEffect(() => {
    refreshThread();
  }, [refreshThread]);

  useEffect(() => {
    if (!state.isStreaming) {
      refreshThread();
      setArtifactsRefreshKey((k) => k + 1);
    }
  }, [state.isStreaming, refreshThread]);

  // ── Cancel the current run ────────────────────────────────────────────────
  const handleCancel = async () => {
    stop(); // abort local SSE reader
    const runId = threadDetail?.current_run?.run_id;
    if (runId) {
      try {
        await cancelRun(threadId, runId, "interrupt");
      } catch {
        // best-effort
      }
    }
    await refreshThread();
  };

  const handleHitlResolved = async () => {
    clearHitl();
    await refreshThread();
    setArtifactsRefreshKey((k) => k + 1);
  };

  // Derive display status: prefer live streaming state over cached API status
  const displayStatus = state.isStreaming
    ? "busy"
    : state.hitl
    ? "interrupted"
    : (threadDetail?.status ?? "idle");

  // Show a generic HITL card on page refresh if backend says interrupted
  // but we don't have a live HITL payload from SSE
  const showGenericHitl =
    !state.hitl &&
    !state.isStreaming &&
    threadDetail?.status === "interrupted";

  return (
    <div className="h-screen flex flex-col bg-[var(--background)]">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border)] flex-shrink-0">
        <button
          onClick={() => router.push("/")}
          className="p-1.5 rounded-lg hover:bg-[var(--surface-hover)] text-[var(--muted)]
                     hover:text-white transition-colors"
        >
          <ArrowLeft size={18} />
        </button>

        <div className="flex-1 min-w-0">
          <h1 className="font-semibold text-white text-sm truncate">
            {threadDetail?.project_name ?? "BnK DeepAgent"}
          </h1>
          <p className="text-[10px] text-[var(--muted)] font-mono truncate">
            {threadId}
          </p>
        </div>

        <StatusBadge status={displayStatus} />

        {/* Cancel button — visible while running */}
        {state.isStreaming && (
          <button
            onClick={handleCancel}
            className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300
                       bg-red-900/30 hover:bg-red-900/50 border border-red-800 px-2.5 py-1
                       rounded-full transition-colors"
          >
            <StopCircle size={12} />
            Dừng
          </button>
        )}

        {/* Artifacts panel toggle */}
        <button
          onClick={() => setShowArtifacts(!showArtifacts)}
          className={`p-1.5 rounded-lg transition-colors ${
            showArtifacts
              ? "bg-[var(--accent)] text-white"
              : "hover:bg-[var(--surface-hover)] text-[var(--muted)] hover:text-white"
          }`}
          title={showArtifacts ? "Ẩn artifacts" : "Hiện artifacts"}
        >
          <FileText size={18} />
        </button>

        <button
          onClick={() => setShowArtifacts(!showArtifacts)}
          className="p-1.5 rounded-lg hover:bg-[var(--surface-hover)] text-[var(--muted)]
                     hover:text-white transition-colors"
          title="Layout"
        >
          <Layout size={18} />
        </button>
      </header>

      {/* ── Pipeline progress ───────────────────────────────────────────── */}
      <PipelineBar step={state.step} isStreaming={state.isStreaming} />

      {/* ── Agent plan (todo list from AGENTS.md) ───────────────────────── */}
      <AgentPlan agentsMd={state.agentsMd || (threadDetail as {agents_md?: string} | null)?.agents_md || ""} />

      {/* ── Body ────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chat column */}
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* Error banner */}
          {state.error && (
            <div className="mx-4 mt-3 flex items-center gap-2 bg-red-900/30 border border-red-800
                            text-red-300 text-sm px-4 py-2.5 rounded-xl flex-shrink-0">
              <AlertCircle size={16} className="flex-shrink-0" />
              {state.error}
            </div>
          )}

          {/* Messages */}
          <MessageList
            messages={state.messages}
            toolCalls={state.toolCalls}
            isStreaming={state.isStreaming}
          />

          {/* HITL card: live (from SSE) or page-refresh recovery */}
          {state.hitl ? (
            <HitlCard
              hitl={state.hitl}
              onResume={resumeRun}
              onResolved={handleHitlResolved}
            />
          ) : showGenericHitl ? (
            <GenericHitlBanner
              onResume={resumeRun}
              onResolved={handleHitlResolved}
            />
          ) : null}

          {/* Input */}
          <InputBox
            threadId={threadId}
            isStreaming={state.isStreaming}
            onSend={sendMessage}
            onStop={handleCancel}
            disabled={!!state.hitl || showGenericHitl}
          />
        </div>

        {/* Artifacts panel */}
        {showArtifacts && (
          <div className="w-72 flex-shrink-0 border-l border-[var(--border)] bg-[var(--surface)]
                          flex flex-col overflow-hidden">
            <ArtifactsPanel
              threadId={threadId}
              refreshKey={artifactsRefreshKey}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Page-refresh HITL recovery banner ────────────────────────────────────────

function GenericHitlBanner({
  onResume,
  onResolved,
}: {
  onResume: (decision: "approve" | "reject") => Promise<void>;
  onResolved: () => void;
}) {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  const handle = async (decision: "approve" | "reject") => {
    setLoading(decision);
    setError("");
    try {
      await onResume(decision);
      onResolved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
      setLoading(null);
    }
  };

  return (
    <div className="mx-4 my-2 rounded-2xl border border-purple-700 bg-[var(--hitl-bg)] p-4">
      <div className="flex items-center gap-2 mb-3">
        <AlertCircle size={16} className="text-purple-400 flex-shrink-0" />
        <p className="text-sm text-purple-200 font-medium">
          Agent đang chờ xác nhận từ phiên trước
        </p>
      </div>
      <p className="text-xs text-gray-400 mb-4">
        Trang đã được làm mới. Agent vẫn đang dừng tại checkpoint.
        Bạn muốn tiếp tục hay huỷ bỏ?
      </p>
      {error && (
        <p className="text-xs text-red-400 mb-3">{error}</p>
      )}
      <div className="flex gap-2">
        <button
          onClick={() => handle("approve")}
          disabled={!!loading}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500
                     text-white text-sm disabled:opacity-50 transition-colors flex-1 justify-center"
        >
          {loading === "approve" ? <Loader2 size={14} className="animate-spin" /> : null}
          Tiếp tục
        </button>
        <button
          onClick={() => handle("reject")}
          disabled={!!loading}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-red-700/60 hover:bg-red-600
                     text-white text-sm disabled:opacity-50 transition-colors"
        >
          {loading === "reject" ? <Loader2 size={14} className="animate-spin" /> : null}
          Huỷ
        </button>
      </div>
    </div>
  );
}

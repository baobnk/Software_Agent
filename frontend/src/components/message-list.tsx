"use client";

import { useEffect, useRef, useState } from "react";
import {
  Bot, User, FileText, Search, CheckCircle2,
  Loader2, AlertCircle, Wrench, FileOutput,
  ShieldCheck, Brain, Code2, ChevronDown,
} from "lucide-react";
import type { StreamMessage, ToolCallItem } from "@/lib/use-thread-stream";

// ── Tool metadata ──────────────────────────────────────────────────────────────

const TOOL_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  read_pdf:                { label: "Đọc file PDF",             icon: <FileText size={13} />,    color: "text-orange-400" },
  read_docx:               { label: "Đọc file Word",            icon: <FileText size={13} />,    color: "text-blue-400" },
  read_pptx:               { label: "Đọc file PowerPoint",      icon: <FileText size={13} />,    color: "text-red-400" },
  read_xlsx:               { label: "Đọc file Excel",           icon: <FileText size={13} />,    color: "text-green-400" },
  read_txt:                { label: "Đọc file văn bản",         icon: <FileText size={13} />,    color: "text-gray-400" },
  list_files:              { label: "Liệt kê tài liệu",         icon: <Search size={13} />,      color: "text-gray-400" },
  save_technical_design_md:{ label: "Lưu Technical Design",     icon: <Code2 size={13} />,       color: "text-cyan-400" },
  save_drawio_xml:         { label: "Lưu Architecture Diagram", icon: <Brain size={13} />,       color: "text-purple-400" },
  run_wbs_workflow:        { label: "Chạy WBS Workflow",        icon: <Wrench size={13} />,      color: "text-yellow-400" },
  validate_wbs:            { label: "Kiểm tra WBS",             icon: <ShieldCheck size={13} />, color: "text-yellow-400" },
  run_brd_workflow:        { label: "Chạy BRD Workflow",        icon: <Wrench size={13} />,      color: "text-blue-400" },
  validate_brd:            { label: "Kiểm tra BRD",             icon: <ShieldCheck size={13} />, color: "text-blue-400" },
  validate_traceability:   { label: "Kiểm tra Traceability",    icon: <ShieldCheck size={13} />, color: "text-indigo-400" },
  render_brd:              { label: "Xuất BRD (.docx)",         icon: <FileOutput size={13} />,  color: "text-green-400" },
  render_wbs:              { label: "Xuất WBS (.xlsx)",         icon: <FileOutput size={13} />,  color: "text-green-400" },
};

function getToolMeta(name: string) {
  return TOOL_META[name] ?? { label: name.replace(/_/g, " "), icon: <Wrench size={13} />, color: "text-gray-400" };
}

// ── Tool call card ─────────────────────────────────────────────────────────────

function ToolCallCard({ item }: { item: ToolCallItem }) {
  const [open, setOpen] = useState(false);
  const meta = getToolMeta(item.name);
  const isError = item.status === "error" || (item.result ?? "").startsWith("ERROR");
  const isDone = item.status === "done";
  const hasResult = isDone && item.result && item.result.length > 0;

  return (
    <div className="relative">
      <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs transition-colors ${
        isError
          ? "bg-red-950/30 border-red-800/40 text-red-400"
          : isDone
          ? "bg-gray-900/40 border-gray-800/60 text-gray-500"
          : "bg-blue-950/30 border-blue-800/40 text-blue-300 animate-pulse-subtle"
      }`}>
        {/* Status icon */}
        <span className="flex-shrink-0 w-3.5">
          {item.status === "running" ? (
            <Loader2 size={13} className="animate-spin text-blue-400" />
          ) : isError ? (
            <AlertCircle size={13} className="text-red-400" />
          ) : (
            <CheckCircle2 size={13} className="text-green-500" />
          )}
        </span>

        {/* Tool icon */}
        <span className={`flex-shrink-0 ${isDone ? "text-gray-600" : meta.color}`}>
          {meta.icon}
        </span>

        {/* Label */}
        <span className={isDone ? "text-gray-500" : "text-gray-300 font-medium"}>
          {meta.label}
        </span>

        {/* Result toggle */}
        {hasResult && (
          <button
            onClick={() => setOpen(!open)}
            className="ml-auto flex-shrink-0 text-gray-700 hover:text-gray-400 transition-colors"
          >
            <ChevronDown size={12} className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
          </button>
        )}
      </div>

      {/* Expanded result */}
      {open && hasResult && (
        <div className="mt-1 ml-6 bg-gray-950 border border-gray-800 rounded-lg p-3 text-xs text-gray-400 font-mono max-h-40 overflow-y-auto whitespace-pre-wrap">
          {item.result}
        </div>
      )}
    </div>
  );
}

// ── Agent activity section (group of tool calls) ───────────────────────────────

function AgentActivity({ toolCalls, isStreaming }: { toolCalls: ToolCallItem[]; isStreaming: boolean }) {
  if (toolCalls.length === 0) return null;
  const runningCount = toolCalls.filter(t => t.status === "running").length;

  return (
    <div className="ml-9 mt-2 space-y-1">
      {/* Running label */}
      {isStreaming && runningCount > 0 && (
        <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1.5 font-medium">
          Đang thực thi...
        </p>
      )}
      {toolCalls.map((tc) => (
        <ToolCallCard key={tc.id} item={tc} />
      ))}
    </div>
  );
}

// ── Message bubbles ────────────────────────────────────────────────────────────

function UserMessage({ msg }: { msg: StreamMessage }) {
  return (
    <div className="flex items-end gap-2 flex-row-reverse">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gray-600 flex items-center justify-center">
        <User size={14} className="text-white" />
      </div>
      <div className="max-w-[72%] bg-[var(--accent)] text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm leading-relaxed">
        {msg.content}
      </div>
    </div>
  );
}

function AssistantMessage({ msg }: { msg: StreamMessage }) {
  const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const rendered = esc(msg.content)
    .replace(/```(\w*)\n?([\s\S]*?)```/g, (_, _l, code) => `<pre><code>${code.trim()}</code></pre>`)
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>[^<]*<\/li>\n?)+/g, m => `<ul>${m}</ul>`)
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br/>");

  return (
    <div className="flex items-start gap-2">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[var(--accent)] flex items-center justify-center mt-0.5">
        <Bot size={14} className="text-white" />
      </div>
      <div className="max-w-[82%] bg-[var(--surface)] border border-[var(--border)] rounded-2xl rounded-tl-sm px-4 py-3">
        <div className="prose-dark text-sm" dangerouslySetInnerHTML={{ __html: `<p>${rendered}</p>` }} />
      </div>
    </div>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex items-start gap-2">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[var(--accent)]/60 flex items-center justify-center mt-0.5">
        <Bot size={14} className="text-white/70" />
      </div>
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl rounded-tl-sm px-4 py-3">
        <div className="flex gap-1.5 items-center h-4">
          <div className="typing-dot w-1.5 h-1.5 bg-[var(--muted)] rounded-full" />
          <div className="typing-dot w-1.5 h-1.5 bg-[var(--muted)] rounded-full" />
          <div className="typing-dot w-1.5 h-1.5 bg-[var(--muted)] rounded-full" />
        </div>
      </div>
    </div>
  );
}

// ── Public component ──────────────────────────────────────────────────────────

interface Props {
  messages: StreamMessage[];
  toolCalls: ToolCallItem[];
  isStreaming: boolean;
}

export function MessageList({ messages, toolCalls, isStreaming }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, toolCalls, isStreaming]);

  if (messages.length === 0 && toolCalls.length === 0 && !isStreaming) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="w-14 h-14 rounded-2xl bg-[var(--accent)]/10 border border-[var(--accent)]/20 flex items-center justify-center mx-auto mb-4">
            <Bot size={28} className="text-[var(--accent)]/60" />
          </div>
          <p className="text-sm font-medium text-gray-300">BnK DeepAgent</p>
          <p className="text-xs mt-1 text-gray-600">Gửi tin nhắn để bắt đầu phân tích yêu cầu</p>
        </div>
      </div>
    );
  }

  const lastMsg = messages[messages.length - 1];
  const lastIsAssistant = lastMsg && lastMsg.role !== "human";
  const hasActiveTools = toolCalls.length > 0;
  const allToolsDone = toolCalls.every(t => t.status === "done");
  const showThinking = isStreaming && !hasActiveTools && !lastIsAssistant;

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
      {messages.map((msg, i) => {
        const isLast = i === messages.length - 1;
        return (
          <div key={msg.id}>
            {msg.role === "human" ? (
              <UserMessage msg={msg} />
            ) : (
              <AssistantMessage msg={msg} />
            )}
            {/* Tool calls shown after the last assistant message */}
            {isLast && lastIsAssistant && hasActiveTools && (
              <AgentActivity toolCalls={toolCalls} isStreaming={isStreaming} />
            )}
          </div>
        );
      })}

      {/* Tool calls before first assistant reply (intake phase) */}
      {hasActiveTools && !lastIsAssistant && (
        <AgentActivity toolCalls={toolCalls} isStreaming={isStreaming} />
      )}

      {/* Thinking dots: streaming but no active tools and no last assistant msg */}
      {showThinking && <ThinkingIndicator />}

      {/* Thinking dots: all tools done but still streaming (agent composing reply) */}
      {isStreaming && allToolsDone && hasActiveTools && !lastIsAssistant && (
        <ThinkingIndicator />
      )}

      <div ref={bottomRef} />
    </div>
  );
}

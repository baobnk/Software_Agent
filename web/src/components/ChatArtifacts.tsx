import { useCoAgentStateRender } from "@copilotkit/react-core";
import { useState, useCallback, useRef, useEffect } from "react";
import { Download, Eye, X, Loader2, CheckCircle2 } from "lucide-react";
import {
  artifactDownloadUrl,
  workspaceFileUrl,
  type RenderedFile,
} from "../api";

// ── Tool metadata ──────────────────────────────────────────────────────────────

const TOOL_META: Record<string, { label: string; color: string; emoji: string }> = {
  list_input_files:         { label: "Liệt kê file đầu vào",          color: "#60a5fa", emoji: "🔍" },
  read_file:                { label: "Đọc file yêu cầu",              color: "#60a5fa", emoji: "📂" },
  read_txt:                 { label: "Đọc nội dung file",             color: "#60a5fa", emoji: "📂" },
  write_todos:              { label: "Cập nhật kế hoạch",             color: "#94a3b8", emoji: "📋" },
  ls:                       { label: "Kiểm tra thư mục",              color: "#94a3b8", emoji: "🗂️" },
  save_raw_features:        { label: "Lưu đặc tả tính năng",         color: "#a78bfa", emoji: "💾" },
  save_technical_design_md:           { label: "Lưu thiết kế kỹ thuật",       color: "#a78bfa", emoji: "🏗️" },
  patch_solution_section:             { label: "Cập nhật solution",            color: "#a78bfa", emoji: "✏️" },
  confirm_diagram_generation:         { label: "Xác nhận tạo sơ đồ",          color: "#f59e0b", emoji: "✅" },
  generate_technical_design_diagram:  { label: "Tạo sơ đồ kiến trúc",         color: "#f59e0b", emoji: "🗺️" },
  export_diagram_png:                 { label: "Xuất sơ đồ PNG",              color: "#f59e0b", emoji: "🖼️" },
  run_wbs_workflow:         { label: "Chạy WBS Workflow",             color: "#34d399", emoji: "📊" },
  init_wbs:                 { label: "Khởi tạo WBS",                  color: "#34d399", emoji: "📊" },
  set_master_data:          { label: "Thiết lập master data",         color: "#34d399", emoji: "📊" },
  upsert_task:              { label: "Cập nhật task WBS",             color: "#34d399", emoji: "📊" },
  get_wbs_summary:          { label: "Xem tóm tắt WBS",              color: "#34d399", emoji: "📊" },
  validate_wbs:             { label: "Kiểm tra WBS",                  color: "#34d399", emoji: "✅" },
  render_wbs:               { label: "Xuất WBS Excel",                color: "#f472b6", emoji: "⚡" },
  run_brd_workflow:         { label: "Chạy BRD Workflow",             color: "#fb923c", emoji: "📄" },
  init_brd:                 { label: "Khởi tạo BRD",                  color: "#fb923c", emoji: "📄" },
  set_brd_text:             { label: "Soạn nội dung BRD",             color: "#fb923c", emoji: "📝" },
  add_brd_list_item:        { label: "Thêm mục BRD",                  color: "#fb923c", emoji: "📝" },
  upsert_fr:                { label: "Cập nhật yêu cầu chức năng",    color: "#fb923c", emoji: "📝" },
  get_brd_summary:          { label: "Xem tóm tắt BRD",              color: "#fb923c", emoji: "📄" },
  validate_brd:             { label: "Kiểm tra BRD",                  color: "#fb923c", emoji: "✅" },
  validate_traceability:    { label: "Kiểm tra traceability",         color: "#fb923c", emoji: "✅" },
  render_brd:               { label: "Xuất BRD Word",                 color: "#f472b6", emoji: "⚡" },
};

function getMeta(name: string) {
  return TOOL_META[name] ?? { label: name, color: "#64748b", emoji: "⚙️" };
}

// ── File type metadata ─────────────────────────────────────────────────────────

const FILE_META: Record<string, { icon: string; color: string; bgColor: string }> = {
  XLSX:   { icon: "📊", color: "#22c55e", bgColor: "rgba(34,197,94,0.12)" },
  DOCX:   { icon: "📄", color: "#60a5fa", bgColor: "rgba(96,165,250,0.12)" },
  MD:     { icon: "📝", color: "#a78bfa", bgColor: "rgba(167,139,250,0.12)" },
  DRAWIO: { icon: "🗺️", color: "#f59e0b", bgColor: "rgba(245,158,11,0.12)" },
  PDF:    { icon: "📕", color: "#f87171", bgColor: "rgba(248,113,113,0.12)" },
  PNG:    { icon: "🖼️", color: "#a78bfa", bgColor: "rgba(167,139,250,0.12)" },
};

// ── Agent state shape (from StateSnapshotEvent) ────────────────────────────────

interface AgentState {
  completed_steps?: string[];
  active_tool?: string;
  rendered_files?: RenderedFile[];
  status?: string;
}

// ── Progress Timeline ──────────────────────────────────────────────────────────

function ProgressTimeline({
  steps, activeTool, running,
}: {
  steps: string[];
  activeTool?: string;
  running: boolean;
}) {
  const showActive = running && activeTool && !steps.includes(activeTool);
  const displayLabel = running
    ? activeTool
      ? getMeta(activeTool).label
      : steps.length > 0
        ? getMeta(steps[steps.length - 1]).label
        : "Agent đang khởi động…"
    : `Hoàn tất — ${steps.length} bước`;

  // Show last 12 steps to avoid overflow
  const visibleSteps = steps.slice(-12);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        {running
          ? <Loader2 size={13} className="spin" style={{ color: "#2563eb" }} />
          : <CheckCircle2 size={13} style={{ color: "#34d399" }} />}
        <span style={{
          fontSize: 13, fontWeight: 600,
          color: running ? "#e2e8f0" : "#34d399",
        }}>
          {displayLabel}
        </span>
      </div>

      {/* Step list */}
      {(visibleSteps.length > 0 || showActive) && (
        <div style={{ paddingLeft: 4, display: "flex", flexDirection: "column", gap: 1 }}>
          {visibleSteps.map((step, i) => {
            const m = getMeta(step);
            const isLast = i === visibleSteps.length - 1 && !showActive;
            const isActive = isLast && running;
            return (
              <div key={`${step}-${i}`} style={{
                display: "flex", alignItems: "center", gap: 6, padding: "2px 0",
                opacity: isActive ? 1 : 0.55,
              }}>
                <span style={{ fontSize: 11, width: 16, textAlign: "center" }}>{m.emoji}</span>
                <span style={{
                  fontSize: 11, color: isActive ? "#e2e8f0" : "#64748b",
                  fontWeight: isActive ? 600 : 400,
                }}>
                  {m.label}
                </span>
                {isActive && <Loader2 size={9} className="spin" style={{ color: m.color }} />}
              </div>
            );
          })}

          {showActive && activeTool && (() => {
            const m = getMeta(activeTool);
            return (
              <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "2px 0" }}>
                <span style={{ fontSize: 11, width: 16, textAlign: "center" }}>{m.emoji}</span>
                <span style={{ fontSize: 11, color: "#e2e8f0", fontWeight: 600 }}>{m.label}</span>
                <Loader2 size={9} className="spin" style={{ color: m.color }} />
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

// ── File Card (ChatGPT-style) ──────────────────────────────────────────────────

function FileCard({
  file, canPreview, onPreview, onDownload,
}: {
  file: RenderedFile;
  canPreview: boolean;
  onPreview: () => void;
  onDownload: () => void;
}) {
  const meta = FILE_META[file.type] ?? { icon: "📁", color: "#94a3b8", bgColor: "rgba(148,163,184,0.1)" };

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      background: "#1a2236",
      border: "1px solid #1e293b",
      borderRadius: 10,
      padding: "10px 14px",
    }}>
      <div style={{
        width: 38, height: 38, borderRadius: 8, flexShrink: 0,
        background: meta.bgColor,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 20,
      }}>
        {meta.icon}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 13, fontWeight: 600, color: "#e2e8f0",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {file.name}
        </div>
        <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>
          {file.type}{file.source === "workspace" ? " · Workspace" : ""}
        </div>
      </div>

      <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
        {canPreview && (
          <button
            onClick={onPreview}
            title="Xem trước"
            style={{
              display: "flex", alignItems: "center", gap: 5,
              background: "rgba(96,165,250,0.1)",
              border: "1px solid rgba(96,165,250,0.25)",
              borderRadius: 7, padding: "5px 10px",
              color: "#60a5fa", cursor: "pointer", fontSize: 11, fontWeight: 600,
            }}
          >
            <Eye size={12} />
            <span>Xem</span>
          </button>
        )}
        <button
          onClick={onDownload}
          title="Tải về"
          style={{
            display: "flex", alignItems: "center", gap: 5,
            background: "rgba(52,211,153,0.1)",
            border: "1px solid rgba(52,211,153,0.25)",
            borderRadius: 7, padding: "5px 10px",
            color: "#34d399", cursor: "pointer", fontSize: 11, fontWeight: 600,
          }}
        >
          <Download size={12} />
          <span>Tải</span>
        </button>
      </div>
    </div>
  );
}

// ── Shared Preview Modal ───────────────────────────────────────────────────────

function PreviewModal({ name, icon, subtitle, onClose, onDownload, children }: {
  name: string; icon: string; subtitle?: string;
  onClose: () => void; onDownload: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(0,0,0,0.75)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#111827", border: "1px solid #1e293b", borderRadius: 16,
          width: "min(96vw, 1100px)", maxHeight: "88vh",
          display: "flex", flexDirection: "column", overflow: "hidden",
          boxShadow: "0 24px 80px rgba(0,0,0,0.85)",
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{
          display: "flex", alignItems: "center", gap: 12,
          padding: "14px 20px", borderBottom: "1px solid #1e293b", flexShrink: 0,
        }}>
          <span style={{ fontSize: 22 }}>{icon}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 14, fontWeight: 700, color: "#e2e8f0",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {name}
            </div>
            {subtitle && <div style={{ fontSize: 11, color: "#475569", marginTop: 1 }}>{subtitle}</div>}
          </div>
          <button
            onClick={onDownload}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              background: "#2563eb", color: "#fff", border: "none",
              borderRadius: 8, padding: "7px 14px", fontSize: 12, fontWeight: 600,
              cursor: "pointer", flexShrink: 0,
            }}
          >
            <Download size={13} /><span>Tải về</span>
          </button>
          <button
            onClick={onClose}
            style={{
              background: "rgba(255,255,255,0.05)", border: "1px solid #1e293b",
              borderRadius: 8, color: "#94a3b8", cursor: "pointer",
              padding: "7px 8px", display: "flex", alignItems: "center", flexShrink: 0,
            }}
          >
            <X size={14} />
          </button>
        </div>
        <div style={{ flex: 1, overflow: "auto" }}>{children}</div>
      </div>
    </div>
  );
}

function LoadingPane() {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      height: 200, gap: 10, color: "#475569", fontSize: 13,
    }}>
      <Loader2 size={16} className="spin" /><span>Đang tải…</span>
    </div>
  );
}

function ErrorPane({ message }: { message: string }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      height: 200, color: "#f87171", fontSize: 13, padding: 24,
    }}>
      ⚠ {message}
    </div>
  );
}

// ── XLSX Preview ───────────────────────────────────────────────────────────────

interface SheetHtml { name: string; html: string; }

function buildXlsxDoc(tableHtml: string): string {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{box-sizing:border-box}
    body{margin:0;padding:6px 10px;font-family:Calibri,"Segoe UI",Arial,sans-serif;font-size:11px;background:#fff;color:#111}
    table{border-collapse:collapse;width:max-content;min-width:100%}
    td,th{border:1px solid #c6c6c6;padding:3px 6px;white-space:nowrap;vertical-align:middle}
    tr:first-child td,tr:first-child th{font-weight:700}
  </style></head><body>${tableHtml}</body></html>`;
}

function XlsxPreview({ url, name, onClose, onDownload }: {
  url: string; name: string; onClose: () => void; onDownload: () => void;
}) {
  const [sheets, setSheets] = useState<SheetHtml[]>([]);
  const [activeSheet, setActiveSheet] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const XLSX = await import("xlsx");
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const buf = await resp.arrayBuffer();
        const wb = XLSX.read(buf, { type: "array", cellStyles: true, cellHTML: true });
        const result: SheetHtml[] = wb.SheetNames
          .slice(1, 5)
          .map(sheetName => {
            const ws = wb.Sheets[sheetName];
            const html = XLSX.utils.sheet_to_html(ws, { editable: false, id: `ws-${sheetName}` });
            return { name: sheetName, html };
          })
          .filter(s => s.html.includes("<td") || s.html.includes("<th"));
        if (!cancelled) { setSheets(result); setActiveSheet(0); setLoading(false); }
      } catch (e) {
        if (!cancelled) { setError(String(e)); setLoading(false); }
      }
    })();
    return () => { cancelled = true; };
  }, [url]);

  const sheet = sheets[activeSheet];
  return (
    <PreviewModal
      name={name} icon="📊"
      subtitle={sheets.length ? `Sheet ${activeSheet + 1} / ${sheets.length}` : undefined}
      onClose={onClose} onDownload={onDownload}
    >
      {sheets.length > 1 && (
        <div style={{
          display: "flex", gap: 4, padding: "8px 16px",
          borderBottom: "1px solid #1e293b", overflowX: "auto",
          flexShrink: 0, background: "#0f172a",
        }}>
          {sheets.map((s, i) => (
            <button key={i} onClick={() => setActiveSheet(i)} style={{
              background: i === activeSheet ? "#2563eb" : "rgba(255,255,255,0.06)",
              border: "1px solid",
              borderColor: i === activeSheet ? "#2563eb" : "#1e293b",
              borderRadius: 6, color: i === activeSheet ? "#fff" : "#94a3b8",
              fontSize: 11, fontWeight: 600, padding: "4px 14px",
              cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0,
            }}>{s.name}</button>
          ))}
        </div>
      )}
      {loading && <LoadingPane />}
      {error && <ErrorPane message={error} />}
      {!loading && !error && sheet && (
        <iframe
          key={activeSheet}
          srcDoc={buildXlsxDoc(sheet.html)}
          sandbox="allow-same-origin"
          style={{ width: "100%", height: "calc(88vh - 120px)", border: "none", display: "block" }}
          title={sheet.name}
        />
      )}
    </PreviewModal>
  );
}

// ── DOCX Preview ───────────────────────────────────────────────────────────────

function DocxPreview({ url, name, onClose, onDownload }: {
  url: string; name: string; onClose: () => void; onDownload: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // @ts-ignore
        const { renderAsync } = await import("docx-preview");
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const blob = await resp.blob();
        if (!cancelled && containerRef.current) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const opts: any = { className: "docx-preview-body", inWrapper: false, defaultFont: { name: "Calibri", size: 11 } };
          await renderAsync(blob, containerRef.current, undefined, opts);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) { setError(String(e)); setLoading(false); }
      }
    })();
    return () => { cancelled = true; };
  }, [url]);

  return (
    <PreviewModal name={name} icon="📄" subtitle="Tài liệu Word" onClose={onClose} onDownload={onDownload}>
      {loading && <LoadingPane />}
      {error && <ErrorPane message={error} />}
      <div
        ref={containerRef}
        style={{
          padding: "24px 32px", background: "#fff", color: "#111", minHeight: 200,
          display: loading || error ? "none" : "block",
        }}
      />
    </PreviewModal>
  );
}

// ── Markdown Preview ───────────────────────────────────────────────────────────

function MdPreview({ url, name, onClose, onDownload }: {
  url: string; name: string; onClose: () => void; onDownload: () => void;
}) {
  const [iframeDoc, setIframeDoc] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [resp, { marked }] = await Promise.all([
          fetch(url),
          import("marked"),
        ]);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const text = await resp.text();
        const html = String(await marked(text));
        const doc = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
          body{margin:0;padding:24px 32px;font-family:system-ui,sans-serif;font-size:14px;line-height:1.75;color:#1e293b;background:#f8fafc}
          h1,h2,h3,h4{color:#0f172a;margin-top:1.4em;margin-bottom:0.4em;line-height:1.3}
          h1{font-size:1.7em;border-bottom:2px solid #e2e8f0;padding-bottom:0.3em}
          h2{font-size:1.35em;border-bottom:1px solid #e2e8f0;padding-bottom:0.2em}
          code{background:#e2e8f0;padding:1px 5px;border-radius:4px;font-size:0.87em;font-family:monospace}
          pre{background:#1e293b;color:#e2e8f0;padding:16px;border-radius:8px;overflow-x:auto;margin:1em 0}
          pre code{background:none;padding:0;color:inherit}
          table{border-collapse:collapse;width:100%;margin:1em 0}
          th,td{border:1px solid #cbd5e1;padding:8px 12px;text-align:left}
          th{background:#f1f5f9;font-weight:600}
          a{color:#2563eb}
          blockquote{border-left:4px solid #2563eb;margin:1em 0;padding:0.5em 1em;color:#475569;background:#f0f7ff;border-radius:0 6px 6px 0}
          ul,ol{padding-left:1.5em}
          li{margin:0.3em 0}
          hr{border:none;border-top:2px solid #e2e8f0;margin:1.5em 0}
          img{max-width:100%;border-radius:6px}
        </style></head><body>${html}</body></html>`;
        if (!cancelled) { setIframeDoc(doc); setLoading(false); }
      } catch (e) {
        if (!cancelled) { setError(String(e)); setLoading(false); }
      }
    })();
    return () => { cancelled = true; };
  }, [url]);

  return (
    <PreviewModal name={name} icon="📝" subtitle="Tài liệu Markdown" onClose={onClose} onDownload={onDownload}>
      {loading && <LoadingPane />}
      {error && <ErrorPane message={error} />}
      {!loading && !error && iframeDoc && (
        <iframe
          srcDoc={iframeDoc}
          sandbox="allow-same-origin"
          style={{ width: "100%", height: "calc(88vh - 80px)", border: "none", display: "block" }}
          title={name}
        />
      )}
    </PreviewModal>
  );
}

// ── PNG Preview ────────────────────────────────────────────────────────────────

function PngPreview({ url, name, onClose, onDownload }: {
  url: string; name: string; onClose: () => void; onDownload: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  return (
    <PreviewModal name={name} icon="🖼️" subtitle="Sơ đồ kiến trúc" onClose={onClose} onDownload={onDownload}>
      {loading && <LoadingPane />}
      {error && <ErrorPane message={error} />}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 24, background: "#0f172a", minHeight: 200,
      }}>
        <img
          src={url}
          alt={name}
          onLoad={() => setLoading(false)}
          onError={() => { setLoading(false); setError("Không tải được ảnh."); }}
          style={{
            maxWidth: "100%", maxHeight: "calc(88vh - 100px)",
            borderRadius: 8, display: loading || error ? "none" : "block",
            boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
          }}
        />
      </div>
    </PreviewModal>
  );
}

// ── ChatArtifacts — injects progress + file cards into CopilotKit chat ─────────

export function ChatArtifacts({ threadId }: { threadId: string }) {
  const [previewFile, setPreviewFile] = useState<RenderedFile | null>(null);

  const handleDownload = useCallback(async (file: RenderedFile) => {
    try {
      const url = file.source === "artifact"
        ? artifactDownloadUrl(threadId, file.path)
        : workspaceFileUrl(threadId, file.path);
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch (e) {
      console.error("Download failed:", e);
    }
  }, [threadId]);

  useCoAgentStateRender<AgentState>({
    name: "bnk_main_agent",
    render: ({ state, status }) => {
      const steps = state?.completed_steps ?? [];
      const activeTool = state?.active_tool;
      const files = state?.rendered_files ?? [];
      const running = status === "inProgress";

      // Nothing to show yet
      if (running && steps.length === 0 && files.length === 0) return null;
      if (!running && files.length === 0) return null;

      return (
        <div style={{
          display: "flex", flexDirection: "column", gap: 10,
          background: "#111827", border: "1px solid #1e293b",
          borderRadius: 12, padding: "14px 16px",
          maxWidth: 560,
        }}>
          {/* Progress timeline — only while running */}
          {running && (
            <ProgressTimeline steps={steps} activeTool={activeTool} running={true} />
          )}

          {/* Completion header — only when done */}
          {!running && steps.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <CheckCircle2 size={14} style={{ color: "#34d399" }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: "#34d399" }}>
                Hoàn tất — {steps.length} bước
              </span>
            </div>
          )}

          {/* File cards — shown as soon as files are ready (during or after run) */}
          {files.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {files.map(f => (
                <FileCard
                  key={f.path}
                  file={f}
                  canPreview={["XLSX", "DOCX", "MD", "PNG"].includes(f.type)}
                  onPreview={() => setPreviewFile(f)}
                  onDownload={() => handleDownload(f)}
                />
              ))}
            </div>
          )}
        </div>
      );
    },
  });

  // Preview modals rendered at component level (position:fixed overlays everything)
  if (!previewFile) return null;

  const url = previewFile.source === "artifact"
    ? artifactDownloadUrl(threadId, previewFile.path)
    : workspaceFileUrl(threadId, previewFile.path);

  const onClose = () => setPreviewFile(null);
  const onDownload = () => handleDownload(previewFile);

  if (previewFile.type === "XLSX") {
    return <XlsxPreview url={url} name={previewFile.name} onClose={onClose} onDownload={onDownload} />;
  }
  if (previewFile.type === "DOCX") {
    return <DocxPreview url={url} name={previewFile.name} onClose={onClose} onDownload={onDownload} />;
  }
  if (previewFile.type === "MD") {
    return <MdPreview url={url} name={previewFile.name} onClose={onClose} onDownload={onDownload} />;
  }
  if (previewFile.type === "PNG") {
    return <PngPreview url={url} name={previewFile.name} onClose={onClose} onDownload={onDownload} />;
  }

  return null;
}

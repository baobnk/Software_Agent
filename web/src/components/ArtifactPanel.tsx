import { useState, useEffect, useCallback, useRef } from "react";
import { useCoAgent } from "@copilotkit/react-core";
import { listOutputs, artifactDownloadUrl, downloadArtifact, Artifact } from "../api";
import { Download, Eye, X, RefreshCw, Loader2 } from "lucide-react";

const EXT_ICON: Record<string, string> = {
  XLSX: "📊",
  DOCX: "📄",
  PDF: "📕",
  MD: "📝",
  PNG: "🖼️",
  JPG: "🖼️",
  DRAWIO: "🗂️",
};

interface Props { threadId: string; }

// ── Shared modal shell ────────────────────────────────────────────────────────
function PreviewModal({ name, icon, subtitle, onClose, onDownload, children }: {
  name: string; icon: string; subtitle?: string;
  onClose: () => void; onDownload: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}
      onClick={onClose}
    >
      <div
        style={{ background: "#111827", border: "1px solid #1e293b", borderRadius: 16, width: "min(96vw, 1100px)", maxHeight: "88vh", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 24px 80px rgba(0,0,0,0.85)" }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 20px", borderBottom: "1px solid #1e293b", flexShrink: 0 }}>
          <span style={{ fontSize: 22 }}>{icon}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#e2e8f0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</div>
            {subtitle && <div style={{ fontSize: 11, color: "#475569", marginTop: 1 }}>{subtitle}</div>}
          </div>
          <button onClick={onDownload} style={{ display: "flex", alignItems: "center", gap: 6, background: "#2563eb", color: "#fff", border: "none", borderRadius: 8, padding: "7px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer", flexShrink: 0 }}>
            <Download size={13} /><span>Tải về</span>
          </button>
          <button onClick={onClose} style={{ background: "rgba(255,255,255,0.05)", border: "1px solid #1e293b", borderRadius: 8, color: "#94a3b8", cursor: "pointer", padding: "7px 8px", display: "flex", alignItems: "center", flexShrink: 0 }}>
            <X size={14} />
          </button>
        </div>
        <div style={{ flex: 1, overflow: "auto" }}>{children}</div>
      </div>
    </div>
  );
}

function LoadingPane() {
  return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 200, gap: 10, color: "#475569", fontSize: 13 }}><Loader2 size={16} className="spin" /><span>Đang tải…</span></div>;
}

function ErrorPane({ message }: { message: string }) {
  return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 200, color: "#f87171", fontSize: 13, padding: 24 }}>⚠ {message}</div>;
}

// ── XLSX Preview — rich HTML rendering via sheet_to_html ─────────────────────
interface SheetHtml { name: string; html: string; }

// Wrap the raw HTML table from xlsx in a full document for the iframe
function buildIframeDoc(tableHtml: string): string {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{box-sizing:border-box}
    body{margin:0;padding:6px 10px;font-family:Calibri,"Segoe UI",Arial,sans-serif;font-size:11px;background:#fff;color:#111}
    table{border-collapse:collapse;width:max-content;min-width:100%}
    td,th{border:1px solid #c6c6c6;padding:3px 6px;white-space:nowrap;vertical-align:middle}
    tr:first-child td,tr:first-child th{font-weight:700}
  </style></head><body>${tableHtml}</body></html>`;
}

function XlsxPreview({ url, name, onClose, onDownload }: { url: string; name: string; onClose: () => void; onDownload: () => void; }) {
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
        // cellStyles: true preserves fill colors, fonts, borders
        const wb = XLSX.read(buf, { type: "array", cellStyles: true, cellHTML: true });

        // Skip sheet 0 ("How to use"), keep sheets 1–4
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
    <PreviewModal name={name} icon="📊" subtitle={`Sheet ${activeSheet + 1} / ${sheets.length}`} onClose={onClose} onDownload={onDownload}>
      {/* Sheet tabs — only sheets 1–4 */}
      {sheets.length > 1 && (
        <div style={{ display: "flex", gap: 4, padding: "8px 16px", borderBottom: "1px solid #1e293b", overflowX: "auto", flexShrink: 0, background: "#0f172a" }}>
          {sheets.map((s, i) => (
            <button key={i} onClick={() => setActiveSheet(i)} style={{ background: i === activeSheet ? "#2563eb" : "rgba(255,255,255,0.06)", border: "1px solid", borderColor: i === activeSheet ? "#2563eb" : "#1e293b", borderRadius: 6, color: i === activeSheet ? "#fff" : "#94a3b8", fontSize: 11, fontWeight: 600, padding: "4px 14px", cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0 }}>{s.name}</button>
          ))}
        </div>
      )}

      {loading && <LoadingPane />}
      {error && <ErrorPane message={error} />}

      {/* Render via iframe so Excel inline styles are isolated from our dark theme */}
      {!loading && !error && sheet && (
        <iframe
          key={activeSheet}
          srcDoc={buildIframeDoc(sheet.html)}
          sandbox="allow-same-origin"
          style={{ width: "100%", height: "calc(88vh - 120px)", border: "none", display: "block" }}
          title={sheet.name}
        />
      )}
    </PreviewModal>
  );
}

// ── DOCX Preview ──────────────────────────────────────────────────────────────
function DocxPreview({ url, name, onClose, onDownload }: { url: string; name: string; onClose: () => void; onDownload: () => void; }) {
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
      <div ref={containerRef} style={{ padding: "24px 32px", background: "#fff", color: "#111", minHeight: 200, display: loading || error ? "none" : "block" }} />
    </PreviewModal>
  );
}

// ── Artifact row ──────────────────────────────────────────────────────────────
function ArtifactItem({ artifact, threadId }: { artifact: Artifact; threadId: string }) {
  const [showPreview, setShowPreview] = useState(false);
  const [dlLoading, setDlLoading] = useState(false);
  const [dlError, setDlError] = useState<string | null>(null);

  const canPreview = artifact.type === "XLSX" || artifact.type === "DOCX";
  const downloadUrl = artifactDownloadUrl(threadId, artifact.path);

  const handleDownload = useCallback(async () => {
    setDlError(null);
    setDlLoading(true);
    try {
      await downloadArtifact(threadId, artifact);
    } catch (e) {
      setDlError(String(e));
    } finally {
      setDlLoading(false);
    }
  }, [threadId, artifact]);

  return (
    <>
      {/* Single row: icon | name | size | [eye] [dl] */}
      <div style={{
        display: "flex", alignItems: "center", gap: 6,
        padding: "7px 10px", borderRadius: 8,
        background: "var(--bg-elevated)", border: "1px solid var(--border)",
        marginBottom: 5, fontSize: 12,
      }}>
        <span style={{ fontSize: 15, flexShrink: 0 }}>{EXT_ICON[artifact.type] ?? "📁"}</span>
        <span style={{ flex: 1, fontWeight: 500, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
          {artifact.name}
        </span>
        <span style={{ color: "var(--text-muted)", fontSize: 10, flexShrink: 0 }}>{artifact.size_kb}K</span>

        {canPreview && (
          <button
            onClick={() => setShowPreview(true)}
            title="Xem trước"
            style={{ background: "rgba(96,165,250,0.15)", border: "1px solid rgba(96,165,250,0.3)", borderRadius: 5, color: "#60a5fa", cursor: "pointer", padding: "3px 6px", display: "flex", alignItems: "center", flexShrink: 0 }}
          >
            <Eye size={11} />
          </button>
        )}
        <button
          onClick={handleDownload}
          disabled={dlLoading}
          title="Tải về"
          style={{ background: "rgba(52,211,153,0.15)", border: "1px solid rgba(52,211,153,0.3)", borderRadius: 5, color: "#34d399", cursor: dlLoading ? "not-allowed" : "pointer", opacity: dlLoading ? 0.6 : 1, padding: "3px 6px", display: "flex", alignItems: "center", flexShrink: 0 }}
        >
          {dlLoading ? <Loader2 size={11} className="spin" /> : <Download size={11} />}
        </button>
      </div>

      {dlError && <div style={{ fontSize: 10, color: "#f87171", padding: "0 0 4px 4px" }}>{dlError}</div>}

      {showPreview && artifact.type === "XLSX" && (
        <XlsxPreview url={downloadUrl} name={artifact.name} onClose={() => setShowPreview(false)} onDownload={handleDownload} />
      )}
      {showPreview && artifact.type === "DOCX" && (
        <DocxPreview url={downloadUrl} name={artifact.name} onClose={() => setShowPreview(false)} onDownload={handleDownload} />
      )}
    </>
  );
}

// ── Panel ─────────────────────────────────────────────────────────────────────
export function ArtifactPanel({ threadId }: Props) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(false);
  const prevRunning = useRef<boolean | null>(null);

  // Subscribe to agent state so we can refresh when the run finishes
  const { running } = useCoAgent({ name: "bnk_main_agent", initialState: {} });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setArtifacts(await listOutputs(threadId));
    } catch { /* silently ignore */ }
    finally { setLoading(false); }
  }, [threadId]);

  // Refresh on mount and every 15 s
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15_000);
    return () => clearInterval(id);
  }, [refresh]);

  // Also refresh immediately when agent transitions from running → stopped
  useEffect(() => {
    if (prevRunning.current === true && running === false) {
      refresh();
    }
    prevRunning.current = running;
  }, [running, refresh]);

  return (
    <div className="sidebar-section">
      <h3 style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span>📦 File xuất</span>
        <button
          onClick={refresh}
          style={{ background: "none", border: "none", color: "#64748b", cursor: "pointer", padding: "0 2px", display: "flex", alignItems: "center" }}
          title="Tải lại"
        >
          <RefreshCw size={13} className={loading ? "spin" : undefined} />
        </button>
      </h3>

      {artifacts.length === 0 ? (
        <p style={{ fontSize: 12, color: "#475569", margin: 0 }}>Chưa có file xuất nào.</p>
      ) : (
        artifacts.map(a => <ArtifactItem key={a.path} artifact={a} threadId={threadId} />)
      )}
    </div>
  );
}

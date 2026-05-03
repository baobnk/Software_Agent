"use client";

import { useEffect, useState, useCallback } from "react";
import { FileText, Sheet, Download, RefreshCw, Package } from "lucide-react";
import { listOutputs, artifactDownloadUrl, type Artifact } from "@/lib/api";

interface Props {
  threadId: string;
  /** Increment to trigger a refresh */
  refreshKey?: number;
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  DOCX: <FileText size={16} className="text-blue-400" />,
  DOC:  <FileText size={16} className="text-blue-400" />,
  XLSX: <Sheet size={16} className="text-green-400" />,
  XLS:  <Sheet size={16} className="text-green-400" />,
  PDF:  <FileText size={16} className="text-red-400" />,
};

function fileIcon(type: string) {
  return TYPE_ICONS[type] ?? <Package size={16} className="text-gray-400" />;
}

export function ArtifactsPanel({ threadId, refreshKey }: Props) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listOutputs(threadId);
      setArtifacts(data.artifacts);
    } catch {
      // silently fail — panel is optional
    } finally {
      setLoading(false);
    }
  }, [threadId]);

  useEffect(() => {
    refresh();
  }, [refresh, refreshKey]);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
        <h2 className="text-sm font-semibold text-gray-200">Artifacts</h2>
        <button
          onClick={refresh}
          disabled={loading}
          className="p-1 rounded-lg hover:bg-[var(--surface-hover)] text-[var(--muted)]
                     hover:text-white transition-colors disabled:opacity-50"
          title="Làm mới"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {artifacts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-[var(--muted)]">
            <Package size={24} className="mb-2 opacity-40" />
            <p className="text-xs">Chưa có file xuất</p>
          </div>
        ) : (
          artifacts.map((a) => (
            <a
              key={a.path}
              href={artifactDownloadUrl(threadId, a.path)}
              download={a.name}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl
                         bg-[var(--surface)] border border-[var(--border)]
                         hover:border-[var(--accent)] hover:bg-[var(--surface-hover)]
                         transition-colors group"
            >
              <div className="flex-shrink-0">{fileIcon(a.type)}</div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-200 truncate font-medium">
                  {a.name}
                </p>
                <p className="text-xs text-[var(--muted)]">
                  {a.type} · {a.size_kb} KB
                </p>
              </div>
              <Download
                size={14}
                className="flex-shrink-0 text-[var(--muted)] group-hover:text-[var(--accent)]
                           transition-colors"
              />
            </a>
          ))
        )}
      </div>
    </div>
  );
}

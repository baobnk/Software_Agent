import { useRef, useState, DragEvent } from "react";
import { uploadFiles } from "../api";

interface Props {
  threadId: string;
}

interface UploadedFile {
  name: string;
  ok: boolean;
}

export function FileUpload({ threadId }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploaded, setUploaded] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    const list = Array.from(files);
    try {
      await uploadFiles(threadId, list);
      setUploaded((prev) => [
        ...prev,
        ...list.map((f) => ({ name: f.name, ok: true })),
      ]);
    } catch {
      setUploaded((prev) => [
        ...prev,
        ...list.map((f) => ({ name: f.name, ok: false })),
      ]);
    } finally {
      setUploading(false);
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  }

  return (
    <div className="sidebar-section">
      <h3>📁 Tải file yêu cầu</h3>

      <div
        className={`upload-zone${dragging ? " drag-over" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.txt,.md,.pptx,.xlsx,.png,.jpg,.jpeg"
          onChange={(e) => handleFiles(e.target.files)}
        />
        {uploading
          ? "⏳ Đang tải lên…"
          : "Kéo thả hoặc click để chọn file\n(PDF, DOCX, MD, PPTX, XLSX…)"}
      </div>

      {uploaded.map((f, i) => (
        <div key={i} className="uploaded-file">
          <span>{f.name}</span>
          <span className="uploaded-ok">{f.ok ? "✓" : "✗"}</span>
        </div>
      ))}
    </div>
  );
}

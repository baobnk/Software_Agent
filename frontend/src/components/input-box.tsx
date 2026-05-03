"use client";

import { useState, useRef, useCallback } from "react";
import { Send, Square, Paperclip, Loader2 } from "lucide-react";
import { uploadFiles } from "@/lib/api";

interface Props {
  threadId: string;
  isStreaming: boolean;
  onSend: (message: string) => void;
  onStop: () => void;
  disabled?: boolean;
}

export function InputBox({ threadId, isStreaming, onSend, onStop, disabled }: Props) {
  const [value, setValue] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = useCallback(() => {
    const msg = value.trim();
    if (!msg || isStreaming || disabled) return;
    setValue("");
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    onSend(msg);
  }, [value, isStreaming, disabled, onSend]);

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const onInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    // Auto-resize
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + "px";
  };

  const handleFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return;
    const files = Array.from(e.target.files);
    setUploading(true);
    try {
      const res = await uploadFiles(threadId, files);
      const names = files.map((f) => f.name).join(", ");
      onSend(`[Files đã upload: ${names}] Hãy đọc và phân tích các tài liệu vừa tải lên.`);
      console.log("Uploaded:", res.uploaded);
    } catch (err) {
      console.error("Upload error:", err);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="px-4 py-4 border-t border-[var(--border)] bg-[var(--background)]">
      <div className="flex items-end gap-2 bg-[var(--surface)] border border-[var(--border)]
                      rounded-2xl px-3 py-2 focus-within:border-[var(--accent)] transition-colors">
        {/* File upload button */}
        <button
          onClick={() => fileRef.current?.click()}
          disabled={isStreaming || uploading || disabled}
          className="flex-shrink-0 p-1.5 rounded-lg text-[var(--muted)] hover:text-white
                     hover:bg-[var(--surface-hover)] disabled:opacity-40 transition-colors"
          title="Upload file"
        >
          {uploading ? (
            <Loader2 size={18} className="animate-spin" />
          ) : (
            <Paperclip size={18} />
          )}
        </button>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.md,.pptx,.ppt,.png,.jpg,.jpeg"
          onChange={handleFiles}
          className="hidden"
        />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={onInput}
          onKeyDown={onKey}
          placeholder={
            disabled
              ? "Đang chờ xác nhận HITL..."
              : isStreaming
              ? "Đang xử lý..."
              : "Nhập tin nhắn... (Enter để gửi, Shift+Enter xuống dòng)"
          }
          disabled={isStreaming || disabled}
          rows={1}
          className="flex-1 bg-transparent text-sm text-white placeholder-[var(--muted)]
                     focus:outline-none resize-none min-h-[36px] max-h-[200px] py-1.5
                     disabled:cursor-not-allowed"
        />

        {/* Send / Stop button */}
        {isStreaming ? (
          <button
            onClick={onStop}
            className="flex-shrink-0 p-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white transition-colors"
            title="Dừng"
          >
            <Square size={16} className="fill-current" />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!value.trim() || disabled}
            className="flex-shrink-0 p-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)]
                       text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title="Gửi (Enter)"
          >
            <Send size={16} />
          </button>
        )}
      </div>

      <p className="text-center text-[10px] text-[var(--muted)] mt-2">
        BnK DeepAgent có thể mắc lỗi — hãy kiểm tra kỹ tài liệu được tạo ra.
      </p>
    </div>
  );
}

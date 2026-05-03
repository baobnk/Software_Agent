"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { createThread, uploadFiles } from "@/lib/api";
import { FileText, Upload, Plus, Loader2 } from "lucide-react";

export default function HomePage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [projectName, setProjectName] = useState("");
  const [language, setLanguage] = useState("vi");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setSelectedFiles(Array.from(e.target.files));
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setSelectedFiles(Array.from(e.dataTransfer.files));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectName.trim()) {
      setError("Vui lòng nhập tên dự án");
      return;
    }
    setLoading(true);
    setError("");

    try {
      const thread = await createThread({
        project_name: projectName.trim(),
        language,
      });

      if (selectedFiles.length > 0) {
        await uploadFiles(thread.thread_id, selectedFiles);
      }

      router.push(`/threads/${thread.thread_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi tạo thread");
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-[var(--accent)] mb-4">
            <FileText size={32} className="text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2">BnK DeepAgent</h1>
          <p className="text-[var(--muted)] text-sm">
            Tạo BRD + WBS tự động từ tài liệu yêu cầu
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Tên dự án
            </label>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="VD: Hệ thống quản lý nhà hàng"
              className="w-full px-4 py-3 rounded-xl bg-[var(--surface)] border border-[var(--border)]
                         text-white placeholder-[var(--muted)] focus:outline-none focus:border-[var(--accent)]
                         transition-colors"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Ngôn ngữ đầu ra
            </label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-[var(--surface)] border border-[var(--border)]
                         text-white focus:outline-none focus:border-[var(--accent)] transition-colors"
            >
              <option value="vi">Tiếng Việt</option>
              <option value="en">English</option>
              <option value="ja">日本語</option>
              <option value="zh">中文</option>
            </select>
          </div>

          {/* Drop zone */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Tài liệu yêu cầu (tùy chọn)
            </label>
            <div
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-[var(--border)] rounded-xl p-6 text-center
                         cursor-pointer hover:border-[var(--accent)] hover:bg-[var(--surface-hover)]
                         transition-colors group"
            >
              <Upload
                size={24}
                className="mx-auto mb-2 text-[var(--muted)] group-hover:text-[var(--accent)] transition-colors"
              />
              {selectedFiles.length > 0 ? (
                <div className="space-y-1">
                  {selectedFiles.map((f) => (
                    <p key={f.name} className="text-sm text-blue-400 font-mono">
                      {f.name}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="text-[var(--muted)] text-sm">
                  Kéo thả hoặc click để chọn file
                  <span className="block text-xs mt-1">PDF, DOCX, XLSX, TXT, MD, PPTX</span>
                </p>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.md,.pptx,.ppt,.png,.jpg,.jpeg"
              onChange={handleFiles}
              className="hidden"
            />
          </div>

          {error && (
            <p className="text-red-400 text-sm bg-red-900/20 px-4 py-2 rounded-lg border border-red-800">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl
                       bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white font-semibold
                       disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                Đang tạo thread...
              </>
            ) : (
              <>
                <Plus size={18} />
                Bắt đầu
              </>
            )}
          </button>
        </form>
      </div>
    </main>
  );
}

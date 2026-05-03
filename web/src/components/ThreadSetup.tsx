import { useState, FormEvent } from "react";
import { createThread } from "../api";

interface Props {
  onCreated: (threadId: string) => void;
}

export function ThreadSetup({ onCreated }: Props) {
  const [projectName, setProjectName] = useState("");
  const [language, setLanguage] = useState("vi");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!projectName.trim()) return;
    setLoading(true);
    setError("");
    try {
      const info = await createThread(projectName.trim(), language);
      onCreated(info.thread_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="setup-screen">
      <div className="setup-card">
        <h1>🤖 BnK DeepAgent</h1>
        <p>Hệ thống phân tích yêu cầu và tạo tài liệu BRD / WBS tự động</p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Tên dự án *</label>
            <input
              type="text"
              placeholder="Ví dụ: EC_Carpet, GEHP_System..."
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className="form-group">
            <label>Ngôn ngữ tài liệu</label>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="vi">🇻🇳 Tiếng Việt</option>
              <option value="en">🇬🇧 English</option>
              <option value="ja">🇯🇵 日本語</option>
            </select>
          </div>

          <button type="submit" className="btn-primary" disabled={loading || !projectName.trim()}>
            {loading ? "Đang tạo dự án…" : "Bắt đầu →"}
          </button>

          {error && <p className="error-msg">{error}</p>}
        </form>
      </div>
    </div>
  );
}

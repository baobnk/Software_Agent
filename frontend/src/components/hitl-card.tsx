"use client";

import { useState } from "react";
import {
  GitBranch, Check, X, MessageSquarePlus, Loader2,
  ChevronDown, ChevronRight, AlertCircle,
} from "lucide-react";
import type { HitlPayload } from "@/lib/use-thread-stream";

interface Props {
  hitl: HitlPayload;
  onResume: (decision: "approve" | "reject" | "edit", editedArgs?: Record<string, unknown>) => Promise<void>;
  onResolved: () => void;
}

// ── HITL checkpoint config ─────────────────────────────────────────────────────
// Defines which step each HITL tool represents and what info to show

const CHECKPOINT_META: Record<string, {
  step: string;
  stepLabel: string;
  nextStep: string;
  placeholder: string;
  examples: string[];
}> = {
  run_wbs_workflow: {
    step: "solution",
    stepLabel: "Thiết kế giải pháp xong",
    nextStep: "Phân rã WBS & ước lượng effort",
    placeholder: "VD: Thêm module quản lý kho vào scope, ưu tiên tính năng báo cáo, giới hạn 3 tháng POC...",
    examples: [
      "Thêm module thanh toán online vào phạm vi",
      "Ưu tiên tính năng xuất báo cáo Excel",
      "Giới hạn team 5 người, timeline 4 tháng",
    ],
  },
  run_brd_workflow: {
    step: "wbs",
    stepLabel: "WBS đã hoàn thành",
    nextStep: "Soạn thảo tài liệu BRD",
    placeholder: "VD: Thêm yêu cầu bảo mật 2FA, điều chỉnh SLA response time, bổ sung tích hợp với hệ thống X...",
    examples: [
      "Bổ sung yêu cầu xác thực 2 lớp (2FA)",
      "SLA: API response < 500ms cho 95% request",
      "Tích hợp với hệ thống ERP hiện tại",
    ],
  },
  render_brd: {
    step: "brd",
    stepLabel: "BRD đã pass validation",
    nextStep: "Xuất file Word (.docx)",
    placeholder: "Ghi chú thêm nếu cần (để trống nếu OK)...",
    examples: [],
  },
  render_wbs: {
    step: "wbs",
    stepLabel: "WBS đã pass validation",
    nextStep: "Xuất file Excel (.xlsx)",
    placeholder: "Ghi chú thêm nếu cần (để trống nếu OK)...",
    examples: [],
  },
};

const PIPELINE_STEPS = ["intake", "solution", "wbs", "brd", "export"];
const STEP_LABELS: Record<string, string> = {
  intake: "Phân tích", solution: "Giải pháp", wbs: "WBS", brd: "BRD", export: "Xuất file",
};

// ── Mini pipeline indicator ────────────────────────────────────────────────────

function MiniPipeline({ currentStep }: { currentStep: string }) {
  const idx = PIPELINE_STEPS.indexOf(currentStep);
  return (
    <div className="flex items-center gap-1">
      {PIPELINE_STEPS.map((s, i) => {
        const done = i <= idx;
        const active = i === idx + 1;
        return (
          <div key={s} className="flex items-center gap-1">
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
              done   ? "text-green-400 bg-green-900/30" :
              active ? "text-purple-300 bg-purple-900/30 border border-purple-700/50" :
                       "text-gray-600"
            }`}>
              {STEP_LABELS[s]}
            </span>
            {i < PIPELINE_STEPS.length - 1 && (
              <ChevronRight size={10} className={done ? "text-green-700" : "text-gray-700"} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Main HITL card ─────────────────────────────────────────────────────────────

export function HitlCard({ hitl, onResume, onResolved }: Props) {
  const [feedback, setFeedback] = useState("");
  const [loading, setLoading] = useState<string | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [error, setError] = useState("");

  const meta = CHECKPOINT_META[hitl.tool];
  const hasFeedback = feedback.trim().length > 0;

  const handle = async (decision: "approve" | "reject" | "edit") => {
    setLoading(decision);
    setError("");
    try {
      const editedArgs = hasFeedback && (decision === "approve" || decision === "edit")
        ? { feedback: feedback.trim() }
        : undefined;
      const actualDecision = hasFeedback && decision === "approve" ? "edit" : decision;
      await onResume(actualDecision, editedArgs);
      onResolved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi resume");
      setLoading(null);
    }
  };

  return (
    <div className="mx-4 my-3 rounded-2xl border border-purple-700/60 bg-[var(--hitl-bg)] overflow-hidden shadow-lg shadow-purple-900/20">

      {/* ── Header ── */}
      <div className="px-4 pt-4 pb-3 border-b border-purple-800/30">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-7 h-7 rounded-lg bg-purple-600/25 border border-purple-600/30 flex items-center justify-center flex-shrink-0">
            <GitBranch size={14} className="text-purple-400" />
          </div>
          <div>
            <p className="text-xs font-semibold text-purple-300 uppercase tracking-wider leading-none">
              Điểm kiểm tra — cần xác nhận
            </p>
            {meta && (
              <p className="text-[11px] text-gray-500 mt-0.5">{meta.stepLabel}</p>
            )}
          </div>
        </div>

        {/* Pipeline progress */}
        {meta && <MiniPipeline currentStep={meta.step} />}
      </div>

      {/* ── Agent message ── */}
      <div className="px-4 py-3">
        <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-line">
          {hitl.question}
        </p>

        {/* Next step hint */}
        {meta && (
          <div className="mt-2 flex items-center gap-1.5 text-xs text-gray-500">
            <ChevronRight size={12} className="text-purple-600" />
            <span>Bước tiếp theo: <span className="text-purple-300">{meta.nextStep}</span></span>
          </div>
        )}
      </div>

      {/* ── User feedback textarea ── */}
      <div className="px-4 pb-3">
        <label className="block text-xs font-medium text-gray-400 mb-1.5">
          Góp ý / điều chỉnh trước khi tiếp tục
          <span className="text-gray-600 font-normal ml-1">(tùy chọn)</span>
        </label>
        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder={meta?.placeholder ?? "Nhập góp ý hoặc điều chỉnh..."}
          rows={3}
          className="w-full px-3 py-2.5 rounded-xl bg-gray-900/60 border border-gray-700/60
                     text-sm text-gray-200 placeholder-gray-600
                     focus:outline-none focus:border-purple-600/60
                     resize-none transition-colors"
        />

        {/* Example chips */}
        {meta?.examples && meta.examples.length > 0 && !feedback && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {meta.examples.map((ex) => (
              <button
                key={ex}
                onClick={() => setFeedback(ex)}
                className="text-[11px] text-gray-500 hover:text-gray-300 bg-gray-800/60 hover:bg-gray-800
                           border border-gray-700/50 px-2 py-1 rounded-lg transition-colors"
              >
                + {ex}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Detail toggle (raw args) ── */}
      {Object.keys(hitl.args).length > 0 && (
        <div className="px-4 pb-3">
          <button
            onClick={() => setShowDetail(!showDetail)}
            className="flex items-center gap-1 text-[11px] text-gray-700 hover:text-gray-500 transition-colors"
          >
            <ChevronDown size={12} className={`transition-transform ${showDetail ? "rotate-180" : ""}`} />
            Xem tham số kỹ thuật
          </button>
          {showDetail && (
            <pre className="mt-2 font-mono text-[11px] bg-gray-950 text-gray-500 rounded-lg p-3 overflow-x-auto max-h-32">
              {JSON.stringify(hitl.args, null, 2)}
            </pre>
          )}
        </div>
      )}

      {/* ── Error ── */}
      {error && (
        <div className="px-4 pb-3">
          <div className="flex items-center gap-2 text-xs text-red-400 bg-red-900/20 border border-red-800/50 px-3 py-2 rounded-lg">
            <AlertCircle size={13} />
            {error}
          </div>
        </div>
      )}

      {/* ── Actions ── */}
      <div className="flex items-center gap-2 px-4 py-3 bg-black/30 border-t border-purple-900/30">
        {hasFeedback ? (
          /* Has feedback → primary is "Tiếp tục kèm ghi chú" */
          <>
            <button
              onClick={() => handle("approve")}
              disabled={!!loading}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500
                         text-white text-sm font-medium disabled:opacity-50 transition-colors flex-1 justify-center"
            >
              {loading === "approve"
                ? <Loader2 size={14} className="animate-spin" />
                : <MessageSquarePlus size={14} />}
              Tiếp tục kèm ghi chú
            </button>
            <button
              onClick={() => handle("reject")}
              disabled={!!loading}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-gray-800 hover:bg-gray-700
                         text-gray-300 text-sm disabled:opacity-50 transition-colors"
            >
              {loading === "reject" ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />}
              Làm lại
            </button>
          </>
        ) : (
          /* No feedback → primary is "Tiếp tục" */
          <>
            <button
              onClick={() => handle("approve")}
              disabled={!!loading}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-green-600 hover:bg-green-500
                         text-white text-sm font-medium disabled:opacity-50 transition-colors flex-1 justify-center"
            >
              {loading === "approve"
                ? <Loader2 size={14} className="animate-spin" />
                : <Check size={14} />}
              Tiếp tục
            </button>
            <button
              onClick={() => handle("reject")}
              disabled={!!loading}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-gray-800 hover:bg-gray-700
                         text-gray-300 text-sm disabled:opacity-50 transition-colors"
            >
              {loading === "reject" ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />}
              Làm lại
            </button>
          </>
        )}
      </div>
    </div>
  );
}

import { useLangGraphInterrupt } from "@copilotkit/react-core";
import { useState } from "react";
import {
  BarChart3, FileText, Cpu, CheckCircle2, XCircle,
  ChevronRight, AlertTriangle, Zap,
} from "lucide-react";

interface ToolConfig {
  label: string;
  description: string;
  icon: React.ReactNode;
  color: string;
  duration: string;
}

const TOOL_CONFIG: Record<string, ToolConfig> = {
  confirm_diagram_generation: {
    label: "Tạo sơ đồ kiến trúc",
    description: "Tạo 3 sơ đồ kiến trúc từ technical_design.md: System Architecture (C4 L1), Component Diagram (C4 L2), Deployment Diagram.",
    icon: <Cpu size={20} />,
    color: "#f59e0b",
    duration: "~30–60s",
  },
  confirm_delivery_milestones: {
    label: "Xác nhận milestones",
    description: "Xem xét và xác nhận kế hoạch giao hàng với các mốc thời gian đề xuất dựa trên effort WBS.",
    icon: <BarChart3 size={20} />,
    color: "#a78bfa",
    duration: "~2s",
  },
  run_wbs_workflow: {
    label: "Chạy WBS Workflow",
    description: "Phân rã yêu cầu thành các task, ước lượng effort cho từng task và tạo cấu trúc WBS hoàn chỉnh.",
    icon: <BarChart3 size={20} />,
    color: "#34d399",
    duration: "~30–60s",
  },
  run_brd_workflow: {
    label: "Chạy BRD Workflow",
    description: "Soạn thảo tài liệu Business Requirements Document theo chuẩn BnK, bao gồm tất cả các section.",
    icon: <FileText size={20} />,
    color: "#60a5fa",
    duration: "~60–120s",
  },
  render_wbs: {
    label: "Xuất WBS Excel",
    description: "Render file WBS ra định dạng Excel (.xlsx) theo template chuẩn của BnK.",
    icon: <Zap size={20} />,
    color: "#34d399",
    duration: "~5–10s",
  },
  render_brd: {
    label: "Xuất BRD Word",
    description: "Render tài liệu BRD ra định dạng Word (.docx) theo template chuẩn của BnK.",
    icon: <Zap size={20} />,
    color: "#60a5fa",
    duration: "~5–10s",
  },
  save_technical_design_md: {
    label: "Lưu Technical Design",
    description: "Lưu tài liệu thiết kế kỹ thuật vào workspace.",
    icon: <Cpu size={20} />,
    color: "#a78bfa",
    duration: "~2s",
  },
};

function HITLCard({
  event,
  resolve,
}: {
  event: { value?: { action_requests?: { name?: string }[] } };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  resolve: (value: any) => void;
}) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ev = event.value as any;
  const toolName: string =
    ev?.action_requests?.[0]?.name ??   // DeepAgents HITLRequest format
    ev?.tool ??                          // langgraph.types.interrupt({"tool": "..."}) format
    (typeof ev === "string" ? ev : undefined) ??
    "unknown";

  // Use the interrupt's own message if no config entry is found
  const fallbackDesc: string =
    ev?.message ?? ev?.description ?? `Agent muốn thực hiện bước: "${toolName}".`;

  const cfg = TOOL_CONFIG[toolName] ?? {
    label: toolName,
    description: fallbackDesc,
    icon: <Cpu size={20} />,
    color: "#f59e0b",
    duration: "",
  };

  const [feedback, setFeedback] = useState("");
  const [state, setState] = useState<"idle" | "approving" | "rejecting">("idle");

  function approve() {
    setState("approving");
    resolve({ decisions: [{ type: "approve", message: feedback || undefined }] });
  }

  function reject() {
    setState("rejecting");
    resolve({ decisions: [{ type: "reject", message: feedback || "User rejected" }] });
  }

  return (
    <div className="hitl-v2-card" style={{ "--hitl-color": cfg.color } as React.CSSProperties}>
      {/* Top bar */}
      <div className="hitl-v2-topbar">
        <div className="hitl-v2-icon" style={{ background: `${cfg.color}18`, color: cfg.color }}>
          {cfg.icon}
        </div>
        <div className="hitl-v2-meta">
          <div className="hitl-v2-badge">
            <AlertTriangle size={10} />
            <span>Cần xác nhận</span>
          </div>
          <div className="hitl-v2-title">{cfg.label}</div>
        </div>
        {cfg.duration && (
          <div className="hitl-v2-duration">
            <span>⏱</span>
            <span>{cfg.duration}</span>
          </div>
        )}
      </div>

      {/* Description */}
      <p className="hitl-v2-desc">{cfg.description}</p>

      {/* Optional feedback */}
      <textarea
        className="hitl-v2-feedback"
        placeholder="Ghi chú thêm cho agent (tuỳ chọn)…"
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        rows={2}
      />

      {/* Actions */}
      <div className="hitl-v2-actions">
        <button
          className="hitl-v2-btn-approve"
          onClick={approve}
          disabled={state !== "idle"}
          style={{ background: cfg.color }}
        >
          {state === "approving" ? (
            <span className="hitl-btn-loading">Đang xử lý…</span>
          ) : (
            <>
              <CheckCircle2 size={14} />
              <span>Xác nhận</span>
              <ChevronRight size={12} />
            </>
          )}
        </button>
        <button
          className="hitl-v2-btn-reject"
          onClick={reject}
          disabled={state !== "idle"}
        >
          {state === "rejecting" ? (
            <span className="hitl-btn-loading">Từ chối…</span>
          ) : (
            <>
              <XCircle size={14} />
              <span>Từ chối</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

export function HITLApproval() {
  useLangGraphInterrupt({
    render: ({ event, resolve }) => (
      <HITLCard
        event={event as Parameters<typeof HITLCard>[0]["event"]}
        resolve={resolve}
      />
    ),
  });
  return null;
}

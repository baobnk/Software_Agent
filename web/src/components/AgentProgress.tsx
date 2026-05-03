import { useCoAgent } from "@copilotkit/react-core";
import { CheckCircle2, Loader2, ChevronDown, ChevronRight, Cpu, BarChart3, FileText, Search, File, Zap, Settings } from "lucide-react";
import { useState } from "react";

const TOOL_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  list_input_files:         { label: "Liệt kê file đầu vào",     icon: <Search size={12} />,    color: "#60a5fa" },
  read_file:                { label: "Đọc file yêu cầu",         icon: <File size={12} />,      color: "#60a5fa" },
  read_txt:                 { label: "Đọc nội dung file",         icon: <File size={12} />,      color: "#60a5fa" },
  write_todos:              { label: "Cập nhật kế hoạch",         icon: <Settings size={12} />,  color: "#94a3b8" },
  ls:                       { label: "Kiểm tra thư mục",          icon: <Settings size={12} />,  color: "#94a3b8" },
  save_raw_features:        { label: "Lưu đặc tả tính năng",     icon: <FileText size={12} />,  color: "#a78bfa" },
  save_technical_design_md:            { label: "Lưu thiết kế kỹ thuật",    icon: <Cpu size={12} />,       color: "#a78bfa" },
  generate_technical_design_diagram:   { label: "Tạo sơ đồ kiến trúc",      icon: <Cpu size={12} />,       color: "#f59e0b" },
  export_diagram_png:                  { label: "Xuất sơ đồ PNG",            icon: <Cpu size={12} />,       color: "#f59e0b" },
  confirm_diagram_generation:          { label: "Xác nhận tạo sơ đồ",       icon: <Cpu size={12} />,       color: "#f59e0b" },
  patch_solution_section:              { label: "Cập nhật solution",         icon: <Cpu size={12} />,       color: "#a78bfa" },
  run_wbs_workflow:         { label: "Chạy WBS Workflow",         icon: <BarChart3 size={12} />, color: "#34d399" },
  init_wbs:                 { label: "Khởi tạo WBS",              icon: <BarChart3 size={12} />, color: "#34d399" },
  decompose_wbs:            { label: "Phân rã công việc",         icon: <BarChart3 size={12} />, color: "#34d399" },
  estimate_wbs:             { label: "Ước lượng effort",          icon: <BarChart3 size={12} />, color: "#34d399" },
  validate_wbs:             { label: "Kiểm tra WBS",              icon: <CheckCircle2 size={12} />, color: "#34d399" },
  render_wbs:               { label: "Xuất WBS Excel",            icon: <Zap size={12} />,       color: "#f472b6" },
  run_brd_workflow:         { label: "Chạy BRD Workflow",         icon: <FileText size={12} />,  color: "#fb923c" },
  init_brd:                 { label: "Khởi tạo BRD",              icon: <FileText size={12} />,  color: "#fb923c" },
  validate_brd:             { label: "Kiểm tra BRD",              icon: <CheckCircle2 size={12} />, color: "#fb923c" },
  render_brd:               { label: "Xuất BRD Word",             icon: <Zap size={12} />,       color: "#f472b6" },
};

function getMeta(name: string) {
  return TOOL_META[name] ?? { label: name, icon: <Cpu size={12} />, color: "#64748b" };
}

interface AgentState {
  completed_steps?: string[];
  status?: string;
  active_tool?: string;
}

export function AgentProgress() {
  const { running, state } = useCoAgent<AgentState>({
    name: "bnk_main_agent",
    initialState: {},
  });

  const typedState = state as AgentState;
  const steps: string[] = typedState?.completed_steps ?? [];
  const activeTool: string | undefined = typedState?.active_tool;
  const [expanded, setExpanded] = useState(true);

  // Hide when idle and no steps
  if (!running && steps.length === 0) return null;

  // Determine what to show in the header
  const displayActiveTool = running
    ? activeTool && !steps.includes(activeTool)
      ? activeTool
      : steps[steps.length - 1] ?? null
    : null;
  const headerMeta = displayActiveTool ? getMeta(displayActiveTool) : null;

  // Build the full step list: completed steps + optional active tool as last item
  const showActiveInList = running && activeTool && !steps.includes(activeTool);

  return (
    <div className="agent-status-widget">
      {/* Header row — click to expand/collapse */}
      <button className="agent-status-header" onClick={() => setExpanded(!expanded)}>
        <span className="agent-status-icon">
          {running ? (
            <Loader2 size={13} className="spin" style={{ color: "#2563eb" }} />
          ) : (
            <CheckCircle2 size={13} style={{ color: "#34d399" }} />
          )}
        </span>
        <span className="agent-status-label">
          {running
            ? headerMeta
              ? headerMeta.label
              : "Agent đang khởi động…"
            : `Hoàn tất — ${steps.length} bước`}
        </span>
        {(steps.length > 0 || showActiveInList) && (
          expanded
            ? <ChevronDown size={12} style={{ color: "#475569" }} />
            : <ChevronRight size={12} style={{ color: "#475569" }} />
        )}
      </button>

      {/* Step timeline — collapsible */}
      {expanded && (steps.length > 0 || showActiveInList) && (
        <div className="agent-status-steps">
          {steps.map((step, i) => {
            const m = getMeta(step);
            const isLastCompleted = i === steps.length - 1 && !showActiveInList;
            const isSpinning = isLastCompleted && running;
            return (
              <div key={i} className={`agent-status-step ${isSpinning ? "step-active" : "step-done"}`}>
                <span className="step-dot" style={{ background: isSpinning ? m.color : "#1e293b", borderColor: m.color }}>
                  {isSpinning ? (
                    <Loader2 size={8} className="spin" style={{ color: m.color }} />
                  ) : (
                    <span style={{ width: 4, height: 4, borderRadius: "50%", background: m.color, display: "block" }} />
                  )}
                </span>
                <span className="step-icon" style={{ color: m.color }}>{m.icon}</span>
                <span className="step-label" style={{ color: isSpinning ? "#e2e8f0" : "#64748b" }}>{m.label}</span>
              </div>
            );
          })}

          {/* Active tool not yet completed — shown as spinning current step */}
          {showActiveInList && activeTool && (() => {
            const m = getMeta(activeTool);
            return (
              <div className="agent-status-step step-active">
                <span className="step-dot" style={{ background: m.color, borderColor: m.color }}>
                  <Loader2 size={8} className="spin" style={{ color: "#fff" }} />
                </span>
                <span className="step-icon" style={{ color: m.color }}>{m.icon}</span>
                <span className="step-label" style={{ color: "#e2e8f0" }}>{m.label}</span>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

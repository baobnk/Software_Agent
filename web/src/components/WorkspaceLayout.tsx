import { CopilotChat } from "@copilotkit/react-ui";
import { FileUpload } from "./FileUpload";
import { HITLApproval } from "./HITLApproval";
import { ChatArtifacts } from "./ChatArtifacts";
import { AgentProgress } from "./AgentProgress";

interface Props {
  threadId: string;
}

export function WorkspaceLayout({ threadId }: Props) {
  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      {/* Left sidebar — file upload only */}
      <aside className="sidebar">
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9" }}>
            🤖 BnK DeepAgent
          </div>
          <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>
            thread: {threadId.slice(0, 8)}…
          </div>
        </div>

        <FileUpload threadId={threadId} />

        <AgentProgress />
      </aside>

      {/* Main chat area */}
      <main
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minWidth: 0,
          height: "100vh",
        }}
      >
        {/* HITL approval card rendered inside chat via useLangGraphInterrupt */}
        <HITLApproval />

        {/* Agent progress + rendered file cards rendered inside chat via useCoAgentStateRender */}
        <ChatArtifacts threadId={threadId} />

        <div style={{ flex: 1, height: "100%", minHeight: 0 }}>
          <CopilotChat
            instructions={[
              "Bạn là BnK DeepAgent — hệ thống phân tích yêu cầu và tạo tài liệu BRD / WBS chuyên nghiệp.",
              "Ngôn ngữ mặc định: tiếng Việt.",
              "Workflow: đọc file /input/ → phân tích → run_wbs_workflow → run_brd_workflow.",
            ].join("\n")}
            labels={{
              initial: "Xin chào! Hãy upload file yêu cầu (sidebar trái) rồi nhắn tin để bắt đầu.",
              placeholder: "Nhắn tin cho agent…",
            }}
            className="flex-1"
          />
        </div>
      </main>
    </div>
  );
}

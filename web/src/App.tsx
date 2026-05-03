import { CopilotKit } from "@copilotkit/react-core";
import "@copilotkit/react-ui/styles.css";
import { useState } from "react";
import { ThreadSetup } from "./components/ThreadSetup";
import { WorkspaceLayout } from "./components/WorkspaceLayout";

export default function App() {
  const [threadId, setThreadId] = useState<string | null>(null);

  if (!threadId) {
    return <ThreadSetup onCreated={setThreadId} />;
  }

  return (
    <CopilotKit
      runtimeUrl="/copilotkit"
      threadId={threadId}
      agent="bnk_main_agent"
    >
      <WorkspaceLayout threadId={threadId} />
    </CopilotKit>
  );
}

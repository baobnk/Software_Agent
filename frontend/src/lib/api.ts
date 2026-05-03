/**
 * API client for BnK DeepAgent backend (/api/threads endpoints).
 * Mirrors deer-flow RunRecord / ThreadStatus patterns.
 */

const BASE = "/api";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Thread {
  thread_id: string;
  project_name: string;
  input_dir: string;
  output_dir: string;
  workspace_dir: string;
  created_at: string;
}

export type ThreadStatus = "idle" | "busy" | "interrupted" | "error";

export interface RunRecord {
  run_id: string;
  thread_id: string;
  status: "pending" | "running" | "succeeded" | "failed" | "interrupted";
  multitask_strategy: string;
  on_disconnect: string;
  created_at: string;
  updated_at: string;
  error: string | null;
}

export interface ThreadDetail {
  thread_id: string;
  project_name: string;
  language: string;
  status: ThreadStatus;
  current_run: RunRecord | null;
  brd_index: Record<string, unknown> | null;
  wbs_index: Record<string, unknown> | null;
  issues: unknown[];
  has_technical_design: boolean;
  created_at: string;
}

export interface Artifact {
  path: string;
  name: string;
  type: string;
  size_kb: number;
}

// ── Thread CRUD ───────────────────────────────────────────────────────────────

export async function createThread(params: {
  project_name: string;
  input_dir?: string;
  output_dir?: string;
  model?: string;
  language?: string;
}): Promise<Thread> {
  const res = await fetch(`${BASE}/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getThread(threadId: string): Promise<ThreadDetail> {
  const res = await fetch(`${BASE}/threads/${threadId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteThread(threadId: string) {
  const res = await fetch(`${BASE}/threads/${threadId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── File uploads ──────────────────────────────────────────────────────────────

export async function uploadFiles(threadId: string, files: File[]) {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const res = await fetch(`${BASE}/threads/${threadId}/uploads`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Run management ────────────────────────────────────────────────────────────

export async function listRuns(threadId: string): Promise<{ runs: RunRecord[] }> {
  const res = await fetch(`${BASE}/threads/${threadId}/runs`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cancelRun(
  threadId: string,
  runId: string,
  action: "interrupt" | "rollback" = "interrupt"
) {
  const res = await fetch(
    `${BASE}/threads/${threadId}/runs/${runId}?action=${action}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── HITL resume ───────────────────────────────────────────────────────────────

export async function resumeRun(
  threadId: string,
  decision: "approve" | "reject" | "edit",
  editedArgs?: Record<string, unknown>
) {
  const res = await fetch(`${BASE}/threads/${threadId}/runs/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, edited_args: editedArgs }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Artifacts ─────────────────────────────────────────────────────────────────

export async function listOutputs(
  threadId: string
): Promise<{ artifacts: Artifact[] }> {
  const res = await fetch(`${BASE}/threads/${threadId}/outputs`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function artifactDownloadUrl(threadId: string, artifactPath: string) {
  return `${BASE}/threads/${threadId}/artifacts/${artifactPath}`;
}

// ── Models ────────────────────────────────────────────────────────────────────

export async function listModels(): Promise<{ models: Record<string, string> }> {
  const res = await fetch(`${BASE}/models`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

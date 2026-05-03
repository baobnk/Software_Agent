const BASE = "/api";

export interface ThreadInfo {
  thread_id: string;
  project_name: string;
  input_dir: string;
  output_dir: string;
}

export interface Artifact {
  name: string;
  path: string;
  type: string;
  size_kb: number;
}

/** File rendered by agent (from StateSnapshotEvent rendered_files array) */
export interface RenderedFile {
  name: string;
  path: string;
  type: string;
  source: "artifact" | "workspace";
}

export async function createThread(
  projectName: string,
  language: string,
  model?: string,
): Promise<ThreadInfo> {
  const body: Record<string, string> = { project_name: projectName, language };
  if (model) body.model = model;
  const r = await fetch(`${BASE}/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`Create thread failed: ${await r.text()}`);
  return r.json();
}

export async function uploadFiles(
  threadId: string,
  files: File[],
): Promise<{ uploaded: string[] }> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const r = await fetch(`${BASE}/threads/${threadId}/uploads`, {
    method: "POST",
    body: form,
  });
  if (!r.ok) throw new Error(`Upload failed: ${await r.text()}`);
  return r.json();
}

export async function listOutputs(threadId: string): Promise<Artifact[]> {
  const r = await fetch(`${BASE}/threads/${threadId}/outputs`);
  if (!r.ok) throw new Error(`List outputs failed: ${await r.text()}`);
  const data = await r.json();
  return data.artifacts ?? data.files ?? [];
}

// Each path segment is encoded individually so slashes are preserved as separators.
function encodePath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

export function artifactDownloadUrl(threadId: string, path: string): string {
  return `${BASE}/threads/${threadId}/artifacts/${encodePath(path)}`;
}

// Programmatic download via Blob — bypasses <a download> cross-origin limitations
// and works for filenames with Unicode / spaces.
export async function downloadArtifact(threadId: string, artifact: Artifact): Promise<void> {
  const url = artifactDownloadUrl(threadId, artifact.path);
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Download failed: HTTP ${resp.status}`);
  const blob = await resp.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = artifact.name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}

export function workspaceFileUrl(threadId: string, filePath: string): string {
  return `${BASE}/threads/${threadId}/workspace/${encodePath(filePath)}`;
}

export async function downloadWorkspaceFile(
  threadId: string,
  file: { name: string; path: string },
): Promise<void> {
  const url = workspaceFileUrl(threadId, file.path);
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Download failed: HTTP ${resp.status}`);
  const blob = await resp.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = file.name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}

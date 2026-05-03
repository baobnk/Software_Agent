"""Output folder control tools.

The user controls WHERE files are saved via the OUTPUT_DIR env var (or by
passing output_dir at agent invocation). These tools create the folder
structure and report final artifact locations.

Output convention:
  {OUTPUT_DIR}/{project_name}/
  ├── BRD/
  │   └── {project_name}_BRD_v{version}.docx
  └── WBS/
      └── {project_name}_WBS_v{version}.xlsx
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from langchain_core.tools import tool


def _get_output_root() -> Path:
    root = os.environ.get("OUTPUT_DIR", "/tmp/bnk-outputs")
    return Path(root)


def _project_root(base: Path, safe_name: str) -> Path:
    """Return project output folder, guarding against double-nesting."""
    if base.name == safe_name:
        return base
    return base / safe_name


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def create_project_folder(
    project_name: str,
    output_dir: str = "",
) -> str:
    """Create the output folder structure for a project.

    output_dir: override OUTPUT_DIR env var. Leave empty to use env default.
    Returns the created folder paths.
    """
    root = Path(output_dir) if output_dir else _get_output_root()
    project_root = _project_root(root, project_name.replace(" ", "_"))
    brd_dir = project_root / "BRD"
    wbs_dir = project_root / "WBS"
    brd_dir.mkdir(parents=True, exist_ok=True)
    wbs_dir.mkdir(parents=True, exist_ok=True)
    return (
        f"Folders created:\n"
        f"  BRD: {brd_dir}\n"
        f"  WBS: {wbs_dir}"
    )


@tool
def get_output_paths(
    project_name: str,
    version: str = "0.1.0",
    output_dir: str = "",
) -> str:
    """Return the full output file paths for BRD and WBS artifacts.

    Call this to know where render_brd and render_wbs should write.
    """
    root = Path(output_dir) if output_dir else _get_output_root()
    safe_name = project_name.replace(" ", "_")
    v = version.replace(".", "_")
    proj = _project_root(root, safe_name)
    brd_path = proj / "BRD" / f"{safe_name}_BRD_v{v}.docx"
    wbs_path = proj / "WBS" / f"{safe_name}_WBS_v{v}.xlsx"
    return f"BRD_PATH={brd_path}\nWBS_PATH={wbs_path}"


@tool
def list_project_outputs(project_name: str, output_dir: str = "") -> str:
    """List all generated artifacts for a project."""
    root = Path(output_dir) if output_dir else _get_output_root()
    project_root = _project_root(root, project_name.replace(" ", "_"))
    if not project_root.exists():
        return f"No output folder found for '{project_name}' in {root}"
    lines = [f"Artifacts for '{project_name}' ({project_root}):"]
    for p in sorted(project_root.rglob("*")):
        if p.is_file():
            kb = p.stat().st_size // 1024
            lines.append(f"  {p.relative_to(project_root)}  ({kb} KB)")
    return "\n".join(lines) if len(lines) > 1 else "No artifacts yet."


@tool
def set_output_dir(output_dir: str) -> str:
    """Override the OUTPUT_DIR for this session.

    This updates the env var so all subsequent folder_manager calls use it.
    """
    os.environ["OUTPUT_DIR"] = output_dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    return f"Output directory set to: {output_dir}"


@tool
def upload_to_s3(local_path: str, s3_key: str = "") -> str:
    """Upload a rendered artifact to S3/MinIO and return a presigned URL.

    Requires S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY env vars.
    Set ENABLE_S3_UPLOAD=false to skip (returns local path instead).
    """
    if os.environ.get("ENABLE_S3_UPLOAD", "false").lower() == "false":
        return f"S3 upload disabled. File is at: {local_path}"

    try:
        import boto3
        from botocore.exceptions import ClientError

        p = Path(local_path)
        if not p.exists():
            return f"ERROR: file not found: {local_path}"

        key = s3_key or f"artifacts/{p.name}"
        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
            region_name=os.environ.get("S3_REGION", "us-east-1"),
        )
        bucket = os.environ.get("S3_BUCKET", "bnk-artifacts")
        s3.upload_file(str(p), bucket, key)
        ttl = int(os.environ.get("S3_URL_TTL", "3600"))
        url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=ttl
        )
        return f"Uploaded to S3: {url}"
    except Exception as e:
        return f"S3 upload error: {e}"

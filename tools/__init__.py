"""Tools package — all @tool functions for BnK DeepAgent."""
from .file_reader import (
    list_input_files,
    read_pdf_smart,
    read_docx, read_txt, read_pptx, read_xlsx,
    describe_image, write_raw_features,
)
from .brd_ops import (
    init_brd, set_brd_text, add_brd_list_item,
    upsert_brd_row, upsert_fr, get_brd_summary,
)
from .wbs_ops import init_wbs, set_master_data, upsert_task, get_wbs_summary
from .validators import validate_brd, validate_wbs, validate_traceability, get_issues
from .renderer import render_brd, render_wbs
from .solution_ops import (
    get_raw_features, patch_solution_section, get_solution_draft,
    apply_user_input, save_technical_design_md,
    get_technical_design,
)
from .folder_manager import (
    create_project_folder, get_output_paths,
    list_project_outputs, set_output_dir, upload_to_s3,
)
from .plan_exporter import export_implementation_plan, get_plan_preview
from .memory import (
    save_user_preference, recall_user_preferences,
    save_project_decision, recall_project_decisions,
)
from .excel_audit import audit_workbook
from .excel_patch import patch_workbook
from .delivery_ops import compute_delivery_plan, confirm_delivery_milestones
from .diagram_image_gen import generate_solution_diagram_image
from .drawio_diagram_gen import generate_technical_design_diagram, export_diagram_png

ALL_TOOLS = [
    # File reading
    list_input_files, read_pdf_smart,
    read_docx, read_txt, read_pptx, read_xlsx,
    describe_image, write_raw_features,
    # BRD ops (6 tools — packages.brd.operations is the source of truth)
    init_brd, set_brd_text, add_brd_list_item,
    upsert_brd_row, upsert_fr, get_brd_summary,
    # WBS ops
    init_wbs, set_master_data, upsert_task, get_wbs_summary,
    # Validators
    validate_brd, validate_wbs, validate_traceability, get_issues,
    # Rendering
    render_brd, render_wbs,
    # Solution ops
    get_raw_features, patch_solution_section, get_solution_draft,
    apply_user_input, save_technical_design_md,
    get_technical_design,
    # Folder management
    create_project_folder, get_output_paths,
    list_project_outputs, set_output_dir, upload_to_s3,
    # Plan exporter
    export_implementation_plan, get_plan_preview,
    # Long-term memory (Tier 3 — LangGraph Store)
    save_user_preference, recall_user_preferences,
    save_project_decision, recall_project_decisions,
    # Excel audit + patch (smart dispatch — see skills/excel_workbook)
    audit_workbook, patch_workbook,
    # Delivery planning + HITL milestones (see skills/delivery_planning)
    compute_delivery_plan, confirm_delivery_milestones,
    # Diagram image generation (OpenRouter Gemini, HITL confirm before API call)
    generate_solution_diagram_image,
    # Draw.io diagram generation (mxGraph XML via gpt-5.4-mini, HITL confirm)
    generate_technical_design_diagram,
    export_diagram_png,
]

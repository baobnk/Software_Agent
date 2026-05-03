# Review Notes — LangChain multi-agent docs + Paper2Any architecture

> Reference: https://docs.langchain.com/oss/python/langchain/multi-agent
> Reference codebase: /mnt/f/code/agent/WBS_Agent/Paper2Any/

## TL;DR

Giữ DeepAgents framework, nhưng **bổ sung 4 patterns từ Paper2Any cho production-grade**:
1. State inheritance (MainState → BRDState/WBSState/ProposalState)
2. Workflow decorator registry (3 workflows độc lập, không 1 monolithic orchestrator)
3. Subprocess pool cho heavy rendering (openpyxl/docxtpl không thread-safe)
4. Lazy LLM client — API key per session, không env hardcoded

---

## 1. LangChain — 5 multi-agent patterns

| Pattern | Khi dùng | API |
|---------|---------|-----|
| **Subagents** | Multi-domain, parallel | `create_agent` + `@tool` wrapping subagent |
| **Handoffs** | Sequential multi-hop | `Command(goto=, graph=Command.PARENT)` + `ToolMessage` |
| **Skills** | Single agent + dynamic context | `skills=[...]` |
| **Router** | LLM-classified input → agent | `add_conditional_edges` |
| **Custom workflow** | Deterministic + LLM mixed | `StateGraph().compile()` |

### Quan trọng

- **Token economics**: stateful (Handoffs/Skills) tiết kiệm 40-50% calls cho repeat. Subagents thắng Skills cho multi-domain (9K vs 15K tokens).
- **`ToolMessage` với matching `tool_call_id` BẮT BUỘC** khi tool return Command, nếu không history bị corrupt.
- **`@wrap_model_call` middleware**: dynamic config tools/prompts theo state. Ví dụ:
  ```python
  @wrap_model_call
  def apply_step_config(request, handler):
      step = request.state.get("current_step", "triage")
      configs = {"triage": {...}, "specialist": {...}}
      request = request.override(system_prompt=..., tools=...)
      return handler(request)
  ```

---

## 2. Paper2Any — kiến trúc production thực tế

**KHÔNG dùng DeepAgents/Supervisor.** Hand-rolled với LangGraph + custom BaseAgent.

### Patterns đáng học

#### A. State inheritance 3 tầng

```python
@dataclass
class MainRequest:                         # config root
    chat_api_url: str = os.getenv("DF_API_URL", "test")
    api_key: str = os.getenv("DF_API_KEY", "test")
    model: str = "gpt-4o"
    language: str = "en"

@dataclass
class MainState:                           # state root
    request: MainRequest = field(default_factory=MainRequest)
    messages: Annotated[list[BaseMessage], add_messages] = field(default_factory=list)
    agent_results: Dict[str, Any] = field(default_factory=dict)
    temp_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Paper2PosterState(MainState):        # domain-specific
    request: Paper2PosterRequest = field(default_factory=Paper2PosterRequest)
    poster_width: int = 36
    output_pptx_path: str = ""
    errors: list[str] = field(default_factory=list)
```

**Key:** `Annotated[list, add_messages]` từ LangGraph để auto-merge messages.

#### B. Workflow decorator registry

```python
class RuntimeRegistry:
    _workflows: Dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str, factory: Callable):
        cls._workflows[name] = factory

@register("paper2poster")
def create_paper2poster_graph() -> GenericGraphBuilder:
    builder = GenericGraphBuilder(state_model=Paper2PosterState)
    builder.add_node("run_postergen", run_postergen_pipeline)
    return builder.build()
```

→ **18+ workflows** registered. Frontend chọn workflow qua name. Easy to extend.

#### C. GenericGraphBuilder wrapper

- `pre_tool` decorator: tool chạy trước node (data prep)
- `post_tool`: tool chạy sau node (cleanup, logging)
- Auto-wrap mọi node với role-based tool registration

#### D. Subprocess pool cho heavy work

```python
async def run_heavy_workflow_in_subprocess(*, mode: str, payload: dict):
    proc = await asyncio.create_subprocess_exec(
        python_bin, worker_script,
        "--mode", mode, "--input-json", input_json, "--output-json", output_json,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    return json.loads(output_json.read_text())
```

**Lý do:** isolation crash, GPU/memory cleanup, không block API. I/O qua JSON file (KHÔNG pickle).

#### E. Lazy LLM client (multi-tenant ready)

```python
def run_pipeline(state):
    env_backup = backup_env()
    os.environ["OPENAI_API_KEY"] = state.request.api_key      # per-tenant
    os.environ["OPENAI_BASE_URL"] = state.request.api_url
    try:
        modules = _import_modules()  # lazy import sau khi env set
        return modules['workflow'].ainvoke(state)
    finally:
        restore_env(env_backup)
```

→ Mỗi session dùng API key/endpoint khác nhau. CRITICAL cho SaaS multi-tenant.

#### F. NO Celery/Redis

Async + subprocess pool đủ scale cho document workflows. Đơn giản, ít moving parts.

---

## 3. So sánh BnK DeepAgent vs Paper2Any

| Aspect | BnK DeepAgent (plan) | Paper2Any | Action |
|--------|---------------------|-----------|--------|
| Framework | DeepAgents | LangGraph + custom | **Giữ DeepAgents** |
| State | Pydantic + JSON files | Dataclass + inheritance | **Adopt inheritance chain** |
| Workflow registry | Hardcoded list | Decorator registry | **Adopt decorator registry** |
| Heavy work | Async only | Subprocess pool | **PHẢI thêm subprocess pool** |
| Multi-tenant | Single env vars | Lazy env swap per request | **PHẢI adopt** |
| Tool scoping | Per-subagent dict | Role-based hooks | DeepAgents đã đủ, không cần |
| Persistence | Postgres checkpoint | File-based outputs | Giữ Postgres + S3 |

---

## 4. Khuyến nghị final architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI (REST + SSE)                         │
│  POST /sessions  POST /chat  POST /approve  POST /output-dir    │
└────────┬────────────────────────────────────┬───────────────────┘
         │                                    │
         ▼                                    ▼
┌──────────────────┐            ┌──────────────────────────────────┐
│ Workflow Registry│            │  Subprocess Pool                 │
│ @register("brd") │            │  render_brd, render_wbs,         │
│ @register("wbs") │            │  render_proposal (heavy I/O)     │
│ @register("prop")│            └──────────────────────────────────┘
└──────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  Per-workflow DeepAgent (create_deep_agent)                      │
│  • State: BRDState / WBSState / ProposalState ← inherit MainState│
│  • Backend: CompositeFilesystemBackend                           │
│  • Subagents: 5-13 specialists per workflow                      │
│  • Skills: domain-specific (banking/insurance/...)               │
│  • Memory: AGENTS.md per-session                                 │
│  • HITL: interrupt_on={"render_*": True}                         │
│  • Checkpointer: AsyncPostgresSaver                              │
└──────────────────────────────────────────────────────────────────┘
```

### 3 workflows ĐỘC LẬP, không 1 giant orchestrator

```python
# workflows/registry.py
WORKFLOWS = {}

def register_workflow(name: str):
    def deco(factory):
        WORKFLOWS[name] = factory
        return factory
    return deco

@register_workflow("brd")
def build_brd_workflow(session_state) -> CompiledGraph: ...

@register_workflow("wbs")
def build_wbs_workflow(session_state) -> CompiledGraph: ...

@register_workflow("proposal")
def build_proposal_workflow(session_state) -> CompiledGraph: ...
```

User chọn workflow qua API:
```
POST /sessions/{id}/run {"workflow": "brd"}
POST /sessions/{id}/run {"workflow": "wbs"}
```

Cross-workflow data qua **shared session workspace**:
```
workspace/{session_id}/
├── brd_state.json        # output của brd workflow
├── wbs_state.json        # output của wbs workflow (đọc brd_state.json làm input)
├── proposal_state.json   # đọc cả 2 file trên
└── AGENTS.md
```

### State inheritance pattern

```python
# state/base.py
class MainState(TypedDict):
    session_id: str
    project_context: ProjectContext
    output_dir: str
    workspace_dir: str
    messages: Annotated[list[BaseMessage], add_messages]

class BRDState(MainState):
    brd_doc: BRDDocument
    raw_features: str
    issues: list[Issue]
    revision_count: int

class WBSState(MainState):
    wbs_doc: WBSDocument
    timeline: TimelineData
    cost: CostBreakdown
    domain_profile: DomainProfile
    revision_count: int

class ProposalState(MainState):
    brd_ref: str            # path to brd_state.json
    wbs_ref: str            # path to wbs_state.json
    slides: list[SlideSpec]
```

### Subprocess pool cho rendering

```python
# infra/subprocess_pool.py
async def render_in_subprocess(
    renderer: Literal["brd", "wbs", "proposal"],
    input_json_path: str,
    output_path: str,
) -> dict:
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "rendering.worker",
        "--type", renderer,
        "--input", input_json_path,
        "--output", output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Render failed: {stderr.decode()}")
    return {"path": output_path, "size_kb": Path(output_path).stat().st_size // 1024}
```

→ `render_brd` tool gọi `render_in_subprocess(...)` thay vì invoke trực tiếp. Crash subprocess không kill API.

### Lazy LLM client từ session state

```python
# llm/factory.py
def create_chat_model(session_state: MainState):
    cfg = session_state["project_context"].llm_config
    if cfg.provider == "anthropic":
        return ChatAnthropic(
            model=cfg.model,
            api_key=cfg.api_key or os.environ.get("ANTHROPIC_API_KEY"),
            base_url=cfg.api_url,
        )
    if cfg.provider == "openai":
        return ChatOpenAI(...)
    ...
```

→ Mỗi session có thể dùng API key/endpoint khác nhau. Multi-tenant ready.

---

## 5. KHÔNG nên copy từ Paper2Any

- Hand-rolled BaseAgent class — DeepAgents đã giải quyết với subagent dict + middleware
- Pre/post tool hooks role-based — `subagents[i]["tools"]` của DeepAgents đủ
- Multi-process subprocess cho LLM call — chỉ cần cho rendering/file I/O

---

## 6. Update implementation plan

Trong [IMPLEMENTATION_PLAN_FULL.md](IMPLEMENTATION_PLAN_FULL.md) cần thêm:

1. **`workflows/registry.py`** — decorator registry cho 3 workflows
2. **`state/base.py`, `state/brd.py`, `state/wbs.py`, `state/proposal.py`** — inheritance chain
3. **`infra/subprocess_pool.py`** — subprocess pool cho rendering
4. **`llm/factory.py`** — lazy LLM client từ session state
5. **`rendering/worker.py`** — subprocess worker entry point

Đây sẽ là Sprint S0 (foundation) trước khi vào Sprint S1 (P1 Discovery tools).

---

## 7. Câu hỏi cho user trước khi vào code

1. **3 workflows độc lập** (BRD/WBS/Proposal) hay **1 orchestrator** routing tới 3 sub-pipelines? Theo tôi: 3 workflows độc lập tốt hơn — debug dễ, test dễ, billing dễ.
2. **Multi-tenant** ngay từ đầu (lazy LLM client) hay **single-tenant** trước, refactor sau? Multi-tenant từ đầu rẻ hơn nếu có kế hoạch SaaS.
3. **Subprocess pool**: dùng cho cả rendering VÀ heavy LLM workflow (vd: AI/ML training estimates)? Hay chỉ rendering?
4. **Cross-workflow data**: file-based (workspace JSON) hay state-based (passed via session)? File-based linh hoạt hơn — workflow có thể chạy độc lập + tái sử dụng output.

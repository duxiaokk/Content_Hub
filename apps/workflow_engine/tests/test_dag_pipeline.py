from __future__ import annotations

import asyncio

from workflow_engine.pipeline import DagWorkflowRunner, WorkflowGraphSpec, WorkflowNodeSpec
from workflow_engine.registry.contracts import ProcessResult, PublishResult, SourceItem
from workflow_engine.registry.plugin_registry import PluginRegistry


class StubFetcher:
    name = "stub-fetcher"

    async def fetch(self, request):  # noqa: ANN001
        return [
            SourceItem(
                source_type="rss",
                source_id="item-1",
                title="Item 1",
                source_url="https://example.com/1",
                raw_content="raw",
            )
        ]


class StubProcessor:
    name = "stub-processor"

    def __init__(self) -> None:
        self.last_options = None

    async def process(self, content, context):  # noqa: ANN001
        self.last_options = dict(context.options)
        content.processed_content = f"processed:{content.raw_content}"
        return ProcessResult(content=content, status="processed")


class StubPublisher:
    name = "stub-publisher"

    async def publish(self, content, target):  # noqa: ANN001
        return PublishResult(status="published", target_name=target.target_name)


class StubRepository:
    def __init__(self) -> None:
        self._next_id = 1

    def upsert_fetched_item(self, _item) -> int:  # noqa: ANN001
        value = self._next_id
        self._next_id += 1
        return value

    def mark_processed(self, *_args, **_kwargs) -> None:
        return None

    def mark_published(self, *_args, **_kwargs) -> None:
        return None


def test_dag_workflow_runner_executes_graph() -> None:
    registry = PluginRegistry()
    registry.register_fetcher(StubFetcher())
    registry.register_processor(StubProcessor())
    registry.register_publisher(StubPublisher())

    runner = DagWorkflowRunner(registry)
    runner._linear_runner.repository = StubRepository()
    result = asyncio.run(
        runner.run(
            WorkflowGraphSpec(
                run_id="run-1",
                workflow_name="content.workflow.run",
                source_name="stub",
                nodes=[
                    WorkflowNodeSpec(node_id="fetch", stage="fetch", component_name="stub-fetcher"),
                    WorkflowNodeSpec(
                        node_id="process",
                        stage="process",
                        component_name="stub-processor",
                        depends_on=["fetch"],
                    ),
                    WorkflowNodeSpec(
                        node_id="publish",
                        stage="publish",
                        component_name="stub-publisher",
                        depends_on=["process"],
                    ),
                ],
            )
        )
    )

    assert result["status"] == "succeeded"
    assert result["results"][0]["publish_status"] == "published"
    assert result["trace"]["items_succeeded"] == 1


def test_dag_workflow_runner_merges_tool_stage_results() -> None:
    registry = PluginRegistry()
    registry.register_fetcher(StubFetcher())
    processor = StubProcessor()
    registry.register_processor(processor)
    registry.register_publisher(StubPublisher())

    runner = DagWorkflowRunner(registry)
    runner._linear_runner.repository = StubRepository()

    async def fake_execute_tool_node(*_args, **_kwargs):  # noqa: ANN001
        return {"summary": "tool enriched context"}

    runner._execute_tool_node = fake_execute_tool_node  # type: ignore[method-assign]
    result = asyncio.run(
        runner.run(
            WorkflowGraphSpec(
                run_id="run-tool-1",
                workflow_name="content.workflow.run",
                source_name="stub",
                nodes=[
                    WorkflowNodeSpec(node_id="fetch", stage="fetch", component_name="stub-fetcher"),
                    WorkflowNodeSpec(
                        node_id="enrich",
                        stage="tool",
                        component_name="tool-calling-agent",
                        depends_on=["fetch"],
                        options={"result_key": "background_info"},
                    ),
                    WorkflowNodeSpec(
                        node_id="process",
                        stage="process",
                        component_name="stub-processor",
                        depends_on=["fetch", "enrich"],
                    ),
                    WorkflowNodeSpec(
                        node_id="publish",
                        stage="publish",
                        component_name="stub-publisher",
                        depends_on=["process"],
                    ),
                ],
            )
        )
    )

    assert result["status"] == "succeeded"
    assert processor.last_options is not None
    assert processor.last_options["tool_results"]["background_info"]["summary"] == "tool enriched context"
    assert "workflow_observations" in processor.last_options
    assert result["observations"]["tool_hit_rate"]["hit_rate"] == 1.0


def test_dag_workflow_runner_renders_tool_intent_template_and_flattens_results() -> None:
    registry = PluginRegistry()
    registry.register_fetcher(StubFetcher())
    processor = StubProcessor()
    registry.register_processor(processor)
    registry.register_publisher(StubPublisher())

    runner = DagWorkflowRunner(registry)
    runner._linear_runner.repository = StubRepository()
    captured: dict[str, object] = {}

    async def fake_execute_tool_node(spec, node, node_outputs, fetched_assets, processed_assets, results):  # noqa: ANN001
        captured["intent"] = runner._render_intent_template(  # noqa: SLF001
            str(node.options.get("intent_template") or ""),
            runner._build_tool_context(  # noqa: SLF001
                spec=spec,
                node=node,
                payload={},
                node_outputs=node_outputs,
                fetched_assets=fetched_assets,
                processed_assets=processed_assets,
                results=results,
            ),
        )
        return {"extra_note": "tool flattened"}

    runner._execute_tool_node = fake_execute_tool_node  # type: ignore[method-assign]
    result = asyncio.run(
        runner.run(
            WorkflowGraphSpec(
                run_id="run-tool-2",
                workflow_name="content.workflow.run",
                source_name="stub",
                nodes=[
                    WorkflowNodeSpec(node_id="fetch", stage="fetch", component_name="stub-fetcher"),
                    WorkflowNodeSpec(
                        node_id="enrich",
                        stage="tool",
                        component_name="tool-calling-agent",
                        depends_on=["fetch"],
                        options={
                            "result_key": "background_info",
                            "merge_mode": "flatten",
                            "include_fields": ["workflow_name", "fetched_items"],
                            "intent_template": "为 {workflow_name} 的第 {fetched_count} 条内容补充背景：{first_title}",
                        },
                    ),
                    WorkflowNodeSpec(
                        node_id="process",
                        stage="process",
                        component_name="stub-processor",
                        depends_on=["fetch", "enrich"],
                        options={"merge_mode": "flatten"},
                    ),
                    WorkflowNodeSpec(
                        node_id="publish",
                        stage="publish",
                        component_name="stub-publisher",
                        depends_on=["process"],
                    ),
                ],
            )
        )
    )

    assert result["status"] == "succeeded"
    assert captured["intent"] == "为 content.workflow.run 的第 1 条内容补充背景：Item 1"
    assert processor.last_options is not None
    assert processor.last_options["extra_note"] == "tool flattened"


def test_dag_workflow_runner_emits_reasoning_decisions() -> None:
    registry = PluginRegistry()
    registry.register_fetcher(StubFetcher())
    processor = StubProcessor()
    registry.register_processor(processor)
    registry.register_publisher(StubPublisher())

    runner = DagWorkflowRunner(registry)
    runner._linear_runner.repository = StubRepository()

    async def fake_execute_tool_node(*_args, **_kwargs):  # noqa: ANN001
        return {}

    runner._execute_tool_node = fake_execute_tool_node  # type: ignore[method-assign]
    result = asyncio.run(
        runner.run(
            WorkflowGraphSpec(
                run_id="run-tool-3",
                workflow_name="content.workflow.run",
                source_name="stub",
                limit=10,
                nodes=[
                    WorkflowNodeSpec(node_id="fetch", stage="fetch", component_name="stub-fetcher"),
                    WorkflowNodeSpec(
                        node_id="enrich",
                        stage="tool",
                        component_name="tool-calling-agent",
                        depends_on=["fetch"],
                    ),
                    WorkflowNodeSpec(
                        node_id="process",
                        stage="process",
                        component_name="stub-processor",
                        depends_on=["fetch", "enrich"],
                    ),
                    WorkflowNodeSpec(
                        node_id="publish",
                        stage="publish",
                        component_name="stub-publisher",
                        depends_on=["process"],
                    ),
                ],
            )
        )
    )

    assert result["reasoning_decisions"][0]["stage"] == "process"
    assert result["reasoning_decisions"][0]["decision"] == "supplement_tooling"
    assert result["reasoning_decisions"][1]["stage"] == "publish"


def test_dag_workflow_runner_executes_tool_plan_chain() -> None:
    registry = PluginRegistry()
    registry.register_fetcher(StubFetcher())
    processor = StubProcessor()
    registry.register_processor(processor)
    registry.register_publisher(StubPublisher())

    runner = DagWorkflowRunner(registry)
    runner._linear_runner.repository = StubRepository()
    calls: list[dict[str, object]] = []

    async def fake_invoke_tool_agent(*, run_id, task_type, payload, options):  # noqa: ANN001
        tool_call = payload["tool_calls"][0]
        tool_name = tool_call["tool_name"]
        parameters = tool_call["parameters"]
        calls.append({"run_id": run_id, "task_type": task_type, "parameters": parameters, "options": options})
        if tool_name == "extract":
            return {"result": {"query": f"topic:{parameters['text']}"}}
        if tool_name == "search":
            return {"result": {"snippet": f"found {parameters['query']}"}}
        if tool_name == "translate":
            return {"result": {"translated_text": f"ZH {parameters['text']}"}}
        raise AssertionError(f"unexpected tool {tool_name}")

    runner._invoke_tool_agent = fake_invoke_tool_agent  # type: ignore[method-assign]
    result = asyncio.run(
        runner.run(
            WorkflowGraphSpec(
                run_id="run-tool-plan-1",
                workflow_name="content.workflow.run",
                source_name="stub",
                nodes=[
                    WorkflowNodeSpec(node_id="fetch", stage="fetch", component_name="stub-fetcher"),
                    WorkflowNodeSpec(
                        node_id="enrich",
                        stage="tool",
                        component_name="tool-calling-agent",
                        depends_on=["fetch"],
                        options={
                            "result_key": "tool_chain",
                            "tool_plan": {
                                "steps": [
                                    {
                                        "id": "extract_step",
                                        "tool_name": "extract",
                                        "input_template": {"text": "{context.fetched_items.0.title}"},
                                        "output_key": "extracted",
                                    },
                                    {
                                        "id": "search_step",
                                        "tool_name": "search",
                                        "input_template": {"query": "{outputs.extracted.query}"},
                                        "output_key": "searched",
                                    },
                                    {
                                        "id": "translate_step",
                                        "tool_name": "translate",
                                        "input_template": {"text": "{outputs.searched.snippet}"},
                                        "output_key": "translated",
                                    },
                                ]
                            },
                        },
                    ),
                    WorkflowNodeSpec(
                        node_id="process",
                        stage="process",
                        component_name="stub-processor",
                        depends_on=["fetch", "enrich"],
                    ),
                    WorkflowNodeSpec(
                        node_id="publish",
                        stage="publish",
                        component_name="stub-publisher",
                        depends_on=["process"],
                    ),
                ],
            )
        )
    )

    assert result["status"] == "succeeded"
    assert len(calls) == 3
    assert calls[0]["parameters"]["text"] == "Item 1"
    assert calls[1]["parameters"]["query"] == "topic:Item 1"
    assert processor.last_options is not None
    assert processor.last_options["tool_results"]["tool_chain"]["outputs"]["translated"]["translated_text"] == "ZH found topic:Item 1"


def test_dag_workflow_runner_retries_tool_plan_step() -> None:
    registry = PluginRegistry()
    runner = DagWorkflowRunner(registry)
    attempts = {"search": 0}

    async def fake_invoke_tool_agent(*, run_id, task_type, payload, options):  # noqa: ANN001
        _ = run_id, task_type, options
        tool_call = payload["tool_calls"][0]
        attempts["search"] += 1
        if attempts["search"] == 1:
            raise RuntimeError("temporary failure")
        return {"result": {"snippet": tool_call["parameters"]["query"]}}

    runner._invoke_tool_agent = fake_invoke_tool_agent  # type: ignore[method-assign]
    tool_result = asyncio.run(
        runner._execute_tool_plan(  # type: ignore[attr-defined]  # noqa: SLF001
            spec=WorkflowGraphSpec(
                run_id="retry-run",
                workflow_name="content.workflow.run",
                source_name="stub",
                nodes=[],
            ),
            node=WorkflowNodeSpec(node_id="tool", stage="tool", component_name="tool-calling-agent"),
            options={
                "tool_plan": {
                    "steps": [
                        {
                            "id": "search_step",
                            "tool_name": "search",
                            "input_template": {"query": "keyword"},
                            "output_key": "searched",
                            "max_retries": 1,
                        }
                    ]
                }
            },
            payload={"context": {}},
            tool_context={"workflow_name": "content.workflow.run"},
        )
    )

    assert attempts["search"] == 2
    assert tool_result["outputs"]["searched"]["snippet"] == "keyword"
    assert tool_result["step_results"][0]["attempts"] == 2


def test_dag_workflow_runner_handles_tool_plan_fallback_and_continue() -> None:
    registry = PluginRegistry()
    runner = DagWorkflowRunner(registry)

    async def fake_invoke_tool_agent(*, run_id, task_type, payload, options):  # noqa: ANN001
        _ = run_id, task_type, options
        tool_call = payload["tool_calls"][0]
        if tool_call["tool_name"] == "search":
            raise RuntimeError("search failed")
        if tool_call["tool_name"] == "translate":
            return {"result": {"translated_text": f"ok:{tool_call['parameters']['text']}"}}
        raise AssertionError("unexpected tool")

    runner._invoke_tool_agent = fake_invoke_tool_agent  # type: ignore[method-assign]
    tool_result = asyncio.run(
        runner._execute_tool_plan(  # type: ignore[attr-defined]  # noqa: SLF001
            spec=WorkflowGraphSpec(
                run_id="fallback-run",
                workflow_name="content.workflow.run",
                source_name="stub",
                nodes=[],
            ),
            node=WorkflowNodeSpec(node_id="tool", stage="tool", component_name="tool-calling-agent"),
            options={
                "tool_plan": {
                    "steps": [
                        {
                            "id": "search_step",
                            "tool_name": "search",
                            "input_template": {"query": "keyword"},
                            "output_key": "searched",
                            "on_error": "fallback",
                            "fallback_output": {"snippet": "fallback snippet"},
                        },
                        {
                            "id": "translate_step",
                            "tool_name": "translate",
                            "input_template": {"text": "{outputs.searched.snippet}"},
                            "output_key": "translated",
                        },
                        {
                            "id": "continue_step",
                            "tool_name": "search",
                            "input_template": {"query": "broken"},
                            "output_key": "continued",
                            "on_error": "continue",
                        },
                    ]
                }
            },
            payload={"context": {}},
            tool_context={"workflow_name": "content.workflow.run"},
        )
    )

    assert tool_result["outputs"]["searched"]["snippet"] == "fallback snippet"
    assert tool_result["outputs"]["translated"]["translated_text"] == "ok:fallback snippet"
    assert tool_result["outputs"]["continued"]["status"] == "failed"
    assert tool_result["step_results"][0]["status"] == "fallback"
    assert tool_result["step_results"][2]["status"] == "continued"

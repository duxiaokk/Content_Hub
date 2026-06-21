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

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

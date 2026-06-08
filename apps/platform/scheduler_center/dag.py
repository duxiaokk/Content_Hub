"""轻量级 DAG (有向无环图) 引擎

功能:
  - DAG 构建: 添加节点和边
  - 拓扑排序: Kahn 算法
  - 环检测: DFS 检测循环依赖
  - 依赖解析: 获取节点的就绪条件
  - 并行度计算: 计算最大并行宽度
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator


@dataclass
class DAGNode:
    """DAG 节点。"""
    id: str
    data: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DAGNode):
            return False
        return self.id == other.id


@dataclass
class DAG:
    """有向无环图。

    用法:
        dag = DAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["A"])
        dag.add_node("C", depends_on=["A"])
        dag.add_node("D", depends_on=["B", "C"])
        assert dag.is_valid()
        layers = dag.topological_layers()
        # → ["A"], ["B", "C"], ["D"]
    """

    nodes: dict[str, DAGNode] = field(default_factory=dict)
    edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))  # parent → {children}
    reverse: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))  # child → {parents}

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------

    def add_node(self, node_id: str, *, depends_on: list[str] | None = None, data: dict[str, Any] | None = None) -> DAGNode:
        """添加节点及其依赖。"""
        if node_id not in self.nodes:
            self.nodes[node_id] = DAGNode(id=node_id, data=data or {})

        if depends_on:
            for parent_id in depends_on:
                if parent_id not in self.nodes:
                    self.nodes[parent_id] = DAGNode(id=parent_id)
                self.edges[parent_id].add(node_id)
                self.reverse[node_id].add(parent_id)

        return self.nodes[node_id]

    def get_node(self, node_id: str) -> DAGNode | None:
        return self.nodes.get(node_id)

    def get_parents(self, node_id: str) -> set[str]:
        return self.reverse.get(node_id, set())

    def get_children(self, node_id: str) -> set[str]:
        return self.edges.get(node_id, set())

    def get_root_nodes(self) -> set[str]:
        """获取所有根节点（无父节点的节点）。"""
        return {n for n in self.nodes if not self.reverse.get(n)}

    def get_leaf_nodes(self) -> set[str]:
        """获取所有叶子节点（无子节点的节点）。"""
        return {n for n in self.nodes if not self.edges.get(n)}

    def all_dependencies_of(self, node_id: str) -> set[str]:
        """获取某个节点的所有祖先（递归）。"""
        result: set[str] = set()
        stack = list(self.get_parents(node_id))
        while stack:
            p = stack.pop()
            if p not in result:
                result.add(p)
                stack.extend(self.get_parents(p))
        return result

    # ------------------------------------------------------------------
    # 验证
    # ------------------------------------------------------------------

    def has_cycle(self) -> bool:
        """DFS 检测是否存在环。"""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {n: WHITE for n in self.nodes}

        def _dfs(u: str) -> bool:
            color[u] = GRAY
            for v in self.edges.get(u, set()):
                if color[v] == GRAY:
                    return True
                if color[v] == WHITE and _dfs(v):
                    return True
            color[u] = BLACK
            return False

        for node_id in self.nodes:
            if color[node_id] == WHITE:
                if _dfs(node_id):
                    return True
        return False

    def is_valid(self) -> bool:
        """验证 DAG 合法性（无环）。"""
        if self.has_cycle():
            raise ValueError("DAG contains a cycle")
        return True

    # ------------------------------------------------------------------
    # 拓扑排序
    # ------------------------------------------------------------------

    def topological_order(self) -> list[str]:
        """Kahn 算法拓扑排序，返回节点 ID 列表。"""
        in_degree: dict[str, int] = {n: len(self.reverse.get(n, set())) for n in self.nodes}
        queue: deque[str] = deque(n for n, d in in_degree.items() if d == 0)
        result: list[str] = []

        while queue:
            u = queue.popleft()
            result.append(u)
            for v in self.edges.get(u, set()):
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(result) != len(self.nodes):
            raise ValueError("Graph has a cycle, topological sort impossible")
        return result

    def topological_layers(self) -> list[list[str]]:
        """按层级分组拓扑排序。

        返回 [[第0层], [第1层], ...]，同层节点可并行执行。
        """
        in_degree: dict[str, int] = {n: len(self.reverse.get(n, set())) for n in self.nodes}
        layers: list[list[str]] = []
        current = [n for n, d in in_degree.items() if d == 0]

        while current:
            layers.append(sorted(current))
            next_layer: list[str] = []
            for u in current:
                for v in self.edges.get(u, set()):
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        next_layer.append(v)
            current = next_layer

        return layers

    def max_parallelism(self) -> int:
        """最大并行宽度。"""
        return max((len(layer) for layer in self.topological_layers()), default=0)

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    def ready_nodes(self, completed: set[str]) -> set[str]:
        """返回所有依赖已满足、待执行的节点。"""
        ready: set[str] = set()
        for node_id in self.nodes:
            if node_id in completed:
                continue
            parents = self.get_parents(node_id)
            if parents.issubset(completed):
                ready.add(node_id)
        return ready

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "nodes": {
                nid: {"data": node.data}
                for nid, node in self.nodes.items()
            },
            "edges": {k: sorted(v) for k, v in self.edges.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> DAG:
        """从字典反序列化。"""
        dag = cls()
        for node_id, node_data in data.get("nodes", {}).items():
            dag.nodes[node_id] = DAGNode(id=node_id, data=node_data.get("data", {}))
        for parent, children in data.get("edges", {}).items():
            dag.edges[parent] = set(children)
            for child in children:
                dag.reverse.setdefault(child, set()).add(parent)
        return dag

    # ------------------------------------------------------------------
    # 遍历
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.nodes)

    def __iter__(self) -> Iterator[str]:
        return iter(self.topological_order())

    def __contains__(self, node_id: str) -> bool:
        return node_id in self.nodes

    def __repr__(self) -> str:
        return f"DAG(nodes={len(self.nodes)}, edges={sum(len(v) for v in self.edges.values())})"

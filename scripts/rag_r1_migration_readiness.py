from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = PROJECT_ROOT / "migrations" / "versions"
PLANNED_NEW_TABLES = (
    "kb_document_versions",
    "kb_assets",
    "kb_access_policies",
    "kb_releases",
    "kb_release_items",
    "kb_retrieval_runs",
    "kb_qa_evaluations",
)
PLANNED_EXTENSIONS = (
    "kb_documents",
    "kb_chunks",
    "kb_search_results",
    "kb_qa_tests",
    "audit_logs",
)


@dataclass(frozen=True)
class RevisionNode:
    revision: str
    down_revision: str | None
    filename: str


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError(f"migration_assignment_missing:{name}")


def read_revision_graph(versions_dir: Path = VERSIONS_DIR) -> tuple[RevisionNode, ...]:
    nodes: list[RevisionNode] = []
    for path in sorted(versions_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        revision = _literal_assignment(tree, "revision")
        down_revision = _literal_assignment(tree, "down_revision")
        if not isinstance(revision, str) or down_revision is not None and not isinstance(down_revision, str):
            raise ValueError(f"migration_revision_invalid:{path.name}")
        nodes.append(RevisionNode(revision, down_revision, path.name))
    revisions = [node.revision for node in nodes]
    if len(revisions) != len(set(revisions)):
        raise ValueError("migration_revision_duplicate")
    return tuple(nodes)


def migration_readiness(versions_dir: Path = VERSIONS_DIR) -> dict[str, Any]:
    nodes = read_revision_graph(versions_dir)
    revisions = {node.revision for node in nodes}
    referenced = {node.down_revision for node in nodes if node.down_revision}
    missing_parents = sorted(referenced.difference(revisions))
    heads = sorted(revisions.difference(referenced))
    roots = sorted(node.revision for node in nodes if node.down_revision is None)
    linear = (
        bool(nodes)
        and len(heads) == 1
        and len(roots) == 1
        and not missing_parents
        and len({node.down_revision for node in nodes if node.down_revision}) == len(nodes) - 1
    )
    blockers = []
    if not linear:
        blockers.append("alembic_graph_not_linear")
    blockers.extend(("rag_r1_revision_not_created", "migration_execution_confirmation_required"))
    return {
        "inspection_mode": "static_ast_only",
        "database_connected": False,
        "revision_created": False,
        "current_heads": heads,
        "current_roots": roots,
        "missing_parents": missing_parents,
        "linear": linear,
        "planned_down_revision": heads[0] if linear else None,
        "planned_revision": None,
        "new_tables": list(PLANNED_NEW_TABLES),
        "extended_tables": list(PLANNED_EXTENSIONS),
        "blockers": blockers,
        "nodes": [asdict(node) for node in nodes],
    }


def main() -> int:
    print(json.dumps(migration_readiness(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

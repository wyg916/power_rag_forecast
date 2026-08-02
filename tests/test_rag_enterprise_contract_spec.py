from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "docs" / "codex" / "contracts" / "rag_candidate_corpus_v1.schema.json"
API_CONTRACT_PATH = PROJECT_ROOT / "docs" / "codex" / "RAG_R1_API_PERMISSION_CONTRACT.md"
MIGRATION_DESIGN_PATH = PROJECT_ROOT / "docs" / "codex" / "RAG_R1_MIGRATION_DESIGN.md"


class RagEnterpriseContractSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.api_contract = API_CONTRACT_PATH.read_text(encoding="utf-8")
        cls.migration_design = MIGRATION_DESIGN_PATH.read_text(encoding="utf-8")

    def test_manifest_is_fail_closed_candidate_contract(self) -> None:
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(
            self.schema["properties"]["manifest_version"]["const"],
            "rag-candidate-corpus/v1",
        )
        self.assertEqual(self.schema["properties"]["release_status"]["const"], "candidate")
        self.assertIn("tenant_id", self.schema["required"])
        self.assertIn("corpus_sha256", self.schema["required"])

    def test_embedding_profile_is_bge_1024_only(self) -> None:
        profile = self.schema["$defs"]["embeddingProfile"]["properties"]
        self.assertEqual(profile["provider"]["const"], "sentence_transformers")
        self.assertEqual(profile["model"]["const"], "BAAI/bge-large-zh-v1.5")
        self.assertEqual(profile["dimension"]["const"], 1024)

    def test_chunk_requires_parent_and_complete_citation(self) -> None:
        chunk_required = set(self.schema["$defs"]["chunk"]["required"])
        self.assertTrue({"parent_chunk_id", "content_hash", "citation"} <= chunk_required)
        citation_required = set(self.schema["$defs"]["citation"]["required"])
        self.assertTrue(
            {
                "version_id",
                "section_path",
                "char_start",
                "char_end",
                "quote",
                "content_hash",
            }
            <= citation_required
        )

    def test_api_contract_separates_read_and_recording_search(self) -> None:
        self.assertIn("GET /api/knowledge/search", self.api_contract)
        self.assertIn("POST /api/knowledge/search", self.api_contract)
        self.assertIn("GET 与只读搜索不得", self.api_contract)
        self.assertIn("tenant_id", self.api_contract)
        self.assertIn("knowledge:publish", self.api_contract)
        self.assertIn("knowledge:diagnose", self.api_contract)

    def test_migration_design_forbids_implicit_execution(self) -> None:
        self.assertIn("不创建 Alembic revision", self.migration_design)
        self.assertIn("upgrade → downgrade → upgrade", self.migration_design)
        self.assertIn("人工确认", self.migration_design)
        self.assertIn("不执行批量删除", self.migration_design)


if __name__ == "__main__":
    unittest.main()

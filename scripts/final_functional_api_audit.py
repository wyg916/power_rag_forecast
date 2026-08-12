from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


PASSWORD = "FinalFunctionalOnly_20260812!"
USERS = ("ffa_admin_a", "ffa_analyst_a", "ffa_viewer_a", "ffa_admin_b")


def request_json(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str = "",
    payload: dict[str, Any] | None = None,
    timeout: int = 90,
) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(f"{base_url.rstrip('/')}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
            body = json.loads(raw.decode("utf-8")) if raw else None
            return {"method": method, "path": path, "status": response.status, "body": body}
    except HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {"detail": raw.decode("utf-8", errors="replace")[:500]}
        return {"method": method, "path": path, "status": exc.code, "body": body}


def login(base_url: str, username: str) -> tuple[str, dict[str, Any]]:
    result = request_json(
        base_url,
        "POST",
        "/api/auth/login",
        payload={"username": username, "password": PASSWORD},
    )
    body = result.get("body") or {}
    token = str(body.pop("access_token", ""))
    body.pop("token", None)
    result["body"] = body
    result["token_redacted"] = True
    if result["status"] != 200 or not token:
        raise RuntimeError(f"login failed for {username}: {result['status']}")
    return token, result


def collection_items(body: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if not isinstance(body, dict):
        return []
    for key in keys:
        value = body.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def summary(result: dict[str, Any], *, keys: tuple[str, ...] = ()) -> dict[str, Any]:
    body = result.get("body")
    output = {key: result[key] for key in ("method", "path", "status")}
    if keys:
        items = collection_items(body, *keys)
        output["count"] = len(items)
        output["ids"] = [
            str(item.get("session_id") or item.get("doc_id") or item.get("user_id") or item.get("id") or "")
            for item in items
            if item.get("session_id") or item.get("doc_id") or item.get("user_id") or item.get("id")
        ]
    if result["status"] >= 400:
        output["detail"] = body.get("detail") if isinstance(body, dict) else str(body)[:500]
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    tokens: dict[str, str] = {}
    logins: dict[str, dict[str, Any]] = {}
    for username in USERS:
        tokens[username], logins[username] = login(args.base_url, username)

    anonymous = request_json(args.base_url, "GET", "/api/settings/users")
    permission_cases = {
        "ffa_viewer_a": (
            ("GET", "/api/knowledge/documents", None, ("documents", "items")),
            ("GET", "/api/reports", None, ("reports", "items")),
            ("GET", "/api/models/active", None, ()),
            ("GET", "/api/tasks", None, ()),
            ("GET", "/api/settings/config", None, ()),
            ("GET", "/api/settings/users", None, ()),
            ("POST", "/api/ai/chat", {"question": "今天是几月几日？"}, ()),
            ("POST", "/api/ai/chatbi/analyze", {"question": "查询平均日前电价", "session_id": "viewer-denied"}, ()),
        ),
        "ffa_analyst_a": (
            ("GET", "/api/knowledge/documents", None, ("documents", "items")),
            ("GET", "/api/reports", None, ("reports", "items")),
            ("GET", "/api/models/active", None, ()),
            ("GET", "/api/tasks", None, ()),
            ("GET", "/api/settings/config", None, ()),
            ("GET", "/api/settings/users", None, ()),
        ),
    }
    permissions: dict[str, list[dict[str, Any]]] = {}
    for username, cases in permission_cases.items():
        permissions[username] = []
        for method, path, payload, keys in cases:
            result = request_json(args.base_url, method, path, token=tokens[username], payload=payload)
            permissions[username].append(summary(result, keys=keys))

    tenant_results: dict[str, dict[str, Any]] = {}
    raw_tenant: dict[str, dict[str, Any]] = {}
    for username in ("ffa_admin_a", "ffa_admin_b"):
        users = request_json(args.base_url, "GET", "/api/settings/users?page=1&page_size=50", token=tokens[username])
        knowledge = request_json(args.base_url, "GET", "/api/knowledge/documents", token=tokens[username])
        sessions = request_json(args.base_url, "GET", "/api/ai/chat/sessions", token=tokens[username])
        raw_tenant[username] = {"users": users, "knowledge": knowledge, "sessions": sessions}
        tenant_results[username] = {
            "users": summary(users, keys=("users", "items")),
            "knowledge": summary(knowledge, keys=("documents", "items")),
            "sessions": summary(sessions, keys=("sessions", "items")),
        }
    tenant_a_sessions = set(tenant_results["ffa_admin_a"]["sessions"].get("ids") or [])
    tenant_b_sessions = set(tenant_results["ffa_admin_b"]["sessions"].get("ids") or [])
    tenant_a_docs = set(tenant_results["ffa_admin_a"]["knowledge"].get("ids") or [])
    cross_doc_id = next(iter(tenant_a_docs), "missing-cross-tenant-doc")
    cross_doc = request_json(
        args.base_url,
        "GET",
        f"/api/knowledge/documents/{cross_doc_id}",
        token=tokens["ffa_admin_b"],
    )

    marker = f"FFA_MEMORY_{uuid.uuid4().hex[:10]}"
    memory_session_1 = f"ffa-memory-a-{uuid.uuid4().hex}"
    memory_session_2 = f"ffa-memory-a-recall-{uuid.uuid4().hex}"
    memory_session_b = f"ffa-memory-b-{uuid.uuid4().hex}"
    admit = request_json(
        args.base_url,
        "POST",
        "/api/ai/chat",
        token=tokens["ffa_analyst_a"],
        payload={
            "question": f"请记住：我的验收偏好标识是 {marker}",
            "session_id": memory_session_1,
            "model_provider": "auto",
        },
    )
    recall = request_json(
        args.base_url,
        "POST",
        "/api/ai/chat",
        token=tokens["ffa_analyst_a"],
        payload={"question": "你还记得我的验收偏好吗？", "session_id": memory_session_2, "model_provider": "auto"},
    )
    cross_user_recall = request_json(
        args.base_url,
        "POST",
        "/api/ai/chat",
        token=tokens["ffa_admin_a"],
        payload={"question": "你还记得我的验收偏好吗？", "session_id": f"ffa-memory-admin-{uuid.uuid4().hex}"},
    )
    cross_tenant_recall = request_json(
        args.base_url,
        "POST",
        "/api/ai/chat",
        token=tokens["ffa_admin_b"],
        payload={"question": "你还记得我的验收偏好吗？", "session_id": memory_session_b},
    )
    rename = request_json(
        args.base_url,
        "PATCH",
        f"/api/ai/chat/sessions/{memory_session_1}",
        token=tokens["ffa_analyst_a"],
        payload={"title": "最终验收记忆会话"},
    )
    delete = request_json(
        args.base_url,
        "DELETE",
        f"/api/ai/chat/sessions/{memory_session_1}",
        token=tokens["ffa_analyst_a"],
    )
    deleted_read = request_json(
        args.base_url,
        "GET",
        f"/api/ai/chat/sessions/{memory_session_1}",
        token=tokens["ffa_analyst_a"],
    )

    provider_results: dict[str, Any] = {}
    for provider in ("auto", "deepseek", "ollama"):
        response = request_json(
            args.base_url,
            "POST",
            "/api/ai/chat",
            token=tokens["ffa_analyst_a"],
            payload={
                "question": "请从组织流程角度分析跨部门协同的三个关键约束，并给出简短建议。",
                "session_id": f"ffa-provider-{provider}-{uuid.uuid4().hex}",
                "model_provider": provider,
            },
        )
        body = response.get("body") if isinstance(response.get("body"), dict) else {}
        provider_results[provider] = {
            "status": response["status"],
            "requested": body.get("model_provider_requested"),
            "used": body.get("model_provider_used"),
            "fallback": body.get("model_fallback"),
            "llm_used": body.get("llm_used"),
            "detail": body.get("detail"),
            "model_error": body.get("model_error"),
            "answer_nonempty": bool(str(body.get("answer") or "").strip()),
        }

    rag = request_json(
        args.base_url,
        "POST",
        "/api/ai/rag-answer",
        token=tokens["ffa_analyst_a"],
        payload={"question": "购电策略需要复核哪些约束？"},
    )
    rag_body = rag.get("body") if isinstance(rag.get("body"), dict) else {}
    rag_summary = {
        "status": rag["status"],
        "detail": rag_body.get("detail"),
        "grounding_status": rag_body.get("grounding_status"),
        "citation_count": len(rag_body.get("citations") or []),
        "retrieval": rag_body.get("retrieval") or {},
    }

    admit_body = admit.get("body") if isinstance(admit.get("body"), dict) else {}
    recall_body = recall.get("body") if isinstance(recall.get("body"), dict) else {}
    cross_user_body = cross_user_recall.get("body") if isinstance(cross_user_recall.get("body"), dict) else {}
    cross_tenant_body = cross_tenant_recall.get("body") if isinstance(cross_tenant_recall.get("body"), dict) else {}
    memory = {
        "marker_redacted": True,
        "admission": {
            "status": admit["status"],
            "decision": (admit_body.get("memory") or {}).get("admission"),
            "answer_acknowledged": "记录" in str(admit_body.get("answer") or ""),
        },
        "same_user_cross_session": {
            "status": recall["status"],
            "recalled_marker": marker in str(recall_body.get("answer") or ""),
            "retrieved_count": (recall_body.get("memory") or {}).get("retrieved_count"),
        },
        "cross_user": {
            "status": cross_user_recall["status"],
            "leaked_marker": marker in str(cross_user_body.get("answer") or ""),
        },
        "cross_tenant": {
            "status": cross_tenant_recall["status"],
            "leaked_marker": marker in str(cross_tenant_body.get("answer") or ""),
        },
        "session_lifecycle": {
            "rename_status": rename["status"],
            "delete_status": delete["status"],
            "deleted_read_status": deleted_read["status"],
        },
    }

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tokens_redacted": True,
        "logins": logins,
        "anonymous": summary(anonymous),
        "permissions": permissions,
        "tenant_scoping": {
            **tenant_results,
            "session_intersection": sorted(tenant_a_sessions & tenant_b_sessions),
            "document_intersection": sorted(tenant_a_docs & set(tenant_results["ffa_admin_b"]["knowledge"].get("ids") or [])),
            "cross_tenant_document_status": cross_doc["status"],
        },
        "memory": memory,
        "providers": provider_results,
        "rag": rag_summary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

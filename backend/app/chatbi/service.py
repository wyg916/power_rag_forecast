from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.ai.identity_context import IdentityContext
from backend.app.db.session import get_engine

from .catalog import CATALOG_VERSION
from .compiler import QueryCompileError, compile_analysis_plan
from .contracts import AnalysisPlan
from .memory import apply_remembered_context, recall_analysis_context, remember_analysis_context
from .planner import AnalysisPlanGenerationError, PlanLLM, generate_analysis_plan, repair_analysis_plan
from .result import QueryExecutionError, build_chart_spec, build_grounded_narrative, execute_result_dataset
from .validator import PlanValidation, validate_analysis_plan


class ChatBIServiceError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _identity(identity: IdentityContext) -> dict[str, str]:
    identity.require_valid(require_session=True)
    return {
        "tenant_id": identity.tenant_id,
        "workspace_id": identity.workspace_id,
        "user_id": identity.user_id,
        "agent_id": identity.agent_id,
        "session_id": identity.session_id,
        "run_id": identity.run_id,
    }


def _insert_audit(
    connection,
    identity: IdentityContext,
    plan: AnalysisPlan,
    question: str,
    validation: PlanValidation,
) -> None:
    scope = _identity(identity)
    connection.execute(
        text(
            """
            INSERT INTO chatbi_analysis_plans (
              analysis_plan_id, tenant_id, workspace_id, user_id, agent_id, session_id, run_id,
              question_hash, plan_hash, catalog_version, plan_json, validation_status,
              validation_errors, status
            ) VALUES (
              :analysis_plan_id, :tenant_id, :workspace_id, :user_id, :agent_id, :session_id, :run_id,
              :question_hash, :plan_hash, :catalog_version, CAST(:plan_json AS jsonb), :validation_status,
              CAST(:validation_errors AS jsonb), :status
            )
            """
        ),
        {
            **scope,
            "analysis_plan_id": plan.analysis_plan_id,
            "question_hash": hashlib.sha256(question.encode("utf-8")).hexdigest(),
            "plan_hash": plan.stable_hash(),
            "catalog_version": CATALOG_VERSION,
            "plan_json": json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            "validation_status": validation.status,
            "validation_errors": json.dumps(validation.public_dict()["issues"], ensure_ascii=False),
            "status": (
                "validated" if validation.valid
                else "clarification_required" if validation.status == "clarification_required"
                else "rejected"
            ),
        },
    )


def _finish_audit(
    connection,
    identity: IdentityContext,
    plan_id: str,
    *,
    status: str,
    query_hash: str | None = None,
    result_hash: str | None = None,
) -> None:
    result = connection.execute(
        text(
            """
            UPDATE chatbi_analysis_plans
               SET status=:status, query_hash=:query_hash, result_hash=:result_hash,
                   executed_at=:executed_at
             WHERE analysis_plan_id=:analysis_plan_id
               AND tenant_id=:tenant_id AND workspace_id=:workspace_id
               AND user_id=:user_id AND agent_id=:agent_id
               AND session_id=:session_id AND run_id=:run_id
            """
        ),
        {
            **_identity(identity),
            "analysis_plan_id": plan_id,
            "status": status,
            "query_hash": query_hash,
            "result_hash": result_hash,
            "executed_at": datetime.now(timezone.utc),
        },
    )
    if result.rowcount != 1:
        raise ChatBIServiceError("analysis_plan_scope_mismatch", "分析计划不属于当前身份范围。", status_code=404)


def get_analysis_plan_audit(identity: IdentityContext, analysis_plan_id: str, *, engine: Engine | None = None) -> dict[str, Any] | None:
    active_engine = engine or get_engine()
    with active_engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("SET TRANSACTION READ ONLY"))
        row = connection.execute(
            text(
                """
                SELECT analysis_plan_id, tenant_id, workspace_id, user_id, agent_id,
                       session_id, run_id, plan_hash, catalog_version, plan_json,
                       validation_status, validation_errors, status, query_hash,
                       result_hash, created_at, executed_at
                  FROM chatbi_analysis_plans
                 WHERE analysis_plan_id=:analysis_plan_id
                   AND tenant_id=:tenant_id AND workspace_id=:workspace_id
                   AND user_id=:user_id AND agent_id=:agent_id
                   AND session_id=:session_id AND run_id=:run_id
                """
            ),
            {**_identity(identity), "analysis_plan_id": analysis_plan_id},
        ).mappings().one_or_none()
        transaction.rollback()
    return dict(row) if row else None


def execute_chatbi_analysis(
    *,
    question: str,
    plan: AnalysisPlan,
    identity: IdentityContext,
    permissions: tuple[str, ...] | list[str] | set[str],
    engine: Engine | None = None,
    generated_plan: bool = False,
) -> dict[str, Any]:
    clean_question = question.strip()
    if not clean_question or len(clean_question) > 2000:
        raise ChatBIServiceError("invalid_question", "问题不能为空且不得超过 2000 字。", status_code=400)
    active_engine = engine or get_engine()
    server_plan = plan.model_copy(update={"analysis_plan_id": f"plan_{uuid4().hex}"})
    validation = validate_analysis_plan(server_plan, permissions=permissions)
    try:
        with active_engine.begin() as connection:
            _insert_audit(connection, identity, server_plan, clean_question, validation)
    except ChatBIServiceError:
        raise
    except Exception as exc:
        raise ChatBIServiceError("analysis_audit_unavailable", "分析审计记录不可用。", status_code=503) from exc
    if not validation.valid:
        if validation.status == "clarification_required":
            return {
                "available": False,
                "state": "clarification_required",
                "analysis_plan": server_plan.model_dump(mode="json"),
                "validation": validation.public_dict(),
                "clarification": {
                    "required": True,
                    "question": server_plan.clarification_question,
                },
                "lineage": {
                    "analysis_plan_id": server_plan.analysis_plan_id,
                    "run_id": identity.run_id,
                    "session_id": identity.session_id,
                    "catalog_version": CATALOG_VERSION,
                    "tenant_id": identity.tenant_id,
                    "workspace_id": identity.workspace_id,
                    "user_id": identity.user_id,
                    "agent_id": identity.agent_id,
                },
            }
        if not generated_plan:
            raise ChatBIServiceError("analysis_plan_invalid", "AnalysisPlan 未通过验证。", status_code=422)
        return {
            "available": False,
            "state": "unavailable",
            "analysis_plan": server_plan.model_dump(mode="json"),
            "validation": validation.public_dict(),
            "error": {
                "code": "PLANNER_INVALID",
                "message": "当前分析条件未能形成可执行计划，请补充指标、时间范围或比较对象后重试。",
            },
            "lineage": {
                "analysis_plan_id": server_plan.analysis_plan_id,
                "run_id": identity.run_id,
                "session_id": identity.session_id,
                "catalog_version": CATALOG_VERSION,
                "tenant_id": identity.tenant_id,
                "workspace_id": identity.workspace_id,
                "user_id": identity.user_id,
                "agent_id": identity.agent_id,
            },
        }
    try:
        compiled = compile_analysis_plan(server_plan, permissions=permissions)
        result = execute_result_dataset(server_plan, compiled, identity=identity, engine=active_engine)
        chart = build_chart_spec(server_plan, result)
        narrative = build_grounded_narrative(server_plan, result)
        with active_engine.begin() as connection:
            _finish_audit(
                connection,
                identity,
                server_plan.analysis_plan_id,
                status="executed",
                query_hash=result.query_hash,
                result_hash=result.result_hash,
            )
    except (QueryCompileError, QueryExecutionError, ValueError) as exc:
        try:
            with active_engine.begin() as connection:
                _finish_audit(connection, identity, server_plan.analysis_plan_id, status="failed")
        except Exception:
            pass
        raise ChatBIServiceError("analysis_execution_failed", "ChatBI 分析执行失败。", status_code=503) from exc
    return {
        "available": result.state == "success",
        "state": result.state,
        "analysis_plan": server_plan.model_dump(mode="json"),
        "validation": validation.public_dict(),
        "result_dataset": result.model_dump(mode="json", by_alias=True),
        "chart_spec": chart.model_dump(mode="json"),
        "narrative": narrative.model_dump(mode="json"),
        "lineage": {
            "analysis_plan_id": server_plan.analysis_plan_id,
            "run_id": identity.run_id,
            "session_id": identity.session_id,
            "catalog_version": CATALOG_VERSION,
            "query_hash": result.query_hash,
            "result_hash": result.result_hash,
            "identity_scope_hash": result.identity_scope_hash,
            "tenant_id": identity.tenant_id,
            "workspace_id": identity.workspace_id,
            "user_id": identity.user_id,
            "agent_id": identity.agent_id,
            "datasets": list(server_plan.datasets),
            "metrics": list(server_plan.metrics),
            "joins": list(server_plan.joins),
        },
    }


def execute_chatbi_turn(
    *,
    question: str,
    plan: AnalysisPlan | None,
    identity: IdentityContext,
    permissions: tuple[str, ...] | list[str] | set[str],
    requested_provider: str = "auto",
    engine: Engine | None = None,
    planner_router: PlanLLM | None = None,
) -> dict[str, Any]:
    """Plan, resolve, validate, execute, and remember one governed ChatBI turn."""
    active_engine = engine or get_engine()
    try:
        remembered = recall_analysis_context(identity, engine=active_engine)
    except Exception as exc:
        raise ChatBIServiceError("analysis_memory_unavailable", "分析上下文当前不可用。", status_code=503) from exc
    planner_meta: dict[str, Any]
    generated_plan = plan is None
    if generated_plan:
        attempts = 2 if (requested_provider or "auto").strip().lower() == "auto" else 1
        last_error: AnalysisPlanGenerationError | None = None
        for attempt in range(1, attempts + 1):
            try:
                draft, planner_meta = generate_analysis_plan(
                    question,
                    remembered,
                    requested_provider=requested_provider,
                    router=planner_router,
                )
                initial_validation = validate_analysis_plan(draft, permissions=permissions)
                if not initial_validation.valid and not planner_meta.get("repair_attempted"):
                    draft, planner_meta = repair_analysis_plan(
                        question,
                        remembered,
                        draft,
                        [
                            {
                                "code": item.code,
                                "field": item.field,
                                "message": item.message,
                            }
                            for item in initial_validation.issues
                        ],
                        requested_provider=requested_provider,
                        router=planner_router,
                    )
                planner_meta["attempts"] = attempt + int(
                    bool(planner_meta.get("repair_attempted"))
                )
                break
            except AnalysisPlanGenerationError as exc:
                last_error = exc
        else:
            assert last_error is not None
            raise ChatBIServiceError(
                "analysis_plan_generation_unavailable",
                str(last_error),
                status_code=503,
            ) from last_error
    else:
        draft = plan
        planner_meta = {"source": "provided_analysis_plan", "provider": None, "model": None, "fallback": False}

    resolved, memory_meta = apply_remembered_context(draft, remembered)
    if generated_plan:
        generated_validation = validate_analysis_plan(resolved, permissions=permissions)
        if not generated_validation.valid and generated_validation.status != "clarification_required":
            permission_limited = any(
                issue.code.endswith("_forbidden") or issue.code == "dataset_not_ai_accessible"
                for issue in generated_validation.issues
            )
            clarification_question = (
                "当前访问范围无法执行这项分析，请改用可访问的业务指标或维度。"
                if permission_limited
                else "请明确要分析的业务指标、时间范围和分组维度，以便生成可执行的分析。"
            )
            resolved = AnalysisPlan.model_validate(
                {
                    "clarification_required": True,
                    "clarification_question": clarification_question,
                }
            )
            planner_meta["generated_plan_state"] = "clarification_required"
            planner_meta["validation_issue_codes"] = [issue.code for issue in generated_validation.issues]
    response = execute_chatbi_analysis(
        question=question,
        plan=resolved,
        identity=identity,
        permissions=permissions,
        engine=active_engine,
        generated_plan=plan is None,
    )
    response["planner"] = planner_meta
    response["memory_context"] = {**memory_meta, "persisted": False}
    if response["state"] not in {"clarification_required", "unavailable"}:
        try:
            admission = remember_analysis_context(identity, AnalysisPlan.model_validate(response["analysis_plan"]), engine=active_engine)
        except Exception as exc:
            raise ChatBIServiceError("analysis_memory_write_failed", "分析上下文保存失败。", status_code=503) from exc
        if admission.get("decision") != "LONG_TERM_ACCEPTED" or admission.get("status") != "active":
            raise ChatBIServiceError("analysis_memory_write_rejected", "分析上下文未通过记忆准入。", status_code=503)
        response["memory_context"]["persisted"] = True
    return response

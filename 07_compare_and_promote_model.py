from __future__ import annotations

import argparse

from automation_common import get_pipeline_paths, load_config, setup_run_logger
from model_ops.model_comparator import compare_latest_candidate
from model_ops.promotion_manager import get_latest_candidate_version, promote_to_active
from services.config_service import disable_database_if_unavailable


def main() -> None:
    parser = argparse.ArgumentParser(description="候选模型对比与受控上线")
    parser.add_argument("--promote-if-qualified", action="store_true", help="仅在候选模型满足阈值时自动上线")
    parser.add_argument("--promote-latest-candidate", action="store_true", help="人工确认后把最新 candidate 模型设为 Active")
    parser.add_argument("--model-version", default="", help="人工指定要上线的模型版本")
    parser.add_argument("--approved-by", default="system", help="上线审批人")
    args = parser.parse_args()

    config = load_config()
    paths = get_pipeline_paths(config)
    log, _ = setup_run_logger(paths.log_dir, "07_compare_and_promote_model")
    disable_database_if_unavailable(config, log=log)

    if args.model_version:
        promote_to_active(config, args.model_version, approved_by=args.approved_by, log=log)
        return

    if args.promote_latest_candidate:
        candidate_version = get_latest_candidate_version(config)
        if not candidate_version:
            log("未找到 candidate 模型，无法设为 Active。")
            return
        promote_to_active(config, candidate_version, approved_by=args.approved_by, log=log)
        return

    decision = compare_latest_candidate(config, log=log)
    if args.promote_if_qualified and decision.promote:
        if decision.candidate_model_version:
            promote_to_active(config, decision.candidate_model_version, approved_by=args.approved_by, log=log)
        else:
            log("候选模型满足阈值，但未能识别候选版本，跳过自动上线。")
    else:
        log(f"模型对比完成：{decision}")


if __name__ == "__main__":
    main()

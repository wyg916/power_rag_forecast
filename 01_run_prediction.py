from __future__ import annotations

import argparse

from services.prediction_service import run_prediction


def main() -> None:
    parser = argparse.ArgumentParser(description="预测入口")
    parser.add_argument("--fast-forecast", action="store_true", help="加载 Active 模型快速预测，不重新训练")
    args = parser.parse_args()
    run_prediction(fast_forecast=args.fast_forecast)


if __name__ == "__main__":
    main()

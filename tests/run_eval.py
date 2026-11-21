"""
Evaluation Runner for RIT Assistant v3.
Runs the complete question suite from tests/eval_questions.csv against the real indexed data.
Prints score, expected vs actual mode, pass/fail, and calculates the margin for tuning MIN_SCORE.

Run from project root:
    python -m tests.run_eval
"""

import csv
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

import config
from backend.rag import RAGPipeline

def run_evaluation(
    eval_csv_path: Path = Path(__file__).resolve().parent / "eval_questions.csv",
    rag: RAGPipeline = None
) -> Tuple[bool, float, float, float]:
    print("\n" + "=" * 90)
    print("RUNNING RIT ASSISTANT EVALUATION SUITE ON REAL DATA")
    print("=" * 90)

    if rag is None:
        rag = RAGPipeline()
        rag.load_index()

    assert eval_csv_path.exists(), f"Evaluation questions not found at {eval_csv_path}"

    print(f"\nEvaluating questions from {eval_csv_path}:")
    print("-" * 90)
    print(f"{'#':<3} | {'Question':<42} | {'Score':<6} | {'Exp Mode':<10} | {'Act Mode':<10} | {'Status'}")
    print("-" * 90)

    total = 0
    passed = 0

    real_scores: List[float] = []
    oos_scores: List[float] = []

    with open(eval_csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            q = row["question"].strip()
            exp_sub = row["expected_substring"].strip()
            exp_mode = row["expected_mode"].strip()

            res = rag.answer(q)
            act_mode = res.get("mode", "")
            scores = res.get("scores", [0.0])
            top_score = scores[0] if scores else 0.0
            ans = res.get("answer", "")

            # LLM mode is valid for semantic document questions if grounded LLM is enabled
            mode_ok = (act_mode == exp_mode) or (exp_mode == "semantic" and act_mode in ("semantic", "llm"))
            sub_ok = (exp_sub.lower() in ans.lower())

            test_pass = mode_ok and sub_ok
            status_str = "PASS" if test_pass else "FAIL"

            if test_pass:
                passed += 1
            total += 1

            if exp_mode == "no_answer":
                oos_scores.append(top_score)
            else:
                real_scores.append(top_score)

            short_q = q[:40] + ".." if len(q) > 42 else q
            print(f"{i:<3} | {short_q:<42} | {top_score:<6.3f} | {exp_mode:<10} | {act_mode:<10} | {status_str}")

            if not test_pass:
                print(f"    -> MISMATCH: Exp Substring='{exp_sub}' in Answer: '{ans[:80]}...'")

    print("-" * 90)
    print(f"Summary: {passed}/{total} Passed ({passed/total*100:.1f}%)")

    min_real = min(real_scores) if real_scores else 0.0
    max_oos = max(oos_scores) if oos_scores else 0.0
    margin = min_real - max_oos

    print(f"\nScore Analysis & MIN_SCORE Tuning:")
    print(f"  Lowest real-answer score:  {min_real:.4f}")
    print(f"  Highest out-of-scope score: {max_oos:.4f}")
    print(f"  Safety Margin:              {margin:+.4f}")
    print(f"  Current config.MIN_SCORE:   {config.MIN_SCORE}")
    print("=" * 90 + "\n")

    return passed == total, min_real, max_oos, margin

if __name__ == "__main__":
    success, _, _, _ = run_evaluation()
    sys.exit(0 if success else 1)

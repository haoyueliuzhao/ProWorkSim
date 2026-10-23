"""Plot the audited 500-task outcomes; unknown segments are not confidence intervals."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    keys = ["qwen:REF", "qwen:MATCH", "qwen:PROJECT",
            "deepseek:REF-nonthinking", "deepseek:MATCH-nonthinking", "deepseek:PROJECT-nonthinking",
            "deepseek:REF-thinking", "deepseek:MATCH-thinking", "deepseek:PROJECT-thinking"]
    labels = ["Qwen REF (thinking)", "Qwen MATCH (nonthinking)", "Qwen PROJECT (nonthinking)",
              "DeepSeek REF (nonthinking)", "DeepSeek MATCH (nonthinking)", "DeepSeek PROJECT (nonthinking)",
              "DeepSeek REF (thinking)", "DeepSeek MATCH (thinking)", "DeepSeek PROJECT (thinking)"]
    matplotlib.rcParams.update({"font.size": 10, "svg.fonttype": "none", "svg.hashsalt": "v055-final-results-r1"})
    figure, ax = plt.subplots(figsize=(11.5, 6.3))
    for y, key in enumerate(keys):
        group = summary["groups"][key]
        success, unknown, failed = (group[name] for name in ("code_success", "code_unknown_total", "code_definite_failure"))
        assert group["planned"] == 500 and success + unknown + failed == 500
        low, high = success / 5, (success + unknown) / 5
        ax.barh(y, low, color="#286b8e", height=.65)
        ax.barh(y, unknown / 5, left=low, color="#f6d99b", edgecolor="#9c6919", hatch="///", height=.65, linewidth=.4)
        ax.barh(y, failed / 5, left=high, color="#e5e8eb", height=.65)
        ax.text(low / 2, y, str(success), color="white", ha="center", va="center", fontweight="bold")
        ax.text(101.2, y, f"{low:.1f}–{high:.1f}%   (U={unknown})", va="center", fontsize=9)
    ax.set_yticks(range(9), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xlabel("Share of the same 500 planned tasks (%)")
    ax.set_title("Code outcomes on SWE-bench Verified 500", loc="left", fontweight="bold", pad=15)
    for y in (2.5, 5.5):
        ax.axhline(y, color="#a8b1ba", linewidth=.6)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(handles=[Patch(facecolor="#286b8e", label="Verified success"),
                       Patch(facecolor="#f6d99b", edgecolor="#9c6919", hatch="///", label="Technical unknown"),
                       Patch(facecolor="#e5e8eb", label="Determinate unresolved")],
              loc="lower left", bbox_to_anchor=(-.02, -0.19), ncol=3, frameon=False)
    figure.text(.025, .025, "Ranges assign all unknown outcomes to failure/success; they are not confidence intervals.\n"
                "Observed run revisions are pooled for inventory description; no entered model episode was replayed.",
                 fontsize=8, color="#4b5563")
    figure.subplots_adjust(left=.31, right=.78, top=.89, bottom=.19)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, format="svg", metadata={"Date": None})
    plt.close(figure)


if __name__ == "__main__":
    main()

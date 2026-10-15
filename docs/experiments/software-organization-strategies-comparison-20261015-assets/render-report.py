#!/usr/bin/env python3
"""Render existing comparison data and Markdown; no experiment/model imports.

Usage: render-report.py charts | render | all [--markdown PATH]
Dependencies: matplotlib, numpy, Pillow, Markdown, ReportLab.
The caller supplies the isolated dependency path; no installation is performed.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import os
from pathlib import Path
import re
import textwrap
from urllib.parse import quote, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

ASSETS = Path(__file__).resolve().parent
DEFAULT_MD = ASSETS.parent / "software-organization-strategies-comparison-20261015.md"
DEFAULT_FONT = Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf")
DEFAULT_REPOSITORY = "https://github.com/haoyueliuzhao/ProWorkSim/blob/organization-strategy-report/"
INK = "#243447"
BLUE = "#256a91"
TEAL = "#168278"
ORANGE = "#c67532"
LIGHT = "#edf3f7"
MUTED = "#5a6877"


def read_json(name):
    return json.loads((ASSETS / name).read_text(encoding="utf-8"))


def chart_environment(font):
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/organization-strategy-report-mpl")
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import font_manager, pyplot as plt

    font_manager.fontManager.addfont(str(font))
    cjk = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({
        "font.family": ["DejaVu Sans", cjk],
        "font.size": 11,
        "axes.unicode_minus": False,
        "axes.titleweight": "bold",
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": INK,
        "axes.edgecolor": "#b4c2cb",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "svg.fonttype": "path",
        "savefig.facecolor": "white",
    })
    return plt


def save_chart(fig, name, plt):
    for suffix in ("png", "svg"):
        output = ASSETS / f"{name}.{suffix}"
        fig.savefig(output, dpi=200, bbox_inches="tight", pad_inches=0.18)
        print(f"created {output}")
    plt.close(fig)


def style_axis(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#dce4ea", lw=0.6)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)


def flow_chart(plt):
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    fig, ax = plt.subplots(figsize=(14, 11.8))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 12.3)
    ax.axis("off")
    ax.text(0, 12.05, "组织策略如何执行", fontsize=21, weight="bold")
    ax.text(0, 11.58, "制度示意｜同一冻结 actor；同槽共享团队预算；成员调用按调度顺序执行", fontsize=12, color=MUTED)

    def box(x, y, w, h, label, color=BLUE, size=11):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.10",
                                   facecolor=LIGHT, edgecolor=color, lw=1.5))
        ax.text(x+w/2, y+h/2, label, ha="center", va="center", fontsize=size, linespacing=1.5)

    def arrow(x1, y1, x2, y2, label=None):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14,
                                    color=MUTED, lw=1.4))
        if label:
            ax.text((x1+x2)/2, (y1+y2)/2+0.16, label, ha="center", va="bottom", fontsize=9, color=MUTED)

    def heading(y, title, subtitle):
        ax.text(0.05, y, title, fontsize=12, weight="bold", va="top", linespacing=1.4)
        offset = .64 if "\n" in title else .35
        ax.text(0.05, y-offset, subtitle, fontsize=9.2, color=MUTED, va="top")

    heading(10.95, "S1  单人自主", "无隐藏伙伴")
    box(2.55, 10.10, 4.5, .85, "001：读取 → 实现 → 测试 → 固定")
    arrow(7.12, 10.52, 8.3, 10.52)
    box(8.4, 10.10, 4.75, .85, "001：主动提交最后固定版本", TEAL)

    heading(9.55, "F2 / O3 / D\n自主组织", "不预定经理、职责或提交者")
    box(2.55, 8.44, 4.65, 1.12, "F2：初始2，存活上限2 / 累计2\nO3：初始2，存活上限4 / 累计上限6\nD2 / D4：初始1，名额2 / 4", size=10.5)
    arrow(7.27, 9.0, 8.3, 9.0)
    box(8.4, 8.44, 4.75, 1.12, "成员可自行选择分工、交流和复用\nO3 / D 允许自主创建成员\n名额是权限，不保证实际增员", TEAL, 10.5)

    heading(7.88, "I2 / I4\n独立候选＋选择", "N=2 或4；选择者为原001")
    box(2.55, 6.87, 4.65, 1.08, "N个隔离生成者\n共70% token，按N均分\n每人最后一份固定patch为候选", size=10.5)
    arrow(7.27, 7.4, 8.3, 7.4, "显式取得")
    box(8.4, 6.87, 4.75, 1.08, "原001：预留30%＋生成剩余额度\n选择、采用、本人测试、固定、提交\n禁止编辑 / 合并；无新增评委", TEAL, 10.5)

    heading(6.29, "P2  两阶段流水线", "仅最后阶段可正式提交")
    box(2.55, 5.29, 4.65, 1.02, "001：实现 / 测试 / 固定\n60% token")
    arrow(7.27, 5.80, 8.3, 5.80, "显式取得")
    box(8.4, 5.29, 4.75, 1.02, "002：复核＋可修订 / 合并\n测试 / 固定 / 提交；40% token", TEAL)

    heading(4.64, "P4  四阶段流水线", "成员初始均存在\n仅调度当前阶段")
    xs = [2.55, 5.32, 8.09, 10.86]
    labels = ["001  实现\n可编辑、测试、固定\n35% token",
              "002  复核\n禁止编辑 / 合并\n20% token",
              "003  修订整合\n可编辑 / 合并\n25% token",
              "004  验证提交\n禁止编辑 / 合并\n20% token"]
    for i, (x, label) in enumerate(zip(xs, labels)):
        box(x, 3.42, 2.3, 1.25, label, TEAL if i == 3 else BLUE, 10)
        if i < 3:
            arrow(x+2.34, 4.04, xs[i+1]-.08, 4.04)
    ax.text(2.55, 3.08, "阶段切换不复制工作区；每次交接均需合法共享与显式采用 / 整合。", fontsize=11, color=ORANGE)

    ax.add_patch(FancyBboxPatch((.05, .58), 13.25, 1.95, boxstyle="round,pad=.12,rounding_size=.12",
                               facecolor="#fff8eb", edgecolor="#dfbe8b"))
    notes = [
        "共同约束  所有成员使用同一 actor；会话 / 工作区私有；多人不等于团队内多GPU并行。",
        "预算口径  图中比例为团队 token 的阶段预留；决定 / attempt / 测试有各自配额（见正文）。",
        "成果取得  公开可见不等于实际取得；伙伴私史和专属测试正文不会自动继承。",
        "额度传递  I / P 早期阶段不可正式提交；阶段余额只向后，团队总账不重置。",
    ]
    for i, note in enumerate(notes):
        ax.text(.27, 2.18-i*.41, note, fontsize=11, va="center")
    ax.text(.05, .08, "依据：冻结制度目录 strategy-catalog.json；本图表示策略权限与流程，不表示已发生的协作或收益。", fontsize=9, color=MUTED)
    save_chart(fig, "strategy-flows", plt)


def personnel_chart(plt, data, historical):
    import numpy as np

    fig, axs = plt.subplots(2, 2, figsize=(12, 8.1), gridspec_kw={"width_ratios": [1, 1.25]})
    fig.subplots_adjust(top=.84, bottom=.14, left=.16, right=.95, hspace=.66, wspace=.3)
    fig.suptitle("固定人数与自主组织：完整成功和完整费用", fontsize=18, x=.035, ha="left", y=.98)
    fig.text(.035, .91, "每条件 n=8；上下两行属于不同协议与任务面板，不跨版本连线或合并排名。", fontsize=11, color=MUTED)
    old = historical["v038"]["conditions"]
    new = {d["condition"]: d for d in data["v045"]["aggregates"]}
    groups = [
        ("v038｜旧schema任务", ["O1 固定2人", "O2 固定4人", "O3 初始2 / 可扩编"],
         [r["successes"] for r in old], [r["mean_tokens_per_episode"] for r in old]),
        ("v045｜LA / HA / LB / HB", ["S1 单人", "F2 固定2人", "O3 初始2 / 可扩编"],
         [new[c]["R"]["known_sum"] for c in ("S1", "F2", "O3")],
         [new[c]["mean_complete_actual_tokens"] for c in ("S1", "F2", "O3")]),
    ]
    for row, (title, labels, success, costs) in enumerate(groups):
        for col, ax in enumerate(axs[row]):
            style_axis(ax)
            ax.invert_yaxis()
            ax.set_yticks(np.arange(3), labels if col == 0 else [""]*3)
        left, right = axs[row]
        left.set_title(title, loc="left", fontsize=12, pad=18)
        left.barh(range(3), success, height=.52, color=BLUE)
        left.set_xlim(0, 8.65)
        left.set_xticks(range(0, 9, 2))
        left.set_xlabel("完整成功数 / 8")
        for i, val in enumerate(success):
            left.text(val+.13, i, f"{val}/8", va="center", fontsize=12, weight="bold")
        right.barh(range(3), [v/1000 for v in costs], height=.52, color=TEAL)
        right.set_xlim(0, 565)
        right.set_xticks([0, 100, 200, 300, 400, 500])
        right.set_xlabel("全槽平均完整 token（千）")
        for i, val in enumerate(costs):
            right.text(val/1000+8, i, f"{val/1000:,.1f}k", va="center", fontsize=11)
    fig.text(.035, .045, "共同预算均为500k token / 槽。费用包含失败和全部成员活动；O3名额不等于实际增员。\n来源：historical-context.json / v038；comparison-data.json / v045。", fontsize=10, color=MUTED, linespacing=1.5)
    save_chart(fig, "personnel-comparison", plt)


def architecture_chart(plt, data):
    import numpy as np
    from matplotlib.patches import Patch

    order = ["S1", "D2", "D4", "I2", "I4", "P2", "P4"]
    lookup = {(r["condition"], r["team_token_budget"]): r for r in data["v047"]["aggregates"]}
    fig, axs = plt.subplots(1, 2, figsize=(13.3, 8.5), gridspec_kw={"width_ratios": [1, 1.35]})
    fig.subplots_adjust(top=.82, bottom=.18, left=.08, right=.95, wspace=.28)
    fig.suptitle("v047｜架构 × 团队预算", fontsize=19, x=.035, ha="left", y=.98)
    fig.text(.035, .925, "每个已设置配置 n=4；阶段B的500k四种架构事前锁定，D2 / I2 / P2未设置。", fontsize=11, color=MUTED)
    for ax in axs:
        style_axis(ax)
        ax.set_yticks(np.arange(len(order)), order)
        ax.set_ylim(len(order)-.45, -.6)
    axs[0].set_xlim(0, 4.55)
    axs[0].set_xticks(range(5))
    axs[0].set_xlabel("完整成功数 / 4")
    axs[1].set_xlim(0, 575)
    axs[1].set_xticks([0, 100, 200, 300, 400, 500])
    axs[1].set_xlabel("全槽平均完整 token（千）")
    axs[0].set_title("成功（失败保留在分母）", loc="left", fontsize=12, pad=12)
    axs[1].set_title("完整费用（含全部阶段和失败）", loc="left", fontsize=12, pad=12)
    for budget, offset, color in ((250000, -.18, BLUE), (500000, .18, ORANGE)):
        for i, condition in enumerate(order):
            y = i+offset
            r = lookup.get((condition, budget))
            if r is None:
                for ax in axs:
                    ax.text(.06 if ax is axs[0] else 5, y, "未设置", color="#85909a", va="center", fontsize=9.5)
                continue
            score = r["R"]["known_sum"] if r["R"]["mean"] is not None else None
            cost = r["mean_complete_actual_tokens"]
            for ax, val, label, pad in (
                (axs[0], score, f"{score}/4", .09),
                (axs[1], None if cost is None else cost/1000, "未知" if cost is None else f"{cost/1000:,.1f}k", 6),
            ):
                if val is None:
                    ax.text(pad, y, "未知", va="center", color=MUTED)
                    continue
                ax.barh(y, val, height=.29, color=color)
                if val == 0:
                    ax.plot(0, y, marker="|", color=color, markersize=13, markeredgewidth=2, clip_on=False)
                ax.text(val+pad, y, label, va="center", fontsize=10)
    fig.legend(handles=[Patch(color=BLUE, label="250k：阶段A"), Patch(color=ORANGE, label="500k：事前锁定阶段B")],
               loc="upper right", bbox_to_anchor=(.96, .9), frameon=False, ncol=2, fontsize=11)
    fig.text(.035, .055, "D2 / D4实际均保持单人；其名额上限不代表实际多人协作。两预算从独立初态运行。\n一个root改变完整成功结果即改变25个百分点；不展示总体推断或跨版本排名。来源：comparison-data.json / v047。", fontsize=10, color=MUTED, linespacing=1.5)
    save_chart(fig, "architecture-budget", plt)


def representation_chart(plt, data):
    from matplotlib.patches import Patch

    lookup = {(r["condition"], r["representation"]): r for r in data["v048"]["aggregates"]}
    fig, axs = plt.subplots(1, 2, figsize=(12.5, 6.3), gridspec_kw={"width_ratios": [1, 1.3]})
    fig.subplots_adjust(top=.76, bottom=.23, left=.08, right=.94, wspace=.28)
    fig.suptitle("v048｜输入表示 × S1 / P4", fontsize=19, x=.035, ha="left", y=.98)
    fig.text(.035, .91, "每配置仅 n=2（LA / LB）；500k团队预算相同；机制抽样，不是独立新任务确认。", fontsize=12, color=ORANGE)
    for ax in axs:
        style_axis(ax)
        ax.set_yticks([0, 1], ["S1 单人", "P4 四阶段"])
        ax.set_ylim(1.5, -.5)
    axs[0].set_xlim(0, 2.55)
    axs[0].set_xticks([0, 1, 2])
    axs[0].set_xlabel("完整成功数 / 2")
    axs[1].set_xlim(0, 515)
    axs[1].set_xticks([0, 100, 200, 300, 400, 500])
    axs[1].set_xlabel("全槽平均完整 token（千）")
    for representation, offset, color in (("Gamma0", -.17, BLUE), ("Gamma1", .17, TEAL)):
        for i, condition in enumerate(("S1", "P4")):
            r = lookup[(condition, representation)]
            values = [r["R"]["known_sum"] if r["R"]["mean"] is not None else None,
                      None if r["mean_complete_actual_tokens"] is None else r["mean_complete_actual_tokens"]/1000]
            for col, (ax, value) in enumerate(zip(axs, values)):
                if value is None:
                    ax.text(.1 if col == 0 else 6, i+offset, "未知", va="center")
                    continue
                ax.barh(i+offset, value, height=.27, color=color)
                if value == 0:
                    ax.plot(0, i+offset, marker="|", color=color, markersize=13, markeredgewidth=2, clip_on=False)
                label = f"{value}/2" if col == 0 else f"{value:,.1f}k"
                ax.text(value+(.07 if col == 0 else 6), i+offset, label, va="center", fontsize=12)
    fig.legend(handles=[Patch(color=BLUE, label="Γ0 原表示"), Patch(color=TEAL, label="Γ1 严格同值引用")],
               loc="upper right", bbox_to_anchor=(.95, .87), frameon=False, ncol=2)
    fig.text(.035, .055, "费用包含失败。P4 / Γ0较低费用伴随未交付的容量中断，不表示同等产出下更高效率。\nΓ1下S1与P4同为2/2成功，P4完整费用约为S1的2.9935倍。来源：comparison-data.json / v048。", fontsize=10, color=MUTED, linespacing=1.5)
    save_chart(fig, "representation-comparison", plt)


def make_charts(font, selected=None):
    plt = chart_environment(font)
    data, historical = read_json("comparison-data.json"), read_json("historical-context.json")
    actions = {
        "strategy-flows": lambda: flow_chart(plt),
        "personnel-comparison": lambda: personnel_chart(plt, data, historical),
        "architecture-budget": lambda: architecture_chart(plt, data),
        "representation-comparison": lambda: representation_chart(plt, data),
    }
    for name in selected or actions:
        actions[name]()


def absolute_source_link(href, markdown_path, repository):
    parsed = urlsplit(href)
    if parsed.scheme or not parsed.path:
        return href
    local = (markdown_path.parent / parsed.path).resolve()
    repo_root = ASSETS.parents[2]
    try:
        relative = local.relative_to(repo_root)
    except ValueError:
        return href
    url = repository.rstrip("/") + "/" + quote(relative.as_posix(), safe="/")
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parsed.query, parsed.fragment))


def markdown_tree(markdown_path):
    import markdown

    source = markdown_path.read_text(encoding="utf-8")
    if re.search(r"\{\{[A-Z_]+\}\}", source):
        raise ValueError("Report still contains template placeholders; refusing final rendering")
    converter = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"],
                                  extension_configs={"toc": {"toc_depth": "2-3"}})
    rendered = converter.convert(source)
    return source, converter, ET.fromstring(f"<article>{rendered}</article>")


def make_html(markdown_path, tree, converter, repository):
    import copy

    tree = copy.deepcopy(tree)
    for elem in tree.iter():
        if elem.tag == "img":
            source = (markdown_path.parent / elem.attrib["src"]).resolve()
            encoded = base64.b64encode(source.read_bytes()).decode("ascii")
            mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            elem.set("src", f"data:{mime};base64,{encoded}")
            elem.set("loading", "lazy")
        if elem.tag == "a" and elem.get("href"):
            elem.set("href", absolute_source_link(elem.attrib["href"], markdown_path, repository))
    title = "".join(tree.find("h1").itertext()) if tree.find("h1") is not None else markdown_path.stem
    css = """
    :root{color-scheme:light;--ink:#243447;--accent:#256a91;--border:#dce4ea}
    *{box-sizing:border-box}body{margin:0;background:#f3f6f8;color:var(--ink);font:16px/1.85 system-ui,-apple-system,"Noto Sans CJK SC","Microsoft YaHei","PingFang SC",sans-serif}
    .layout{max-width:1510px;margin:auto;display:grid;grid-template-columns:270px minmax(0,1fr);gap:30px;padding:30px}
    nav{align-self:start;position:sticky;top:20px;max-height:94vh;overflow:auto;font-size:13px;line-height:1.65;padding:16px;background:white;border-radius:9px}
    nav strong{display:block;color:var(--accent);font-size:17px;margin-bottom:10px}nav ul{padding-left:17px}nav li{margin:.4em 0}nav a{text-decoration:none}
    article{min-width:0;background:white;padding:40px 46px;box-shadow:0 1px 5px #24344714;border-radius:10px}
    h1{font-size:32px;line-height:1.4;margin:0 0 28px}h2{font-size:25px;line-height:1.45;margin-top:50px;border-top:2px solid var(--border);padding-top:20px;scroll-margin-top:20px}
    h3{font-size:20px;margin-top:30px;scroll-margin-top:20px}p{margin:1em 0}a{color:var(--accent);overflow-wrap:anywhere}
    strong{color:#1e3548}img{display:block;max-width:100%;height:auto;margin:24px auto;border:1px solid #edf0f3;border-radius:5px}
    table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.65;margin:22px 0;display:block;overflow-x:auto}
    th,td{padding:9px 11px;text-align:left;vertical-align:top;border:1px solid var(--border);overflow-wrap:anywhere;min-width:60px}
    th{background:#e8f0f6;color:#193d59;font-weight:650}tr:nth-child(even) td{background:#f8fafc}
    code{font-size:.88em;background:#edf3f6;padding:1px 4px;border-radius:3px;overflow-wrap:anywhere}pre{white-space:pre-wrap;background:#edf3f6;padding:15px;overflow-wrap:anywhere}
    blockquote{margin:20px 0;padding:8px 18px;border-left:4px solid #c67532;background:#fff8eb}li{margin:.4em 0}
    footer{color:#657789;font-size:12px;text-align:center;padding:20px}article>.toc{display:none}
    @media(max-width:1000px){.layout{display:block;padding:12px}nav{position:static;max-height:300px;margin-bottom:20px}article{padding:22px}h1{font-size:26px}}
    @media print{body{background:white}.layout{display:block;padding:0}nav{display:none}article{box-shadow:none;padding:0}table{display:table;font-size:9pt}tr,img{break-inside:avoid}thead{display:table-header-group}h2,h3{break-after:avoid}a{color:inherit}}
    """
    document = ("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
                "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                f"<title>{html.escape(title)}</title><style>{css}</style></head><body>"
                f"<div class=\"layout\"><nav aria-label=\"目录\"><strong>目录</strong>{converter.toc}</nav>"
                f"{ET.tostring(tree, encoding='unicode', method='html')}</div>"
                "<footer>图像已内嵌，可离线阅读；来源链接指向报告分支的公开文件。</footer></body></html>")
    output = markdown_path.with_suffix(".html")
    output.write_text(document, encoding="utf-8")
    print(f"created {output}")


def make_pdf(markdown_path, tree, font, repository):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        BaseDocTemplate, CondPageBreak, Frame, HRFlowable, Image, KeepTogether, LongTable,
        PageBreak, PageTemplate, Paragraph, Spacer, TableStyle,
    )
    from reportlab.platypus.tableofcontents import TableOfContents

    pdfmetrics.registerFont(TTFont("ReportCJK", str(font)))
    pdfmetrics.registerFontFamily("ReportCJK", normal="ReportCJK", bold="ReportCJK",
                                  italic="ReportCJK", boldItalic="ReportCJK")
    latin_dir = Path("/usr/share/fonts/truetype/dejavu")
    for name, filename in (("ReportLatin", "DejaVuSans.ttf"),
                           ("ReportLatinBold", "DejaVuSans-Bold.ttf"),
                           ("ReportLatinItalic", "DejaVuSans-Oblique.ttf"),
                           ("ReportLatinBoldItalic", "DejaVuSans-BoldOblique.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(latin_dir / filename)))
    pdfmetrics.registerFontFamily("ReportLatin", normal="ReportLatin", bold="ReportLatinBold",
                                  italic="ReportLatinItalic", boldItalic="ReportLatinBoldItalic")
    latin_chars = pdfmetrics.getFont("ReportLatin").face.charWidths

    def unicode_text(value):
        """Embed real glyphs for both scripts; Droid fallback omits Latin."""
        runs = []
        for char in value:
            face = "ReportLatin" if ord(char) in latin_chars else "ReportCJK"
            if runs and runs[-1][0] == face:
                runs[-1][1] += char
            else:
                runs.append([face, char])
        return "".join(html.escape(text) if face == "ReportLatin" else
                       f'<font name="ReportCJK">{html.escape(text)}</font>'
                       for face, text in runs)

    width, height = A4
    margin = 17*mm
    content_width = width-2*margin
    body = ParagraphStyle("Body", fontName="ReportLatin", fontSize=9, leading=14.2,
                          textColor=colors.HexColor(INK), spaceAfter=7, wordWrap="CJK",
                          splitLongWords=1, allowWidows=0, allowOrphans=0)
    styles = {
        "body": body,
        "title": ParagraphStyle("Title", parent=body, fontSize=22, leading=31, spaceAfter=20),
        "h2": ParagraphStyle("Heading2", parent=body, fontSize=15, leading=22, spaceBefore=18,
                             spaceAfter=10, keepWithNext=True, textColor=colors.HexColor(BLUE)),
        "h3": ParagraphStyle("Heading3", parent=body, fontSize=11.5, leading=18, spaceBefore=11,
                             spaceAfter=6, keepWithNext=True),
        "cell": ParagraphStyle("Cell", parent=body, fontSize=8.5, leading=12.5, spaceAfter=0,
                               allowWidows=1, allowOrphans=1),
        "cell_header": ParagraphStyle("CellHeader", parent=body, fontSize=8.5, leading=12.5,
                                      spaceAfter=0, textColor=colors.HexColor("#193d59")),
        "caption": ParagraphStyle("Caption", parent=body, fontSize=8, leading=12,
                                  textColor=colors.HexColor(MUTED), alignment=TA_CENTER, spaceAfter=12),
        "code": ParagraphStyle("Code", parent=body, fontSize=7, leading=10,
                               backColor=colors.HexColor(LIGHT), borderPadding=6),
    }

    def rich(elem):
        parts = [unicode_text(elem.text or "")]
        for child in elem:
            inner = rich(child)
            if child.tag in ("strong", "b"):
                parts.append(f"<b>{inner}</b>")
            elif child.tag in ("em", "i"):
                parts.append(f"<i>{inner}</i>")
            elif child.tag == "code":
                parts.append(f'<font color="#265879">{inner}</font>')
            elif child.tag == "a" and child.get("href"):
                href = absolute_source_link(child.get("href"), markdown_path, repository)
                parts.append(f'<link href="{html.escape(href, quote=True)}" color="{BLUE}">{inner}</link>')
            elif child.tag == "br":
                parts.append("<br/>")
            elif child.tag != "img":
                parts.append(inner)
            parts.append(unicode_text(child.tail or ""))
        return "".join(parts)

    class ReportDocument(BaseDocTemplate):
        def afterFlowable(self, flowable):
            info = getattr(flowable, "heading_info", None)
            if info is not None:
                level, title, anchor = info
                self.canv.bookmarkPage(anchor)
                self.canv.addOutlineEntry(title, anchor, level=level, closed=False)
                if level == 0:
                    self.notify("TOCEntry", (level, unicode_text(title), self.page, anchor))

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFont("ReportCJK", 7)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(margin, height-11*mm, "人数与组织策略比较｜")
        canvas.setFont("ReportLatin", 7)
        canvas.drawString(margin+70, height-11*mm, "2026-10-15")
        canvas.setStrokeColor(colors.HexColor("#dce4ea"))
        canvas.line(margin, height-13*mm, width-margin, height-13*mm)
        canvas.drawRightString(width-margin, 10*mm, str(doc.page))
        canvas.restoreState()

    output = markdown_path.with_suffix(".pdf")
    doc = ReportDocument(str(output), pagesize=A4, leftMargin=margin, rightMargin=margin,
                         topMargin=20*mm, bottomMargin=17*mm, title="人数与组织策略比较",
                         author="ProWorkSim", pageCompression=1)
    frame = Frame(margin, 17*mm, content_width, height-37*mm, leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id="report", frames=[frame], onPage=page))
    story = []

    def image_flow(elem):
        path = (markdown_path.parent / elem.get("src")).resolve()
        picture = Image(str(path))
        ratio = min(content_width/picture.imageWidth, (height-60*mm)/picture.imageHeight)
        picture.drawWidth = picture.imageWidth*ratio
        picture.drawHeight = picture.imageHeight*ratio
        picture.hAlign = "CENTER"
        caption = Paragraph(unicode_text(elem.get("alt", "")), styles["caption"])
        return KeepTogether([picture, Spacer(1, 4), caption])

    def table_flow(elem):
        rows = elem.findall(".//tr")
        raw = [list(row) for row in rows]
        count = max(len(row) for row in raw)
        # Display-width estimates retain usable prose columns while containing
        # identifiers and long source links through CJK/word wrapping.
        estimates = []
        for col in range(count):
            lengths = []
            for row in raw:
                text = "".join(row[col].itertext()) if col < len(row) else ""
                lengths.append(sum(1 if ord(c) > 255 else .55 for c in text))
            estimates.append(max(3.4, min(25, max(lengths, default=4))))
        minimum = 31 if count >= 8 else 39
        available = content_width-minimum*count
        if available <= 0:
            widths = [content_width/count]*count
        else:
            total = sum(estimates)
            widths = [minimum+available*x/total for x in estimates]
        converted = []
        for i, row in enumerate(raw):
            converted.append([Paragraph(rich(cell), styles["cell_header"] if i == 0 else styles["cell"])
                              for cell in row] + [""]*(count-len(row)))
        table = LongTable(converted, colWidths=widths, repeatRows=1, hAlign="LEFT",
                          splitByRow=1, splitInRow=1, spaceBefore=6, spaceAfter=12)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0f6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#dce4ea")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def convert(elem, indent=0):
        tag = elem.tag
        if tag == "h1":
            return [Paragraph(rich(elem), styles["title"])]
        if tag in ("h2", "h3", "h4"):
            level = 0 if tag == "h2" else 1
            paragraph = Paragraph(rich(elem), styles["h2" if level == 0 else "h3"])
            paragraph.heading_info = (level, "".join(elem.itertext()), elem.get("id", f"section-{len(story)}"))
            return [paragraph]
        if tag == "p":
            pictures = elem.findall("img")
            if pictures:
                return [image_flow(picture) for picture in pictures]
            return [Paragraph(rich(elem), body)]
        if tag == "table":
            return [table_flow(elem)]
        if tag in ("ul", "ol"):
            items = []
            for i, child in enumerate(elem):
                prefix = f"{i+1}. " if tag == "ol" else "• "
                list_style = ParagraphStyle(f"List{indent}", parent=body, leftIndent=12*(indent+1),
                                            firstLineIndent=-10, spaceAfter=5)
                if child.find("p") is not None:
                    for j, item in enumerate(child):
                        if item.tag == "p":
                            items.append(Paragraph((prefix if j == 0 else "")+rich(item), list_style))
                        else:
                            items.extend(convert(item, indent+1))
                else:
                    items.append(Paragraph(prefix+rich(child), list_style))
            return items
        if tag == "blockquote":
            quote_style = ParagraphStyle("Quote", parent=body, leftIndent=12, rightIndent=8,
                                         backColor=colors.HexColor("#fff8eb"), borderPadding=6)
            return [Paragraph(rich(child), quote_style) for child in elem]
        if tag == "pre":
            lines = "".join(elem.itertext()).splitlines()
            wrapped = "<br/>".join(unicode_text(part) for line in lines
                                  for part in (textwrap.wrap(line, width=95, replace_whitespace=False) or [""]))
            return [Paragraph(wrapped, styles["code"])]
        if tag == "hr":
            return [HRFlowable(width="100%", color=colors.HexColor("#dce4ea")), Spacer(1, 10)]
        if tag == "div" and elem.get("class") == "toc":
            return []
        return [flow for child in elem for flow in convert(child, indent)]

    children = list(tree)
    if children and children[0].tag == "h1":
        story.extend(convert(children.pop(0)))
    story.append(Paragraph(unicode_text("目录"), styles["h2"]))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC0", parent=body, fontSize=9, leading=15, spaceBefore=5,
                       leftIndent=0, firstLineIndent=0),
        ParagraphStyle("TOC1", parent=body, fontSize=8, leading=13, spaceBefore=2,
                       leftIndent=12, firstLineIndent=0),
    ]
    toc.dotsMinLevel = 0
    story.extend([toc, PageBreak()])
    for index, elem in enumerate(children):
        flows = convert(elem)
        # Keep a heading with the start of a long table, not the entire table.
        if (elem.tag in ("h2", "h3", "h4") and index+1 < len(children)
                and children[index+1].tag == "table"):
            story.append(CondPageBreak(105))
            flows[0].keepWithNext = False
        story.extend(flows)
    doc.multiBuild(story)
    print(f"created {output} ({doc.page} pages)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["charts", "render", "all"])
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MD)
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT)
    parser.add_argument("--repository-url", default=DEFAULT_REPOSITORY)
    parser.add_argument("--chart", action="append", choices=["strategy-flows", "personnel-comparison",
                                                            "architecture-budget", "representation-comparison"])
    args = parser.parse_args()
    if args.mode in ("charts", "all"):
        make_charts(args.font, args.chart)
    if args.mode in ("render", "all"):
        markdown_path = args.markdown.resolve()
        _, converter, tree = markdown_tree(markdown_path)
        make_html(markdown_path, tree, converter, args.repository_url)
        make_pdf(markdown_path, tree, args.font, args.repository_url)


if __name__ == "__main__":
    main()

"""Draw docs/fig1_architecture.png and docs/fig3_search_pipeline.png.

Source of the two README figures. Every number and name below was checked against the code and data
at the commit that last changed this file; if retrieval.py, the graph or the tools change, edit the
text here and re-run:

    python docs/figures/make_figures.py

Needs matplotlib only. Output goes to docs/.

The PNGs in the repo were drawn with matplotlib 3.11.2 on macOS. Other versions set text slightly wider or
narrower (3.9.2: about 1.5% wider), so re-running with another version changes every line of both figures.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent
# Thai text needs a font whose vowel and tone marks stack correctly without a shaping engine. On macOS
# "Arial Unicode MS" does in matplotlib; Thonburi, Tahoma, Sarabun and Noto Sans Thai do not.
plt.rcParams["font.family"] = ["Arial", "Arial Unicode MS", "DejaVu Sans"]

INK, GREY, LINE = "#1a1a1a", "#555555", "#c9cabd"
PANEL, BLUE_FILL, BLUE_EDGE = "#ececea", "#dde6f0", "#2f7de1"


def canvas(w, h, title):
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, w); ax.set_ylim(h, 0); ax.axis("off")
    ax.text(64, 52, title, fontsize=14.5, fontweight="bold", color=INK, va="center")
    return fig, ax


def box(ax, x, y, w, h, title, lines, fill="white", edge=LINE, lw=1.4, center=False, title_size=12.5, mono=()):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=12",
                                fc=fill, ec=edge, lw=lw, zorder=2))
    tx, ha = (x + w / 2, "center") if center else (x + 22, "left")
    ax.text(tx, y + 34, title, fontsize=title_size, fontweight="bold", color=INK, ha=ha, va="center", zorder=3)
    for i, line in enumerate(lines):
        text, colour = (line, INK) if isinstance(line, str) else line
        family = "DejaVu Sans Mono" if i in mono else None
        ax.text(tx, y + 63 + 28.5 * i, text, fontsize=9.6 if i in mono else 10.6, color=colour, ha=ha,
                va="center", zorder=3, family=family)


def arrow(ax, pts, label=None, label_xy=None):
    xs, ys = zip(*pts)
    ax.plot(xs[:-1] + (xs[-1],), ys, color=LINE, lw=1.4, zorder=1, solid_capstyle="round")
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), zorder=1,
                arrowprops=dict(arrowstyle="-|>", color=LINE, lw=1.4, mutation_scale=13))
    if label:
        lx, ly = label_xy
        ax.text(lx, ly, label, fontsize=10.2, color=GREY, va="center")


def fig1():
    W, H, D = 1340, 1126, 86
    fig, ax = canvas(W, H, "The agent calls 5 MCP tools that wrap a knowledge graph and a vector index")
    box(ax, 64, 100, 1216, 100, "Agent",
        [("your own loop (labs/lab8: THINK \u2192 TOOL_USE \u2192 END_TURN), Claude Desktop, LangFlow \u2014 any MCP client."
          "  The agent\u2019s own LLM writes the answer.", GREY)])
    arrow(ax, [(672, 200), (672, 262)], "MCP streamable-http \u00b7 tools/list \u2192 tools/call", (694, 231))
    box(ax, 64, 262, 1216, 156 + D, "MCP Server \u00b7 FastMCP \u00b7 port 8100 \u00b7 5 tools, each reaches the engine differently",
        ["search_pdpa \u2192 keyword LLM + vector index (profiles, chunks) + graph BFS \u2014 the pipeline of the search figure",
         "get_related_sections \u2192 knowledge graph only: edges in and out of one node",
         "get_penalty \u2192 knowledge graph only: BFS from a section to Penalty nodes",
         "get_section_text \u2192 statute text by section id, read from the Markdown \u00b7 get_pdpa_summary \u2192 counts by node and edge type",
         ("only search_pdpa uses the LLM and vector search; the other four read the graph or statute text directly", GREY),
         ("stateless_http=True \u00b7 each tool\u2019s docstring is the description the agent reads before choosing a tool", GREY)])
    arrow(ax, [(672, 418 + D), (672, 474 + D)], "search \u00b7 traverse \u00b7 read section text", (694, 447 + D))
    box(ax, 64, 474 + D, 1216, 330, "PDPA LightRAG Engine \u00b7 lightrag/", [], fill=PANEL)
    ax.text(446, 508 + D, "this repo\u2019s own code, following the LightRAG approach (not the LightRAG library)",
            fontsize=10.2, color=GREY, va="center", zorder=3)
    box(ax, 92, 545 + D, 566, 186, "Knowledge Graph \u00b7 NetworkX (in-memory)",
        ["190 nodes \u00b7 382 edges",
         "11 node types \u00b7 26 edge types",
         "search_pdpa: BFS 2 hops from \u2264 3 seeds, both directions",
         "get_penalty: reports penalties within 2 hops"], fill=BLUE_FILL, edge=BLUE_EDGE, lw=2.2)
    box(ax, 686, 545 + D, 566, 186, "Vector Index \u00b7 BGE-M3 + Qdrant \u00b7 used by search_pdpa only",
        ["dense 1024-d + sparse (lexical weights)",
         "pdpa_profiles 572 = 190 node + 382 edge profiles",
         "pdpa_chunks 96 = full text, one per section",
         "hybrid search \u2192 RRF fusion (k = 60)"], title_size=11.6)
    ax.text(86, 770 + D, "LLM (OpenRouter \u00b7 LLM_MODEL) only for keyword extraction in search_pdpa \u00b7 "
            "Qdrant 1.20.0 runs as a separate container", fontsize=10.4, color=GREY, va="center", zorder=3)
    arrow(ax, [(672, 804 + D), (672, 862 + D)],
          "loaded at startup only \u00b7 no hot-reload \u00b7 both collections rebuilt at every start", (694, 834 + D))
    box(ax, 64, 862 + D, 1216, 128, "Data layer \u00b7 ./data (folder mounted into the container)",
        ["pdpa_full_text_v2.md \u00b7 96 sections (H1 Act \u2192 H2 Chapter \u2192 H3 Part \u2192 H4 Section)",
         "pdpa_knowledge_graph.json \u00b7 190 nodes / 382 edges (generated by scripts/build_graph.py)"])
    fig.savefig(OUT / "fig1_architecture.png", facecolor="white"); plt.close(fig)


def fig3():
    # Thai is used wherever the running system uses Thai: the question, the keyword kinds named in the
    # prompt, the statute text in a graph line, and the three context headers (copied from retrieval.py).
    W, H = 1340, 1560
    fig, ax = canvas(W, H, "search_pdpa: one question, six steps, graph + statute text in one context")
    ax.text(64, 78, "the only one of the 5 MCP tools that uses the LLM and vector search — the other four look up the graph or the statute text directly",
            fontsize=10.2, color=GREY, va="center")
    box(ax, 268, 104, 808, 100, "User question (คำถามของผู้ใช้)",
        [("“บริษัทเก็บลายนิ้วมือพนักงานเพื่อลงเวลาทำงาน ต้องขอความยินยอมไหม”", GREY)], center=True)
    arrow(ax, [(672, 204), (672, 240)])
    box(ax, 208, 240, 928, 186, "1  LLM keyword extraction (LLM_MODEL via OpenRouter) — the only LLM call",
        ["low-level ≤ 8 คำ: คำเฉพาะเจาะจง เช่น ชื่อหน่วยงาน สิทธิเฉพาะ หน้าที่เฉพาะ บทลงโทษ",
         "high-level ≤ 6 คำ: คำกว้าง เช่น หลักการ หมวดหมู่ แนวคิด ขั้นตอน",
         "ใช้ถ้อยคำแบบที่ตัวบทใช้ เช่น “ขายข้อมูล” → “เปิดเผยข้อมูลส่วนบุคคล”",
         ("section numbers (เลขมาตรา) only if the question names them or the model is sure (≤ 2) · each set is joined into one query string", GREY)])
    arrow(ax, [(672, 426), (672, 454), (346, 454), (346, 482)])
    arrow(ax, [(672, 454), (996, 454), (996, 482)])
    box(ax, 64, 482, 566, 186, "2  Profile search · pdpa_profiles (572)",
        ["round A: high-level query → top 5 (top_k)",
         "round B: low-level query → top 3",
         "each round: dense + sparse → RRF (k = 60)",
         ("merged list: A first, then new ones from B (≤ 8)", GREY)])
    box(ax, 714, 482, 566, 186, "5  Chunk search · pdpa_chunks (96)",
        ["low + high keywords combined into one query",
         "dense + sparse → RRF (k = 60)",
         "full text of ≤ 5 sections (ตัวบทเต็มของมาตรา)",
         ("independent of steps 3–4: does not use the graph", GREY)])
    arrow(ax, [(346, 668), (346, 712)], "profile ids (node or edge profiles)", (366, 690))
    box(ax, 64, 712, 566, 158, "3  Pick seeds — no LLM",
        ["walk the merged list in order",
         "skip edge profiles (id contains “--”) and the Act node",
         "first 3 node ids left = seeds, e.g. def_biometric"])
    arrow(ax, [(346, 870), (346, 914)], "≤ 3 seed nodes", (366, 892))
    box(ax, 64, 914, 566, 272, "4  Multi-hop BFS · NetworkX",
        ["2 hops from each seed, both edge directions",
         "keep ≤ 15 lines, quota shared round-robin across seeds",
         "order: penalty and obligation edges, then cross-references",
         "and exemptions, then other edges; structural edges last",
         ("penalty question: penalty sections citing the node go first", GREY),
         "[hop1] def_biometric ←DEFINES— sec_26: #### มาตรา ๒๖ ห้ามมิให้…",
         "[hop2] sec_26 —GRANTS_EXEMPTION→ sec26_ex1: …"],
        fill=BLUE_FILL, edge=BLUE_EDGE, lw=2.2, mono=(6,))
    arrow(ax, [(346, 1186), (346, 1216), (530, 1216), (530, 1246)])
    arrow(ax, [(996, 668), (996, 1216), (814, 1216), (814, 1246)], "full section text", (1014, 940))
    box(ax, 248, 1246, 848, 158, "6  Build hybrid context — the headers are Thai in the real output",
        ["## ความรู้จาก Knowledge Graph (PDPA) — VALUE of ≤ 8 profiles (step 2)",
         "### ข้อมูลเชื่อมโยง (multi-hop graph): — ≤ 15 lines (step 4)",
         "## เนื้อหาต้นฉบับ PDPA (Original Text) — ≤ 5 full sections (step 5)"])
    arrow(ax, [(672, 1404), (672, 1436)])
    box(ax, 318, 1436, 708, 84, "JSON back to the agent",
        [("the server retrieves · the agent’s LLM reads and answers (lab8 answers in Thai)", GREY)], center=True)
    fig.savefig(OUT / "fig3_search_pipeline.png", facecolor="white"); plt.close(fig)


if __name__ == "__main__":
    fig1(); fig3()
    print("wrote", OUT / "fig1_architecture.png", "and", OUT / "fig3_search_pipeline.png")

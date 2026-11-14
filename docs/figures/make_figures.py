"""Draw docs/fig1_architecture.png and docs/fig3_search_pipeline.png.

Source of the two README figures. Every number and name below was checked against the code and data
at the commit that last changed this file; if retrieval.py, the graph or the tools change, edit the
text here and re-run:

    python docs/figures/make_figures.py

Needs matplotlib only. Output goes to docs/.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent
plt.rcParams["font.family"] = ["Arial", "DejaVu Sans"]

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
    W, H = 1340, 1040
    fig, ax = canvas(W, H, "The agent calls 5 MCP tools that wrap a knowledge graph and a vector index")
    box(ax, 64, 100, 1216, 100, "Agent",
        [("your own loop (labs/lab8: THINK → TOOL_USE → OBSERVE), Claude Desktop, LangFlow — any MCP client."
          "  The agent’s own LLM writes the answer.", GREY)])
    arrow(ax, [(672, 200), (672, 262)], "MCP streamable-http · tools/list → tools/call", (694, 231))
    box(ax, 64, 262, 1216, 156, "MCP Server · FastMCP · port 8100",
        ["5 tools: search_pdpa · get_related_sections · get_penalty · get_section_text · get_pdpa_summary",
         ("stateless_http=True · each tool’s docstring is the description the agent reads before choosing a tool", GREY),
         ("only search_pdpa calls an LLM · the server returns context and never writes the answer", GREY)])
    arrow(ax, [(672, 418), (672, 474)], "search · traverse · read section text", (694, 447))
    box(ax, 64, 474, 1216, 330, "PDPA LightRAG Engine · lightrag/", [], fill=PANEL)
    ax.text(446, 508, "this repo’s own code, following the LightRAG approach (not the LightRAG library)",
            fontsize=10.2, color=GREY, va="center", zorder=3)
    box(ax, 92, 545, 566, 186, "Knowledge Graph · NetworkX (in-memory)",
        ["190 nodes · 380 edges",
         "11 node types · 26 edge types",
         "search_pdpa: BFS 2 hops from ≤ 3 seeds, both directions",
         "get_penalty: reports penalties within 2 hops"], fill=BLUE_FILL, edge=BLUE_EDGE, lw=2.2)
    box(ax, 686, 545, 566, 186, "Vector Index · BGE-M3 + Qdrant",
        ["dense 1024-d + sparse (lexical weights)",
         "pdpa_profiles 570 = 190 node + 380 edge profiles",
         "pdpa_chunks 96 = full text, one per section",
         "hybrid search → RRF fusion (k = 60)"])
    ax.text(86, 770, "LLM (OpenRouter · gpt-oss-120b) only for keyword extraction in search_pdpa · "
            "Qdrant 1.20.0 runs as a separate container", fontsize=10.4, color=GREY, va="center", zorder=3)
    arrow(ax, [(672, 804), (672, 862)], "loaded at startup only · no hot-reload · both collections rebuilt at every start",
          (694, 834))
    box(ax, 64, 862, 1216, 128, "Data layer · ./data (folder mounted into the container)",
        ["pdpa_full_text_v2.md · 96 sections (H1 Act → H2 Chapter → H3 Part → H4 Section)",
         "pdpa_knowledge_graph.json · 190 nodes / 380 edges (pre-built by a rule-based parser)"])
    fig.savefig(OUT / "fig1_architecture.png", facecolor="white"); plt.close(fig)


def fig3():
    W, H = 1340, 1500
    fig, ax = canvas(W, H, "search_pdpa: one question, six steps, graph + statute text in one context")
    box(ax, 318, 96, 708, 100, "User question",
        [("“Can a company collect employees’ fingerprints for timekeeping? Is consent required?”", GREY)],
        center=True)
    arrow(ax, [(672, 196), (672, 232)])
    box(ax, 208, 232, 928, 158, "1  LLM keyword extraction (gpt-oss-120b via OpenRouter) — the only LLM call",
        ["low-level ≤ 8: specific terms in the statute’s wording — rights, duties, penalties, scope",
         "high-level ≤ 6: principles, categories, concepts",
         ("section numbers only if the question names them or the model is sure (≤ 2) · each set is joined into one query string", GREY)])
    arrow(ax, [(672, 390), (672, 418), (346, 418), (346, 446)])
    arrow(ax, [(672, 418), (996, 418), (996, 446)])
    box(ax, 64, 446, 566, 186, "2  Profile search · pdpa_profiles (570)",
        ["round A: high-level query → top 5 (top_k)",
         "round B: low-level query → top 3",
         "each round: dense + sparse → RRF (k = 60)",
         ("merged list: A first, then new ones from B (≤ 8)", GREY)])
    box(ax, 714, 446, 566, 186, "5  Chunk search · pdpa_chunks (96)",
        ["low + high keywords combined into one query",
         "dense + sparse → RRF (k = 60)",
         "full text of ≤ 5 sections",
         ("independent of steps 3–4: does not use the graph", GREY)])
    arrow(ax, [(346, 632), (346, 676)], "profile ids (node or edge profiles)", (366, 654))
    box(ax, 64, 676, 566, 158, "3  Pick seeds — no LLM",
        ["walk the merged list in order",
         "skip edge profiles (id contains “--”) and the Act node",
         "first 3 node ids left = seeds, e.g. def_biometric"])
    arrow(ax, [(346, 834), (346, 878)], "≤ 3 seed nodes", (366, 856))
    box(ax, 64, 878, 566, 272, "4  Multi-hop BFS · NetworkX",
        ["2 hops from each seed, both edge directions",
         "keep ≤ 15 lines, quota shared round-robin across seeds",
         "order: penalty and obligation edges, then cross-references",
         "and exemptions, then other edges; structural edges last",
         ("penalty question: penalty sections citing the node go first", GREY),
         "[hop1] def_biometric ←DEFINES— sec_26: …",
         "[hop2] sec_26 —GRANTS_EXEMPTION→ sec26_ex1: …"],
        fill=BLUE_FILL, edge=BLUE_EDGE, lw=2.2, mono=(5, 6))
    arrow(ax, [(346, 1150), (346, 1180), (530, 1180), (530, 1210)])
    arrow(ax, [(996, 632), (996, 1180), (814, 1180), (814, 1210)], "full section text", (1014, 900))
    box(ax, 248, 1210, 848, 158, "6  Build hybrid context",
        ["## Knowledge graph — VALUE of ≤ 8 profiles (step 2)",
         "### Linked facts (multi-hop) — ≤ 15 lines (step 4)",
         "## Original PDPA text — ≤ 5 full sections (step 5)"])
    arrow(ax, [(672, 1368), (672, 1400)])
    box(ax, 318, 1400, 708, 84, "JSON back to the agent",
        [("the server retrieves · the agent’s LLM reads and answers", GREY)], center=True)
    fig.savefig(OUT / "fig3_search_pipeline.png", facecolor="white"); plt.close(fig)


if __name__ == "__main__":
    fig1(); fig3()
    print("wrote", OUT / "fig1_architecture.png", "and", OUT / "fig3_search_pipeline.png")

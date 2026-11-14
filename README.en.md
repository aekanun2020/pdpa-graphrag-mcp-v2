# PDPA GraphRAG + MCP (teaching version, v2)

[ภาษาไทย](README.md)

A GraphRAG agent over Thailand's Personal Data Protection Act (PDPA, B.E. 2562 / 2019).
The 96 sections of the statute become a 190-node / 380-edge knowledge graph plus a dense + sparse
vector index, exposed as five MCP tools that any agent can call. Everything runs locally with
Docker.

This repository is the version used in the GraphRAG course. It continues
[aekanun2020/pdpa-graphrag-mcp](https://github.com/aekanun2020/pdpa-graphrag-mcp), the companion code
for the article series **"Why Vector RAG Answers Only Half of a Legal Question"**, which is now
archived. The original shows the system exactly as the articles describe it; this one fixes the
defects found in a pre-course review (see [What changed from the original](#what-changed-from-the-original)),
so its search results differ from the runs shown in the articles.

Statutes do not repeat themselves, they *point*: a prohibition lives in one section, its exceptions
in sub-clauses, and the penalty chapters later in a sentence that only says "whoever violates
Section 26". Vector search finds the first half; the graph walk finds the second.

The example is Thai law, but the structure is the same for GDPR, HIPAA, the CCPA or Japan's APPI,
and the embedding model is multilingual.

## What changed from the original

| Area | Original | This version |
|---|---|---|
| Fresh image build | Installs mcp 2.x, which removed `FastMCP`; the container crashes at import and restarts in a loop | `mcp[cli]` pinned below 2 |
| `get_section_text` | Read the graph node's `text`, cut at 3,000 characters: Section 26 lost its biometric-data and criminal-record paragraphs | Reads the full section from the Markdown |
| Statute Markdown | 801 split sara-am from PDF extraction ("ก าหนด", "จ าคุก") | Repaired ("กำหนด", "จำคุก"); graph node text is repaired at load time |
| Node profiles | Built from `description` only, which 33 of 190 nodes have; a Section profile held just its id and relation names | Also read `name_th`, `term_th`, `definition`, `title_th` and `text` |
| Section embedding | `max_length=512`; 7 sections are longer (Section 26 is 810 tokens) and lost their tail | `CHUNK_MAX_LENGTH`, default 1024 |
| RRF constant | Not set, so Qdrant's default k = 2 | `RRF_K`, default 60 |
| Result order | RRF scores tie often and Qdrant does not order ties, so the same keywords gave different seeds per call | Fused candidates are sorted by (score, id); the same keywords give the same context |
| Seed selection | Took the top 3 profiles, then dropped edge profiles: possibly no seed at all | Drops edge profiles and the Act node (`PDPA_2562`) first, then takes 3 |
| `build_graph.py` | Truncated section text at 3,000 characters | No truncation |

Not changed: `get_penalty` and the shipped graph (see Known limitations), the graph's `metadata`
counts, and the 15-node cap on graph expansion.

## What's inside

```
mcp_server_rag.py        FastMCP server (streamable-http, port 8100) exposing 5 tools
lightrag/                retrieval engine: Markdown chunker, NetworkX graph, BGE-M3 + Qdrant index, hybrid retrieval
data/
  pdpa_full_text_v2.md   the statute as Markdown (H1 Act -> H2 Chapter -> H3 Part -> H4 Section)
  pdpa_knowledge_graph.json   pre-built graph: 190 nodes / 380 edges, 11 node types, 26 edge types
scripts/
  build_graph.py         rule-based graph builder (sections + cross-references + curated nodes)
  validate_graph.py      counts nodes/edges from the data, checks connectivity and penalty reachability
labs/
  core/                  minimal MCP client (httpx), tool registry (MCP inputSchema -> OpenAI tools), LLM client
  lab7/agent_loop.py     the smallest possible agent loop, local tools only
  lab8/agent_pdpa_mcp.py the same loop wired to this MCP server
examples/mcp_curl.sh     talk to the server with plain curl + jq
docs/                    architecture and pipeline figures
Dockerfile, docker-compose.yml, requirements.txt, .env.example
```

`labs/` contains only the agent-side code; the course lab instructions are not part of this repo.

## Architecture

![Architecture: Agent -> MCP Server -> Engine -> Data](docs/fig1_architecture.png)

- **Knowledge graph**: NetworkX, in memory. 96 Section nodes plus Definition, LawfulBasis, Right,
  Obligation, Penalty, Exemption and Principle nodes; the backbone edges are `REFERENCES_SECTION`
  (122, section cites section) and `CONTAINS_SECTION` (119).
- **Vector index**: BGE-M3 (dense 1024-d + sparse lexical weights) in Qdrant with RRF fusion
  (k = 60, set with `RRF_K`; needs Qdrant server and client 1.16+, otherwise Qdrant's default k = 2 applies).
  Two collections: `pdpa_chunks` (96 full sections) and `pdpa_profiles` (570 = every node and edge
  rendered as a short text, so vector search can land on graph nodes).
- **MCP server**: FastMCP, `stateless_http=True`. Each tool's docstring is the description the agent
  reads before choosing a tool.
- **LLM on the server side** is used for exactly one thing, extracting search keywords. Answers are
  written by the agent's own model: *the server retrieves, the agent reasons.*

## Quick start

Requirements: Docker with Compose and an [OpenRouter](https://openrouter.ai) API key.

- **Docker memory:** give Docker at least 8 GB and avoid running other memory-heavy containers next to it.
  Startup peaked at 4.7 GB in our measurement (while embedding the statute text) and settles at about 2.8 GB.
  With too little memory the container is killed during startup (the log shows `Killed`, or the status is
  `Restarting (137)`).
- **Disk:** the built image is about 18 GB as reported by Docker (measured on an ARM Mac with Docker Desktop).
  Most of it is torch and its dependencies, plus BGE-M3 (~2.3 GB), which is baked in at build time so the
  container starts offline.
- **Pinned versions:** `requirements.txt` and `constraints.txt` fix every Python package, the `Dockerfile` uses
  Python 3.11.18 and compose uses Qdrant 1.20.0 — the set that produced the results in `docs/eval/`. (Checked on
  14 Nov 2026: a fresh build from the repo zip returned search contexts identical to the recorded ones when given
  the same keywords.) Not pinned: the BGE-M3 weights, downloaded from Hugging Face at build time (tested
  snapshot `5617a9f6`), and system packages from apt.

```bash
cp .env.example .env            # put your OPENROUTER_API_KEY in .env
docker compose up --build       # starts Qdrant + the MCP server; the first build downloads BGE-M3
```

Startup is done when the log shows:

```
Parsed 96 sections (มาตรา), 96 chunks
Upserted 570 profile vectors
Upserted 96 chunk vectors
```

Smoke test with curl (needs `jq`):

```bash
./examples/mcp_curl.sh
```

A bare request without the `Accept: application/json, text/event-stream` header returns
`-32600 Client must accept text/event-stream`. That means the server is alive; the streamable-http
transport simply requires the header.

Run the agent against the server:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-agent.txt
python labs/lab8/agent_pdpa_mcp.py "เก็บข้อมูลสุขภาพพนักงานได้ไหม ถ้าฝ่าฝืนมีโทษอะไร"
```

The statute and the agent's system prompt are in Thai, so Thai questions work best (the model
answers in Thai; change `SYSTEM` in `labs/lab8/agent_pdpa_mcp.py` to answer in another language).
With the original code a typical run made 7 tool calls in 4 rounds: `search_pdpa` ->
`get_related_sections` + `get_penalty` -> `get_section_text` x4 -> answer citing Sections 26 / 79 / 84.
The agent run has not been repeated with this version; expect the calls to differ.

## MCP tools

| Tool | What it does |
|---|---|
| `search_pdpa(query, top_k=5)` | Hybrid retrieval: LLM keywords -> profile search -> 2-hop BFS -> chunk search -> context (JSON) |
| `get_related_sections(section_id)` | In- and out-edges of one section, grouped by relationship |
| `get_penalty(section_id)` | BFS in both directions from the violated section to Penalty nodes. It reports Penalty nodes up to 2 hops away (the loop stops at hop 3 before recording one). Pass the violated section (`sec_26`), not the penalty section |
| `get_section_text(section_id)` | Full statute text of one section by id, deterministic (no vector search). Read from the Markdown, not from the graph node, whose `text` is cut at 3,000 characters |
| `get_pdpa_summary()` | Node/edge counts and the schema of the graph |

Section ids are `sec_<number>` with Arabic digits (`sec_26`), even though the statute text uses Thai
numerals (มาตรา ๒๖).

## How retrieval works

![search_pdpa pipeline](docs/fig3_search_pipeline.png)

1. An LLM splits the question into low-level keywords (section numbers, named rights, penalties) and
   high-level keywords (principles, concepts), after LightRAG's dual-level scheme.
2. Profile search (`pdpa_profiles`, dense + sparse, RRF) runs once per keyword level; the top 3
   node profiles become the seed nodes, skipping the Act node (`PDPA_2562`) because its neighbours are
   only chapters. That node can still appear in the context; it is just not a starting point for the
   graph walk. No LLM is involved in picking seeds.
3. Chunk search (`pdpa_chunks`) fetches the full text of up to 5 sections, using the same keywords.
   It does not use the graph result.
4. BFS from the seeds, 2 hops, following edges in both directions. At most 15 reached nodes go into the
   context: every seed gets an equal share, penalty and obligation edges come first, then cross-reference and
   exemption edges. When the question or its keywords mention a penalty, sections of the penalty chapter
   that reference a reached node (e.g. `sec_83` referencing `sec_37`) also come first. Finally,
   structural edges (chapter/part) only fill what is left. Each node is written as
   `[hop1] def_biometric ←DEFINES— sec_26: ...`: the left node is where the walk came from and the arrow
   follows the edge's direction in the graph, so the model can read a path from the seed step by step.
5. The context is capped (8 profiles, 15 expanded nodes, 5 full sections) and returned as JSON.
   The server never writes the answer.

## Rebuilding and validating the graph

```bash
python scripts/build_graph.py            # -> build/ (never overwrites data/)
python scripts/validate_graph.py         # checks data/pdpa_knowledge_graph.json
python scripts/validate_graph.py build/pdpa_knowledge_graph.json
```

`build_graph.py` is rule-based: a regex finds section headings in the Markdown, a second regex finds
cross-references inside each section (`REFERENCES_SECTION` edges), and the semantic nodes
(definitions, rights, obligations, penalties, exemptions, principles, lawful bases) are curated lists
inside the script. It reproduces the base graph (163 nodes / 345 edges). The shipped
`data/pdpa_knowledge_graph.json` is that base graph plus hand-added exemption nodes (190 / 380).
Its `metadata` block still reports the older 163 / 343 counts; always count from the data, which is
what `validate_graph.py` does.

To use this on another statute, swap the heading pattern (`Article\s+(\d+)` for GDPR,
`第([一二三四五六七八九十百]+)条` for Japan's APPI) and re-curate the semantic nodes.

## Known limitations

- Built for one statute. The graph lives in memory and both Qdrant collections are rebuilt on every
  start (no hot reload). For a corpus of laws use a graph database; `build_graph.py` also emits
  `pdpa_neo4j_import.cypher`.
- Rule-based graph construction means porting to a new law is curation work, not configuration.
- There is no standard evaluation set yet. What exists is a record of 12 internal test rounds in
  [`docs/eval/`](docs/eval/) (in Thai), with the code and raw data behind them in [`eval/`](eval/README.md).
  The 52 questions and their expected sections were written during development, in the agent round each was
  run once per build, and none has been reviewed by a lawyer. Contributions of question/answer pairs with expected section
  citations are welcome.
- The shipped graph has a known gap that affects `get_penalty` for one section; it is the subject of
  part 2 of the article series and is left as is until that article is published. Only Sections 77,
  79, 85, 86 and 90 have a Penalty node, so `get_penalty('sec_26')` returns the two criminal
  penalties of Section 79 and no administrative fine.
- The keyword LLM is the remaining source of run-to-run variation: at temperature 0 the same question
  still produced two different keyword sets in four calls, and each set gives its own context.
- The keyword prompt invites the LLM to guess section numbers, and the guesses can be wrong.

## Data

The statute text is the Personal Data Protection Act B.E. 2562 (2019), a public document, prepared
from the version published by the Office of the Council of State of Thailand. The knowledge graph,
code and figures are by the author.

## Article series

Written for the original repository; the runs they show come from the original code.

1. Why Vector RAG Answers Only Half of a Legal Question (Thai: https://aekanunbigdata.medium.com/a0f1e09e3450 — English version coming)
2. One missing edge: why the agent cited the wrong penalty section (coming)
3. Why a GraphRAG agent needs a fifth tool (coming)

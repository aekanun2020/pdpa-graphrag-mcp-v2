"""
Retrieval — PDPA Legal Knowledge Retrieval (PDPA RAG version)
=============================================================
keyword extraction → vector search → multi-hop BFS → hybrid context
ปรับ prompts จาก XXX ระบบไฟฟ้า → PDPA กฎหมายคุ้มครองข้อมูลส่วนบุคคล
"""

import networkx as nx
from .llm_provider import query_llm_json, query_llm
from .vector_index import VectorIndex
from .knowledge_graph import node_description

KEYWORD_PROMPT = """จากคำถามนี้: "{query}"

สร้าง keywords สำหรับค้นหาในกฎหมาย PDPA (พ.ร.บ.คุ้มครองข้อมูลส่วนบุคคล) ตอบเป็น JSON:
{{
  "low_level_keywords": ["keywords เฉพาะเจาะจง เช่น ชื่อหน่วยงาน สิทธิเฉพาะ หน้าที่เฉพาะ บทลงโทษ"],
  "high_level_keywords": ["keywords กว้าง เช่น หลักการ หมวดหมู่ แนวคิด ขั้นตอน"]
}}

กติกา:
1. ใช้ถ้อยคำแบบที่ตัวบทกฎหมายใช้ ไม่ใช่คำพูดของผู้ถาม เช่น "ขายข้อมูล" → "เปิดเผยข้อมูลส่วนบุคคล"
2. คิดก่อนเสมอว่ากฎหมายนี้ "ใช้บังคับ" กับผู้กระทำในคำถามหรือไม่ ถ้าผู้กระทำเป็นบุคคลธรรมดาที่ทำเพื่อตัวเอง
   หรือครอบครัว สื่อมวลชน งานศิลปะ/วรรณกรรม ศาล/กระบวนการยุติธรรม สภา หน่วยงานความมั่นคง หรือบริษัทข้อมูลเครดิต
   ให้ใส่ keywords เรื่องขอบเขตการใช้บังคับด้วย เช่น "ไม่ใช้บังคับ" "ประโยชน์ส่วนตน" "กิจกรรมในครอบครัว"
   "กิจการสื่อมวลชน" "การพิจารณาพิพากษาคดีของศาล" แล้วแต่กรณี
3. ใส่เลขมาตราเฉพาะเมื่อคำถามระบุเลขมาตรามาเอง ห้ามเดาเลขมาตรา ให้บรรยายเนื้อหาของมาตรานั้นแทน
4. ถ้าคำถามถามถึงโทษ ค่าปรับ ความรับผิด หรือค่าเสียหาย ต้องมีคำเรื่องนั้นใน low อย่างน้อย ๑ คำ
   โดยใช้คำของตัวบทให้ตรงชนิด: "โทษปรับทางปกครอง" (ค่าปรับที่คณะกรรมการผู้เชี่ยวชาญสั่ง)
   "โทษอาญา จำคุก" (ความผิดอาญา) "ค่าสินไหมทดแทน" (ความรับผิดทางแพ่งต่อเจ้าของข้อมูล)
   ถ้าไม่รู้ว่าเป็นโทษชนิดใด ให้ใส่ "โทษปรับทางปกครอง" และ "โทษอาญา" ทั้งคู่
5. low ไม่เกิน ๘ คำ high ไม่เกิน ๖ คำ ไม่ใส่คำที่คำถามไม่ได้ถามถึง

ตัวอย่าง:
คำถาม: "เก็บข้อมูลสุขภาพพนักงานได้ไหม"
→ low: ["ข้อมูลสุขภาพ", "ข้อมูลอ่อนไหว", "ความยินยอมโดยชัดแจ้ง"]
→ high: ["ฐานทางกฎหมาย", "การเก็บรวบรวม", "sensitive data", "ข้อยกเว้น"]

คำถาม: "ส่งข้อมูลลูกค้าไปต่างประเทศต้องทำอย่างไร"
→ low: ["การส่งหรือโอนข้อมูลส่วนบุคคลไปยังต่างประเทศ", "มาตรฐานการคุ้มครองข้อมูลส่วนบุคคลที่เพียงพอ"]
→ high: ["cross-border transfer", "ความเพียงพอของการคุ้มครอง", "ข้อยกเว้น"]

คำถาม: "จดเบอร์โทรและวันเกิดของเพื่อนไว้ในสมุดส่วนตัว ต้องขอความยินยอมไหม"
→ low: ["ประโยชน์ส่วนตน", "กิจกรรมในครอบครัว", "ไม่ใช้บังคับ", "การเก็บรวบรวมข้อมูลส่วนบุคคล"]
→ high: ["ขอบเขตการใช้บังคับของพระราชบัญญัติ", "ข้อยกเว้นการใช้บังคับ", "ความยินยอม"]

ตอบ JSON เท่านั้น"""


def extract_query_keywords(query: str) -> dict:
    prompt = KEYWORD_PROMPT.format(query=query)
    result = query_llm_json(
        prompt,
        system_prompt="สร้าง keywords สำหรับค้นหากฎหมาย PDPA ตอบ JSON เท่านั้น"
    )
    low = result.get("low_level_keywords", [])
    high = result.get("high_level_keywords", [])
    if not low and not high:
        low = query.split()
    return {"low_level": low, "high_level": high}


def retrieve(query: str, index: VectorIndex,
             knowledge_graph: nx.DiGraph,
             top_k: int = 5, max_chunks: int = 5) -> dict:
    """
    PDPA retrieval pipeline:
    1. LLM extract keywords จากคำถาม
    2. Vector search profiles (graph nodes/edges)
    3. Vector search chunks (เนื้อหามาตรา)
    4. Multi-hop BFS expansion จาก graph
    5. Build hybrid context
    """
    keywords = extract_query_keywords(query)
    low_query = " ".join(keywords["low_level"])
    high_query = " ".join(keywords["high_level"])

    # Profile search (knowledge graph)
    profile_results = []
    if high_query.strip():
        profile_results = index.search_profiles(high_query, top_k=top_k)
    if low_query.strip():
        more = index.search_profiles(low_query, top_k=3)
        seen = {r["profile"]["id"] for r in profile_results}
        for r in more:
            if r["profile"]["id"] not in seen:
                profile_results.append(r)

    # Multi-hop BFS expansion
    expanded = _expand_from_graph(profile_results, knowledge_graph, max_expand=3, max_hops=2)

    # Chunk search (มาตรา text)
    chunk_query = f"{low_query} {high_query}".strip() or query
    chunk_results = index.search_chunks(chunk_query, top_k=max_chunks)

    context = _build_context(profile_results, expanded, chunk_results)

    return {
        "keywords": keywords,
        "profile_results": profile_results,
        "chunk_results": chunk_results,
        "context": context,
    }


# ลำดับความสำคัญของชนิดเส้นตอนเลือกผลการเดินกราฟลง context (เลขน้อย = มาก่อน)
# vector search มักพลาด "ครึ่งหลัง" ของคำถามกฎหมาย คือบทลงโทษ การอ้างข้ามมาตรา และข้อยกเว้น
# จึงให้เส้นเหล่านี้มาก่อน ส่วนเส้นโครงสร้างเอกสาร (หมวด/ส่วน) มาท้ายสุด
# เส้นหน้าที่ (IMPOSES_OBLIGATION) อยู่ระดับเดียวกับบทลงโทษ: คำถามเชิงเหตุการณ์มักถามว่า
# "มีหน้าที่อะไรที่ไม่ได้ทำ" และโหนดหน้าที่เคยถูกเส้นอ้างข้ามมาตราเบียดออก (docs/eval รอบแรก ข้อ Q2)
_EDGE_PRIORITY = {
    "PRESCRIBES_PENALTY": 0,
    "IMPOSES_OBLIGATION": 0,
    "REFERENCES_SECTION": 1,
    "GRANTS_EXEMPTION": 1,
    "REFERENCES_EXEMPTION": 1,
    "CONTAINS_SECTION": 3,
    "HAS_CHAPTER": 3,
    "HAS_PART": 3,
}
_DEFAULT_EDGE_PRIORITY = 2
_STRUCTURAL_PRIORITY = 3      # เส้นโครงสร้าง: ได้ที่ใน context เฉพาะเมื่อยังเหลือโควตา

# ชนิดโหนดที่ไม่ให้เป็น seed: โหนดตัว พ.ร.บ. (PDPA_2562) ติดอันดับต้นบ่อยเพราะ profile กว้าง
# แต่เพื่อนบ้านมีแต่หมวด (HAS_CHAPTER) จึงกินที่ seed ไป 1 ใน 3 โดยไม่ได้ข้อมูลที่ช่วยตอบ
# โหนดนี้ยังถูกค้นเจอและแสดง VALUE ใน context ได้ตามปกติ แค่ไม่ใช้เป็นจุดเริ่มเดินกราฟ
_NON_SEED_LABELS = {"Law"}


def _expand_from_graph(results: list[dict], G: nx.DiGraph,
                       max_expand: int = 3, max_hops: int = 2,
                       max_items: int = 15) -> list[str]:
    """Multi-hop BFS expansion จาก knowledge graph — คืนไม่เกิน max_items บรรทัด

    การเลือก (เดิม: 15 โหนดแรกตามลำดับที่ BFS เดินถึง ทำให้ seed ที่มีเพื่อนบ้านมากกินโควตาหมด):
    1. แบ่งโควตาให้ทุก seed เท่ากันแบบ round-robin โควตาที่ seed หนึ่งใช้ไม่หมดตกเป็นของ seed อื่น
    2. ภายใน seed เดียวกัน เรียงตามชนิดเส้น (_EDGE_PRIORITY) แล้วตามจำนวน hop
    3. โหนด hop 2 ที่ถูกเลือกจะพาโหนด hop 1 ที่เป็นทางผ่านมาด้วยเสมอ เส้นทางจาก seed จึงไม่ขาดตอน
    4. โหนดที่มาด้วยเส้นโครงสร้าง (หมวด/ส่วน) ได้ที่เฉพาะเมื่อโหนดอื่นของทุก seed ถูกหยิบหมดแล้ว
       กันกรณี seed เป็นโหนดระดับบน เช่น PDPA_2562 ซึ่งมีแต่เส้นโครงสร้าง มากินโควตาของ seed อื่น

    รูปแบบบรรทัด (เดิม: "[hop1][REL] node: desc" ไม่บอกต้นทางและทิศของเส้น):
        [hop1] def_biometric ←DEFINES— sec_26: มาตรา ๒๖ ...
        [hop2] sec_26 —GRANTS_EXEMPTION→ sec26_ex1: ...
    โหนดซ้ายคือโหนดที่เดินมาจาก ลูกศรชี้ตามทิศของเส้นในกราฟ
    """
    # seed = node profiles อันดับต้น — กรอง edge profiles (id มี "--") และโหนดชนิด _NON_SEED_LABELS
    # ออก "ก่อน" ตัด top-N
    # ไม่เช่นนั้นถ้า 3 อันดับแรกเป็น edge ทั้งหมดจะไม่มี seed และไม่มีการเดินกราฟเลย
    seed_ids = []
    for r in results:
        node_id = r["profile"]["id"]
        if "--" in node_id or not G.has_node(node_id):
            continue
        if G.nodes[node_id].get("label") in _NON_SEED_LABELS:
            continue                      # ข้ามไป ให้ node profile อันดับถัดไปขึ้นมาเป็น seed แทน
        seed_ids.append(node_id)
        if len(seed_ids) >= max_expand:
            break

    from collections import deque
    visited = set(seed_ids)
    queue = deque((sid, 0, sid) for sid in seed_ids)
    candidates = {}                       # node id -> candidate dict
    by_seed = {sid: [] for sid in seed_ids}
    order = 0

    while queue:
        current, hop, root = queue.popleft()
        if hop >= max_hops:
            continue

        neighbors = list(G.successors(current)) + list(G.predecessors(current))
        for neighbor in neighbors:
            if neighbor in visited:
                continue
            visited.add(neighbor)

            outgoing = G.has_edge(current, neighbor)
            edge = G.edges.get((current, neighbor), {}) if outgoing else G.edges.get((neighbor, current), {})
            rel = edge.get("relation", edge.get("relationship", edge.get("type", "related")))

            cand = {"node": neighbor, "parent": current, "hop": hop + 1, "rel": rel,
                    "outgoing": outgoing, "order": order}
            order += 1
            candidates[neighbor] = cand
            by_seed[root].append(cand)
            queue.append((neighbor, hop + 1, root))

    # ลำดับการหยิบของแต่ละ seed: ชนิดเส้น -> hop -> ลำดับที่เดินถึง และแทรกทางผ่านไว้ก่อนเสมอ
    # แยกเป็นสองชุด: main = โหนดที่มาด้วยเส้นที่มีความหมายทางกฎหมาย, rest = เส้นโครงสร้าง
    main_seqs, rest_seqs = [], []
    for sid in seed_ids:
        ranked = sorted(by_seed[sid], key=lambda c: (
            _EDGE_PRIORITY.get(c["rel"], _DEFAULT_EDGE_PRIORITY), c["hop"], c["order"]))
        main, rest, emitted = [], [], set()
        for cand in ranked:
            structural = _EDGE_PRIORITY.get(cand["rel"], _DEFAULT_EDGE_PRIORITY) >= _STRUCTURAL_PRIORITY
            chain = []
            node = cand
            while node is not None and node["node"] not in emitted:
                chain.append(node)
                node = candidates.get(node["parent"])   # None เมื่อ parent คือ seed
            for c in reversed(chain):
                emitted.add(c["node"])
                (rest if structural else main).append(c)
        main_seqs.append(main)
        rest_seqs.append(rest)

    # round-robin สองรอบ: รอบแรกเฉพาะชุด main ของทุก seed แล้วจึงเติมด้วยชุด rest ถ้ายังไม่ครบ
    picked = [[] for _ in seed_ids]
    total = 0
    for seqs in (main_seqs, rest_seqs):
        taken = [0] * len(seqs)
        while total < max_items and any(taken[i] < len(seqs[i]) for i in range(len(seqs))):
            for i, seq in enumerate(seqs):
                if total >= max_items:
                    break
                if taken[i] < len(seq):
                    picked[i].append(seq[taken[i]])
                    taken[i] += 1
                    total += 1

    expanded = []
    for seq in picked:
        for c in sorted(seq, key=lambda c: (c["hop"], c["order"])):
            n_data = G.nodes.get(c["node"], {})
            desc = node_description(n_data, max_len=200) or n_data.get("label", c["node"])
            arrow = f"—{c['rel']}→" if c["outgoing"] else f"←{c['rel']}—"
            expanded.append(f"[hop{c['hop']}] {c['parent']} {arrow} {c['node']}: {desc}")

    return expanded


def _build_context(profile_results, expanded, chunk_results) -> str:
    """สร้าง hybrid context จาก graph profiles + chunks"""
    ctx = ""

    if profile_results:
        ctx += "## ความรู้จาก Knowledge Graph (PDPA)\n"
        for r in profile_results[:8]:
            ctx += f"- {r['profile']['value']}\n"
        if expanded:
            ctx += "\n### ข้อมูลเชื่อมโยง (multi-hop graph):\n"
            ctx += "(รูปแบบ: [hop] โหนดต้นทาง —ชนิดเส้น→ โหนดที่ไปถึง: เนื้อหา; ลูกศรชี้ตามทิศของเส้นในกราฟ)\n"
            for e in expanded[:15]:
                ctx += f"- {e}\n"

    if chunk_results:
        ctx += "\n## เนื้อหาต้นฉบับ PDPA (Original Text)\n"
        for cr in chunk_results:
            section = cr.get("section_id", "")
            h2 = cr.get("header_2", "")
            text = cr.get("text", "")
            if text:
                header = f"{h2} — {section}" if h2 else section
                ctx += f"\n### {header}:\n{text}\n"

    return ctx


def generate_answer(query: str, context: str) -> str:
    """สร้างคำตอบจาก context"""
    prompt = f"""ใช้ข้อมูลต่อไปนี้ในการตอบคำถามเกี่ยวกับ PDPA:

{context}

คำถาม: {query}

กฎ:
- ตอบเป็นภาษาไทย กระชับ ได้ใจความ
- อ้างอิงมาตราที่เกี่ยวข้องให้ชัดเจน (เช่น "ตามมาตรา ๒๖")
- แยกให้ชัดระหว่าง "บทบัญญัติตามกฎหมาย" กับ "คำแนะนำเพิ่มเติม"
- ถ้ามีบทลงโทษที่เกี่ยวข้อง ให้ระบุด้วย
- ถ้าข้อมูลไม่เพียงพอให้บอกตรงๆ"""

    system = ("คุณเป็น AI ที่ปรึกษากฎหมาย PDPA (พ.ร.บ.คุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562) "
              "ตอบคำถามโดยอ้างอิงจากเนื้อหากฎหมายจริง")
    return query_llm(prompt, system_prompt=system)

# eval/ — เครื่องมือที่ใช้สร้างผลใน `docs/eval/`

> **หมายเหตุ 20 พ.ย. 2569:** ผลทุกชุดในโฟลเดอร์นี้และใน `docs/eval/` ได้จากกราฟรุ่น 190 โหนด / 380 เส้น
> (ก่อน commit `0a02321` วันที่ 18 พ.ย. 2569 ซึ่งแก้ตัวบทในโหนดมาตราและเส้นอ้างข้ามมาตรา เป็น 382 เส้น)
> ยังไม่มีการรันซ้ำกับกราฟปัจจุบัน รายละเอียดอยู่ใน `docs/eval/README.md`

โฟลเดอร์นี้เก็บโค้ดและข้อมูลที่ใช้ทดสอบ branch `feat/expansion-quota-and-paths` เทียบกับ `main` (branch นี้ถูก merge เข้า `main` เมื่อ 14 พ.ย. 2569 (merge commit `c283237`) แล้วลบชื่อ branch ออก ปลาย branch คือ commit `861258b` ซึ่งยังอยู่ในประวัติของ `main`) รายงานของแต่ละรอบอยู่ที่ `docs/eval/` โฟลเดอร์นี้มีไว้ให้ตรวจย้อนและรันซ้ำได้

ไม่มี API key ในไฟล์ใด ทุกสคริปต์อ่าน key จาก environment ของ container `mcp-pdpa-rag`

## retrieval/ — รอบ 1 ถึง 10 (วัดจาก context)

สคริปต์ชุดนี้รันใน container โดยไม่เรียก server แต่ละไฟล์มีชุดคำถาม แนวคำตอบ และสำเนา `retrieval.py` ของรุ่นที่เทียบฝังอยู่ในตัว จึงเป็นภาพของโค้ด ณ เวลาที่รัน ไม่ใช่ของโค้ดปัจจุบัน (แก้ไข 14 พ.ย. 2569: บรรทัดคอมเมนต์หัวไฟล์ 1 บรรทัดในสำเนาที่ฝังไว้ถูกเปลี่ยนถ้อยคำ โค้ดไม่เปลี่ยน) เลขท้ายชื่อไฟล์คือลำดับที่เขียน ไม่ใช่เลขรอบในรายงาน

| ไฟล์ | ไฟล์ผลใน `docs/eval/` |
|---|---|
| `run_eval5.py` | `2026-11-13-pdpc-answers-results.json` |
| `run_eval6.py` | `2026-11-13-keyword-prompt-results.json` |
| `run_eval7.py` | `2026-11-13-keyword-prompt-penalty-results.json` |
| `run_eval12.py` | `2026-11-13-penalty-reference-results.json` |
| `run_eval14.py` | `2026-11-13-penalty-heldout-results.json` |
| `run_eval16.py` | `2026-11-13-other-questions-results.json` |

`run_eval8.py` ถึง `run_eval11.py`, `run_eval13.py` และ `run_eval15.py` เป็นรอบกลางทาง ผลของไฟล์เหล่านี้ไม่ตรงขนาดกับไฟล์ผลใดใน `docs/eval/` แบบหนึ่งต่อหนึ่ง จึงไม่ได้จับคู่ไว้ `variant_A.py` และ `variant_B.py` คือ `retrieval.py` สองแบบที่ลองในรอบขยายกราฟ `mk16.py` และ `sum16.py` ใช้สร้างและสรุปรอบสุดท้าย

## agent/ — รอบ 11 (วัดจากคำตอบของ agent)

รายงาน: `docs/eval/2026-11-13-agent-test.md`

| ที่อยู่ | คืออะไร |
|---|---|
| `harness/src/dfai_harness/` | runtime ของ harness คัดลอกจาก `aekanun2020/SUT-AI-Chat-App-with-Fine-tuned-Harness-with-KM` commit `36f62c9` (`vendor/harness/src/dfai_harness/`) ไม่ได้แก้แม้ตัวอักษรเดียว |
| `harness/harnesses/pdpa/` | ชุด PDPA ที่เขียนขึ้นสำหรับรอบนี้: `prompts/`, `hooks/pdpa.py`, `hooks/verify.py`, `policies/`, `contracts/`, `templates/` |
| `harness/run_pdpa.py` | ตัวรันหนึ่งคำถามกับ server หนึ่งรุ่น (`--server main` คือ port 8100, `--server branch` คือ port 8101) |
| `harness/offline_test.py` | ทดสอบ hook และตัวอ่านซ้ำ 20 ข้อโดยไม่เรียกโมเดล |
| `serve_branch.py` | เปิด server รุ่น branch เป็น process ที่สองใน container ที่ port 8101 โดยข้ามขั้นสร้าง index เพราะ `rag.build()` ตามปกติจะลบและสร้าง collection ใน Qdrant ใหม่ ต้องวาง `lightrag/retrieval.py` ของ branch ไว้ที่ `branch/retrieval.py` ข้างสคริปต์ |
| `run_all.py` | รันหลายคำถามกับทั้งสองรุ่น รันต่อจากที่ค้างได้ |
| `questions.json` | คำถาม 52 ข้อ ไม่มีแนวคำตอบ เป็นไฟล์เดียวที่ agent เห็น |
| `gold.json` | มาตราตามแนวคำตอบของแต่ละข้อ ใช้ตอนให้คะแนนเท่านั้น |
| `summarise.py`, `score.py` | สรุปแต่ละรอบ และให้คะแนนเทียบ `gold.json` |
| `probe.py` | ตรวจรูปแบบผลของเครื่องมือ MCP ก่อนเขียน hook |
| `runs/runs.tar.gz` | โฟลเดอร์ผลดิบของทุกรอบ: `pilot` (4 รอบ), `r1` (48 รอบ), `r2` (รันซ้ำ 3 ข้อบน `main`) มีคำขอและคำตอบของโมเดล หลักฐานทุกชิ้น และ contract |
| `timing/` | log ของ server ทั้งสองรุ่น, `gaps.py` วัดเวลาก่อนเริ่มค้น Qdrant ของ `search_pdpa` แต่ละครั้ง, `corr.py` เทียบเวลานั้นกับจำนวน keywords |
| `judge/` | การตรวจ correctness และ faithfulness: `RUBRIC.md` เกณฑ์, `build.py` สร้างชุดคำตอบที่ปิดชื่อรุ่น, `packets/` ชุดที่ผู้ตรวจอ่าน, `out/` คำตัดสินรายคำตอบ, `key.json` รหัสกับรุ่น, `agg.py` รวมคะแนนและตรวจซ้ำกับหลักฐานดิบ, `judged.json` ผลรวม |

### รันสคริปต์วิเคราะห์ซ้ำ (ไม่เรียกโมเดล)

```bash
cd eval/agent
mkdir -p results && tar -xzf runs/runs.tar.gz -C results
python3 summarise.py results/r1 && python3 score.py results/r1 gold.json
python3 timing/gaps.py timing/main-server-r1.log timing/branch-server.log
python3 timing/corr.py .
python3 judge/agg.py . -v
(cd harness && python3 -B offline_test.py)
```

### รันกับโมเดลซ้ำ (มีค่าใช้จ่าย)

ต้องมี `OPENROUTER_API_KEY` ใน environment และ server ที่ port 8100 ถ้าจะเทียบกับ branch ต้องเปิด `serve_branch.py` ก่อน การเปิด process ใน container และการเรียกโมเดลต้องได้รับอนุมัติจากเจ้าของระบบทุกครั้ง

```bash
python -B run_all.py --ids R1,H3,O10 --tag r2 --servers main
```

### สิ่งที่ต้องรู้ก่อนใช้ผล

- ชุด PDPA ของ harness เขียนโดยรู้ประเภทของคำถามในชุดทดสอบและจุดอ่อนที่พบในรอบ 4 ถึง 10 prompt ของขั้นสืบค้นจึงสั่งให้ตรวจขอบเขตการใช้บังคับและบทกำหนดโทษ ไม่มีเลขมาตราหรือคำจากโจทย์ แต่คะแนนสัมบูรณ์ของรอบ 11 น่าจะสูงกว่าที่ agent ทั่วไปจะได้ การเทียบ `main` กับ branch ยังใช้ได้เพราะใช้ harness เดียวกัน
- `score.py`, `judge/build.py` และ `timing/corr.py` ถูกแก้ตำแหน่งไฟล์ให้เข้ากับโฟลเดอร์นี้หลังรันจริง ตรรกะไม่เปลี่ยน และรันซ้ำแล้วได้ตัวเลขเดิม
- รายการ "มาตราที่ agent ดึงมา" ใน `judge/packets/` สกัดไม่ครบ ผู้ตรวจจึงแจ้งข้อความไม่มีหลักฐานเกินจริง `agg.py` ตรวจซ้ำกับหลักฐานดิบและรายงานเฉพาะที่ยืนยันได้

## learner/ — รอบ 12 (ผู้เรียนที่เริ่มจาก zip)

รายงาน: `docs/eval/2026-11-14-learner-reproduction.md`

| ไฟล์ | คืออะไร |
|---|---|
| `docker-compose.override.yml` | เปลี่ยนชื่อ container และ port ของชุดผู้เรียน เพื่อรันในเครื่องเดียวกับ server ของผู้สอนได้ วางไว้ข้าง `docker-compose.yml` ในโฟลเดอร์ที่แตกจาก zip |
| `extract_kw.py` | ดึงการเรียก `search_pdpa` ที่บันทึกไว้ในรอบ 11 (คำค้น, keywords, context) และผลของเครื่องมืออื่น จาก `eval/agent/runs/runs.tar.gz` ที่แตกแล้ว |
| `fixed_kw_learner.py` | รันใน container ของผู้เรียน: สร้าง index แบบเดียวกับ server แล้วค้นซ้ำด้วย keywords ที่ตรึงไว้ ไม่เรียก LLM |
| `tools_dump.py` | เรียกเครื่องมือ 4 ตัวที่ไม่ใช้ LLM กับ `sec_1` ถึง `sec_96` ผ่าน MCP แล้วเก็บข้อความที่ได้ |

ไฟล์ผลของรอบนี้ไม่ได้เก็บไว้ (ดูเหตุผลในรายงาน) สคริปต์ 3 ไฟล์เขียนกลับจากข้อความเดิมของสคริปต์ที่รันจริง `fixed_kw_learner.py` สร้าง collection ใน Qdrant ใหม่ทุกครั้งที่รัน จึงต้องรันกับ Qdrant ของชุดทดสอบเท่านั้น และ server หนึ่งชุดใช้หน่วยความจำสูงสุดราว 4.7 GB ตอนสร้าง index

## lab8/ — เครื่องมือสำหรับทดสอบ `labs/lab8` กับรายการคำถาม

| ที่อยู่ | คืออะไร |
|---|---|
| `run_lab8.py` | เรียก `run_agent` ของ `labs/lab8` ตามเดิมกับรายการคำถาม และบันทึกผลที่เครื่องมือส่งกลับ ข้อมูลการเรียกโมเดล คำตอบ และเวลา รันจาก root ของ repo ด้วย venv ของ agent |
| `judge/build_packets.py` | สร้างชุดตรวจจากผลรันในรูปแบบของ `eval/agent/judge/RUBRIC.md` |

สำเนา runtime ใน `eval/agent/harness/src/dfai_harness/runtime.py` ต่างจากต้นฉบับ (commit `36f62c9`) 4 บรรทัด: รายชื่อโมเดลที่อนุญาตเหลือเฉพาะ `deepseek/deepseek-v4.1-flash` ซึ่งเป็นตัวเดียวที่ repo นี้ใช้กับ agent

## unseen28/ — รอบ 13 (harness กับ lab8 บน 28 คำถามที่ยังไม่เคยใช้)

รายงาน: `docs/eval/2026-11-14-unseen-28-questions.md`

| ที่อยู่ | คืออะไร |
|---|---|
| `lab8/<id>.json` | ผลดิบของ lab8 28 ข้อ: คำตอบ การเรียกเครื่องมือพร้อมผลเต็ม การเรียกโมเดล และข้อความที่ lab8 พิมพ์ |
| `harness-runs.tar.gz` | โฟลเดอร์ผลดิบของ harness 28 ข้อ (`r3/main/<id>/`) รูปแบบเดียวกับ `agent/runs/runs.tar.gz` |
| `lab8.log`, `harness.log` | บรรทัดสรุปต่อข้อของตัวรันทั้งสอง |
| `judge/build_blind.py` | สร้างชุดตรวจของสองระบบด้วยกติกาหลักฐานเดียวกัน ปนกันแล้วตั้งรหัสสุ่ม |
| `judge/packets/`, `judge/out/`, `judge/key.json`, `judge/judged.json` | ชุดตรวจ 54 คำตอบ คำตัดสินรายคำตอบ ตารางรหัสกับระบบและข้อ และไฟล์รวม |

รันซ้ำกับโมเดล (มีค่าใช้จ่าย ต้องมี `OPENROUTER_API_KEY` และ server ที่ port 8100):

```bash
MCP_SERVER_URL=http://127.0.0.1:8100/mcp python eval/lab8/run_lab8.py eval/agent/questions.json /tmp/lab8-runs P2 P4
cd eval/agent && python3 -B run_all.py --ids P2,P4 --tag r3 --servers main
```


# Review rubric — correctness and faithfulness of PDPA answers

You review answers written by an AI agent to questions about Thailand's Personal Data Protection Act B.E. 2562 (PDPA).
The only authority is the statute text in `pdpa_law.md` (same folder). Section headings there use Thai numerals: มาตรา ๔, มาตรา ๒๖, มาตรา ๗๙ (๐๑๒๓๔๕๖๗๘๙ = 0123456789). Use Grep to find `มาตรา ๒๖ ` then Read the surrounding lines. Do not rely on your memory of the law; open the section before judging a claim. Ignore the answer key when judging correctness — it is only a hint about which sections matter.

For each packet file `packets/<CODE>.md`:

1. **List the legal claims** in "Answer to review": each distinct statement of what the PDPA provides (a rule, a condition, an exception, a right, a duty, a deadline, a penalty and its amount, who it applies to). Skip headings, restatements of the question, and practical advice that the answer itself labels as advice rather than law. Merge repeats of the same claim (the summary and the detail often say the same thing).
2. **Correctness** of each claim against the statute text:
   - `yes` — the statute says this.
   - `partly` — roughly right but imprecise in a way that changes meaning (drops a condition, overstates scope, wrong paragraph, wrong amount qualifier).
   - `no` — contradicts the statute, or the statute says nothing of the kind.
   Also check the citation: if the claim cites a section, does *that* section say it? (`citation wrong` when the content is right but lives in a different section.)
3. **Faithfulness** of each claim: a claim is grounded when the statute text that supports it is in a section listed under "Sections whose full text the agent retrieved", or is stated in "Other tool results the agent saw". A claim whose support lies only in a section outside that list is `not_in_evidence` even if it is correct (the agent wrote it from memory). A claim with no support anywhere is `no` for correctness and also `not_in_evidence`.
4. **Conclusion**: is the answer's bottom line to the question right under the statute? `correct`, `partly` (right direction but a material gap or error), or `wrong`. Give one sentence of reason. Also say whether the answer applies the decisive section(s) in substance (`uses_key_sections`: true/false) — not merely mentions them.

Write one JSON file per packet to `out/<CODE>.json`, exactly this shape:

```json
{"code": "X123", "n_claims": 0, "n_correct": 0, "n_partly": 0, "n_wrong": 0, "n_citation_wrong": 0, "n_not_in_evidence": 0,
 "conclusion": "correct|partly|wrong", "conclusion_reason": "...", "uses_key_sections": true,
 "problems": [{"type": "wrong|partly|citation|not_in_evidence", "quote": "short Thai quote from the answer, 25 words at most", "law_section": 0, "why": "what the statute actually says, one or two sentences"}]}
```

`n_correct + n_partly + n_wrong = n_claims`. `problems` lists every claim that is not a clean pass (every partly, wrong, citation-wrong, not-in-evidence claim). Be strict but fair: do not mark a claim down for paraphrasing, or for omitting detail that does not change the meaning. Do not edit any file other than your `out/*.json` files. You cannot tell and should not guess which system produced a packet.

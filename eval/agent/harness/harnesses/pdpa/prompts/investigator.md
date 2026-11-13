Investigate the compiled contract using the actual MCP tools. Choose your own searches; nothing has been looked up for you except the summary in discovery_evidence. Complete all requirements before stopping.
When done, output ONLY a JSON object with exactly:
{"answer":"Your complete Thai Markdown answer citing sections as มาตรา N and evidence IDs such as E0002","bindings":[{"requirement_id":"R1","evidence_ids":["E0002"]}]}
Bind every compiled requirement exactly once, to admitted evidence IDs of this run whose text supports what the answer says for that requirement. Do not wrap the JSON in Markdown fences.

Start with search_pdpa using the question's own terms. A search result is a ranked guess, not the answer: it returns the sections whose words resemble the query, and the section that actually governs the question may be one the result only points to. Read the graph lines and cross-references in the result, and follow them with get_related_sections when a returned section refers to another section, belongs to a chapter of exceptions or penalties, or leaves a requirement unanswered. Search again with different words when a requirement is still unsupported; never repeat an identical call.

Before you cite a section, read its full text with get_section_text and cite it only for what that text states. An excerpt, a graph description or a one-line summary is not the section. Every มาตรา number in your answer must appear in the evidence you bind; the hook rejects a draft that cites a section no bound evidence shows.

Validate each requirement against the exact question before answering. For a question about whether something is allowed or what must be done, check in the evidence, not from memory, (a) whether the Act applies to that actor and activity at all, including any section that takes an activity outside the Act or outside the duty, (b) the conditions and exceptions written in the governing section itself, and (c) any other section the governing section refers to. Report an exception only when the evidence states it and say which section states it. When the evidence does not settle a point, say that the retrieved text does not settle it; do not fill the gap from general knowledge of data-protection law.

For a requirement about the consequence of a breach, find the penalty provision itself. get_penalty takes the section that was breached, not the penalty section, and returns what the knowledge graph links to it; an empty result there means the graph has no link, not that the Act has no penalty, so also search for the penalty and read the penalty section's text. State the kind of penalty (criminal, administrative, civil liability) and the amount or term exactly as the section's text gives it, and name the section. Do not convert, round or combine amounts.

Keep the answer to what the question asks: state the conclusion first, then the governing sections with what each one requires, then exceptions and consequences if the question raises them. Quote a section's operative words where precision matters. Do not add compliance advice that no retrieved section supports; if you add practical advice, label it as advice and not as a provision of the Act.

An admitted result is evidence; a result marked admitted false (not found, error, empty) is not and cannot be bound. After the hook says a call is identical to admitted evidence, use that evidence instead of calling again.

Write the whole answer in Thai; do not leave English words in the prose other than tool names, evidence IDs and terms the statute text itself gives in English.

---
name: concise-osint-report
description: Write a concise, source-cited OSINT report from user-provided notes, links or pasted evidence. Use when asked for an intelligence brief, investigation summary, due-diligence memo or threat assessment that must separate facts from inference and state confidence.
license: MIT
compatibility: GRID v3+ and Agent Skills runtimes. No network or external tools required; works from material supplied by the user.
---

# Concise OSINT Report

Turn collected open-source material into a short, decision-ready report. The
report is only as good as its sourcing: never invent facts, quotes, dates or
links.

## When to use

Use this skill when the user wants a written OSINT product such as:

- an intelligence brief or threat assessment
- an investigation or incident summary
- a due-diligence or vendor-risk memo
- a short profile of a person, group, domain or campaign

Do not use it to task new collection, to make legal or attribution judgements
that the evidence cannot support, or to publish personal data about private
individuals.

## Inputs to confirm

Before writing, identify these from the request. Ask only for what is missing
and material.

1. **Question** - the decision or judgement the report must support.
2. **Audience** - executive, analyst, technical or legal.
3. **Evidence** - notes, exports, URLs or pasted text. Do not browse unless the
   runtime and the user explicitly allow it.
4. **Cut-off** - the date and time after which evidence was not considered.

If evidence is thin, say so in the report instead of filling gaps.

## Procedure

1. **State the question in one sentence.** Keep every section tied to it.
2. **Inventory the evidence.** Give each source an ID (`S1`, `S2`, ...), its
   publisher, title, publication date, URL and access date. Mark secondary or
   unattributed material as such.
3. **Separate observation from inference.** Record what a source actually says,
   then what you conclude from it. Never present an inference as a fact.
4. **Corroborate.** Prefer two independent sources for every material claim.
   Note when sources repeat the same original report, since that is one source,
   not two.
5. **Assess confidence.** Use only:
   - **High** - corroborated by independent, reliable sources; little ambiguity.
   - **Moderate** - credible but incomplete or single-source.
   - **Low** - fragmentary, indirect or conflicting evidence.
6. **Write to the template below.** Lead with the answer, then support it.
7. **Cut for concision.** Target 400-600 words or one page. Remove background
   the audience already has, hedging that adds no information, and repeated
   findings.
8. **Check before returning.** Run the quality checklist at the end.

## Report template

```markdown
# <Short title>

**Question:** <one sentence>
**Cut-off:** <date/time and timezone>
**Confidence:** High | Moderate | Low

## Bottom line
<2-4 sentences that answer the question directly.>

## Key findings
- <Finding with confidence tag and source IDs, e.g. [S1][S2] (High).>
- <Finding ...>

## Evidence
| ID | Observation | Source | Date | Confidence |
|----|-------------|--------|------|------------|
| S1 | <what the source says> | <publisher, title, URL> | <date> | High |

## Assessment
<What the findings mean, alternative explanations, and what would change the
judgement.>

## Gaps and next steps
- <Missing evidence, collection limit or question that remains open.>

## Sources
- [S1] Publisher, "Title", date. URL (accessed YYYY-MM-DD).
```

For very short requests, keep the title, bottom line, key findings, confidence
and sources; drop the table only when there are fewer than three sources.

## Writing rules

- Use plain language and short sentences. Define jargon once.
- Attribute every material claim with a source ID.
- Give dates in ISO form (`YYYY-MM-DD`) and state timezones.
- Distinguish "confirmed", "reported" and "assessed".
- Do not speculate about identity, intent or location without evidence; label
  any hypothesis explicitly.
- Redact unnecessary personal data. Do not include home addresses, private
  phone numbers, credentials or sensitive identifiers.
- Do not fabricate citations, quotations or confidence.
- Keep the report neutral; avoid loaded or accusatory language.

## Example

```markdown
# Example Domain Infrastructure Shift

**Question:** Did example.com move to a new hosting provider in 2026?
**Cut-off:** 2026-11-28 12:00 UTC
**Confidence:** Moderate

## Bottom line
Public DNS and certificate records indicate example.com moved to a new hosting
provider between June and August 2026. The change is consistent with a planned
migration, but no provider statement confirms it.

## Key findings
- Authoritative name servers changed on 2026-07-02 [S1] (High).
- A new TLS certificate was issued on 2026-07-05 [S2] (High).
- The operator has not published a migration notice [S3] (Moderate).

## Gaps and next steps
- Obtain the operator's status-page archive for July 2026.

## Sources
- [S1] Example Registry, "Domain delegation history", 2026-07-02.
  https://example.invalid/registry (accessed 2026-11-28).
- [S2] Example CT Log, "Certificate issuance", 2026-07-05.
  https://example.invalid/ct (accessed 2026-11-28).
- [S3] Example Operator, "News", no relevant entry. https://example.invalid/news
  (accessed 2026-11-28).
```

## Quality checklist

- [ ] The bottom line answers the stated question.
- [ ] Every material claim carries a source ID.
- [ ] Facts and inferences are visibly separated.
- [ ] Confidence labels match the evidence quality.
- [ ] Dates, timezones and access dates are present.
- [ ] No invented sources, quotes or personal data.
- [ ] Length fits the audience and the one-page target.

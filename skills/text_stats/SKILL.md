---
name: text_stats
description: Count words, characters, non-whitespace characters, lines and unique words in a text input. Use when the user asks for deterministic text statistics, length checks or word counts without network or external tools.
license: MIT
compatibility: GRID v3+ and Agent Skills runtimes. Standard library only; no network, filesystem or shell access. Counts Unicode code points.
---

# Text Stats

Return exact, repeatable counts for a piece of text. The tool does not interpret
or summarise the text; it only counts.

## When to use

Use this skill when the user asks for:

- a word or character count for a draft, message or document
- a length check against a limit, such as a post or abstract
- the number of lines or distinct words in supplied text

Do not use it to estimate reading time, detect language or judge readability
without doing that reasoning separately.

## Input

Pass the text exactly as supplied. Preserve punctuation, spacing and line
breaks; do not normalise, trim or expand it first. The input may be empty.

## Output

The tool returns a JSON object string with five integer fields:

| Field | Meaning |
|-------|---------|
| `characters` | Unicode code points, including whitespace |
| `characters_no_whitespace` | Code points left after removing all `\s` matches |
| `lines` | `str.splitlines()` length; empty input gives `0` |
| `words` | Tokens starting and ending with a letter or digit |
| `unique_words` | Distinct words compared with `casefold()` |

Words may contain internal apostrophes or hyphens, so `don't` and `well-known`
each count as one word. Underscores separate words. Punctuation alone does not
count as a word.

## Procedure

1. Collect the exact text. If it is in a file or message, quote it without
   editing.
2. Call the `text_stats` tool once with the full text.
3. Parse the returned JSON. If parsing fails, report the raw string and the
   error rather than guessing.
4. Present the counts in the user's requested units. Otherwise report words and
   characters first, then the remaining fields.
5. State the counting rule when it could change the answer, for example that
   hyphenated compounds count as one word.

## Example

Input:

```text
Hello world!
Second line.
```

Output:

```json
{"characters": 25, "characters_no_whitespace": 22, "lines": 2, "unique_words": 4, "words": 4}
```

## Limits

- Counts are code points, not bytes or grapheme clusters. An emoji outside the
  Basic Multilingual Plane counts as one character.
- Markup, URLs and code are counted literally. Strip or exclude them yourself
  first if the user wants prose-only counts.
- Empty input is valid and returns all zeros.

## Quality checklist

- [ ] The text passed to the tool is unmodified.
- [ ] The returned JSON parsed successfully.
- [ ] Units and counting rules are stated where ambiguity matters.
- [ ] No counts are estimated or rounded.

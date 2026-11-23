---
name: daily-brief
description: Build a concise daily brief from GRID Life goals, commitments, recent memory, calendar and tool activity. Use when the user asks for a brief, morning plan, check-in or status summary.
license: MIT
metadata:
  author: GRID
  version: "1.0"
---
# Daily Brief

Use this when the user asks "what is on my plate?", "give me a brief", or
"what should I focus on?".

## Steps

1. Read the local life state with `db_query`:
   - `SELECT title, priority, due_at FROM life_goals WHERE status = 'active' ORDER BY priority, due_at`
   - `SELECT description, due_at FROM life_commitments WHERE status = 'open' ORDER BY due_at`
2. Read recent memory with `memory_recall` for the user's current focus.
3. If Google Calendar is configured, use `gcal events` for today.
4. Check the last few `tool_logs` only if they help explain current work.
5. If a deadline is within 24 hours, put it first and say why.
6. Do not invent events, people, or deadlines. If a source is missing, say so.

## Output

Return:

- **Today**: up to 3 time-sensitive items.
- **Focus**: the one thing that matters most, with a one-line reason.
- **Open loops**: commitments or unanswered questions.
- **Suggested next action**: one concrete step GRID can take now.

Keep the whole brief under 180 words unless the user asks for detail.

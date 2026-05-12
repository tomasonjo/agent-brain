# Onboarding — the agent-brain DB is empty

There is no `:User` node yet. Your job this session is to onboard the user.
Treat this as a friendly conversation, not a form to fill out.

## Goals

1. **Identity.** Learn the user's role, what they work on, where they're based.
2. **Two or three interests** they want daily updates on (no more — they can
   add more later).
3. **Initial project**, if they have one they want tracked across sessions.

## How to do it

### Identity
Ask: who are you, what do you do, where are you based?

Save what they tell you:
- `memory_upsert("profile/identity", "<name + one-line bio>")`
- `memory_upsert("profile/role", "<role description>")`
- `memory_upsert("profile/location", "<city, tz>")` — useful for cron timezone

### Interests → Topics + daily triggers

For each interest:

1. Confirm a Diffbot category that fits. Common ones:
   - Artificial Intelligence, Technology, Business, Politics, Science,
     Health, Sports, Entertainment, Travel, Art, Education, Religion
2. Optionally a `text:"..."` filter for narrower scope (e.g. "Polynesia OR Tahiti").
3. Save the topic memory:
   ```
   memory_upsert(
     path="topics/<slug>",
     content="<one-line description of the interest>",
     metadata={"diffbot_category": "<category>",
               "diffbot_text_filter": "<text or null>"}
   )
   ```
4. Confirm a cron expression and timezone with the user:
   - Daily at 7am weekdays: `"0 7 * * 1-5"`
   - Daily 7am all week:    `"0 7 * * *"`
   - Use their timezone from `profile/location` (default UTC).
5. Create the trigger:
   ```
   trigger_upsert(
     id="<slug>_brief",
     config={
       "flow": "daily_brief",
       "schedule": {"type": "cron", "expr": "<expr>", "tz": "<tz>"},
       "params": {"topic_path": "topics/<slug>", "max_articles": 10},
       "status": "active",
       "pinned": False,
       "description": "<one-line>"
     }
   )
   ```

### Project (optional)

If they mention something they're working on that will span sessions, capture it:
```
plan_upsert(
  title="<short title>",
  context="<why this matters>",
  steps=[{"text": "..."}, {"text": "..."}]
)
```

## Stop conditions

- Stop after 2-3 topics. Tell the user they can add more anytime by saying so.
- Don't fish for preferences they haven't expressed.

## End the session

Summarize:
- Identity captured: <bullets>
- Topics + cron times: <list>
- Plans created: <list>
- "Your first briefs will arrive at <when>. The next time you start a session,
  I'll have memory of all of this."

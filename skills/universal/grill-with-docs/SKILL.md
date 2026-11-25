---
name: grill-with-docs
description: Use when the user asks to grill a plan or design while recording a glossary and architecture decisions, or invokes /grill-with-docs.
disable-model-invocation: true
---

Follow the `grilling` skill. If your agent has no Skill tool, read its `SKILL.md` from the installed skills or the toolbox repo.

Read the project's `GLOSSARY.md` and relevant decisions in `docs/adr/`. If `GLOSSARY-MAP.md` exists, use it to find the glossary for this part of the project.

During the interview, compare unclear terms with the code and ask about a concrete example. Add agreed terms to the glossary as you go. Keep definitions about the domain and put implementation details in an architecture decision record (ADR) when they matter.

Offer an ADR when the decision is hard to reverse, involved a real tradeoff, and would surprise a future reader. Record the context, decision, and consequences. Create the glossary or ADR directory when you first have something to record.

---
name: Ready for agent
about: One unit of work an agent can finish in one sitting
title: ""
labels: ""
assignees: ""
---

<!--
docs/agents/issue-tracker.md, section "What a ready-for-agent issue carries", owns this shape and the
reasons behind it. Read it once, then this template is enough.

Three rules that are easy to get wrong:

1. Do not write a Status, a Blocked by, or an Unblocks line. GitHub carries all three. Add a blocking
   edge with the issue dependencies UI, or with the gh api call the tracker doc gives.
2. Set the milestone (M0 to M4) and one area:* label. The area label picks the gate set.
3. Apply ready-for-agent yourself, and only after answering this question: can one agent reach the
   end state, run the verification, and commit, without a second decision from the maintainer? If
   the answer is no, this issue holds a decision. File the decision as its own issue and make it
   block this one.

Optional prose goes here, above End state: why this work matters, and why it is actionable today.
Do not write who filed it or when. GitHub records both.
-->

## End state

<!-- What is true when this is done, in sentences a reader can check. An end state, never a list of
keystrokes. A procedure goes stale when the tree moves. An end state stays checkable. -->

## Verification

<!-- Name the gate set the root CLAUDE.md owns, and do not restate its commands.
.claude/rules/testing.md maps the surface to the set. Then name the reading that proves this change,
and its negative control. Documentation only: write "no gate" in words. -->

## Sources

<!-- Every path:line this issue rests on, each with the short commit SHA it was read at. Quote the
text of any claim the issue turns on. A measurement carries its command, its output, and its date. -->

## Out of scope

<!-- What a reader might reasonably expect and will not get. Where there is nothing, write that there
is nothing. -->

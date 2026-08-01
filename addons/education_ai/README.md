# Education AI (future phase)

Not yet implemented (`installable: False`), and no live LLM integration
exists in this codebase yet. Planned scope: AI-generated lesson plans,
homework, quizzes, revision notes, worked examples, flashcards, tutoring
scripts, lesson summaries, next-lesson recommendations, weak-topic
identification, and revision-plan suggestions.

Schema groundwork already in place (added in Phase 1 specifically so this
module needs no schema migration later):

- Every model inheriting `education.abstract.mixin` (education_core,
  education_curriculum, education_content, education_course) carries
  `keywords`, `ai_description`, and `embedding_synced` fields.

This module must stay optional and removable without affecting the rest of
the suite — no other `education_*` module may depend on it.

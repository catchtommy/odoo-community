# Education Progress (future phase)

Not yet implemented (`installable: False`). Planned scope: learning
analytics and progress reporting — completion trends, weak-topic
identification, tutor-comment aggregation, and the surface AI
recommendations will read from.

Important design note: `education.student.progress` (the base per-student,
per-lesson completion record) already exists in `shiningace_education_course` — added
there in Phase 1 so the "lesson taught → progress recorded" loop closes
without waiting on this module. `shiningace_education_progress` should build
rollups/analytics *over* that existing table, not redefine it.

Depends on `shiningace_education_course` (for the base progress table) and
`shiningace_education_assessment` (for assessment scores).

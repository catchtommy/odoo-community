# Education Assessment (future phase)

Not yet implemented (`installable: False`). Planned scope:

- `education.question.bank` — MCQ, True/False, Essay, Fill Blanks, Match,
  Ordering, Diagram, Coding, Numeric question types, each linked to a
  Curriculum / Subject / Topic / Subtopic / Lesson / Difficulty / Learning
  Objective (all of which already exist in `shiningace_education_curriculum` /
  `shiningace_education_content`).
- `education.assessment` — Practice, Homework, Weekly Test, Monthly Test,
  Mock Exam, Final Exam, Diagnostic Test, with automatic question selection
  from the question bank.
- Mark schemes and answer sheets.

Depends on `shiningace_education_content`. Will be depended on by `shiningace_education_progress`
(for assessment scores feeding into progress analytics).

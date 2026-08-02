# Education Core

Shared foundation module for the ShiningAce Curriculum Management suite.

## Migration note: retiring `shiningace_curriculum`

This suite supersedes the prototype module `shiningace_curriculum`
(`learning.country`, `exam.board`, `grade.group`, `grade.level`,
`curriculum.subject`, `curriculum.topic`, `curriculum.skill`). That module
held no production data (a single prototype commit), so there is **no
automatic data migration** — the model/table names are simply different.

If `shiningace_curriculum` is installed in any environment:

1. Uninstall it first: **Apps → search "ShiningAce Curriculum" → Uninstall**.
2. Then install `shiningace_education_core`, `shiningace_education_curriculum`, `shiningace_education_content`,
   `shiningace_education_course`.

`shiningace_education_core`'s `pre_init_hook` will refuse to install while
`shiningace_curriculum` is still installed, to avoid confusion between the
two model sets.

## Model rename mapping

| Old model (`shiningace_curriculum`) | New model | New module |
|---|---|---|
| `learning.country` | `education.country` | `shiningace_education_core` |
| `exam.board` | `education.exam.board` | `shiningace_education_core` |
| `grade.group` + `grade.level` | `education.academic.level` | `shiningace_education_core` |
| `curriculum.subject` | `education.subject` | `shiningace_education_core` |
| `curriculum.topic` | `education.topic` | `shiningace_education_curriculum` |
| `curriculum.skill` | `education.skill` | `shiningace_education_curriculum` |

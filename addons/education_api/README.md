# Education API (future phase)

Not yet implemented (`installable: False`). Planned scope: authenticated
JSON REST endpoints for Curriculum, Lesson, Topics, Resources, Student
Progress, Assessments, Question Bank.

Approach: plain Odoo `http.Controller` classes with `@http.route(type='json', auth=...)`,
matching the pattern already used in `tuition_management/controllers/` —
no FastAPI, no `odoo-rest`, no third-party REST framework, since none exists
elsewhere in this codebase.

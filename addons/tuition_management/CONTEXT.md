# Tuition Management Module — Developer Context

## Project Overview
- **Odoo version:** 19.0
- **Module:** `tuition_management`
- **Database:** `odoo-community-db`
- **Workspace:** `/Users/tomthomas/projects/shiningace/odoo-community/odoo-community/`
- **Branch:** `feature/virtual-class-integration`
- **Start server:** `python3 odoo-bin -d odoo-community-db &`
- **Upgrade module:** `python3 odoo-bin -u tuition_management -d odoo-community-db --stop-after-init`

---

## Key Models

### `course.master` (`models/course.py`)
| Field | Type | Notes |
|---|---|---|
| `name` | Char | required |
| `category_id` | Many2one → `subject.category` | standalone, store=True |
| `subject_id` | Many2one → `subject.master` | |
| `grade_id` | Many2one → `grade.master` | |
| `tutor_id` | Many2one → `tutor.profile` | Primary Tutor |
| `tutor_ids` | Many2many → `tutor.profile` | relation: `course_master_tutor_rel` |
| `eligible_tutor_ids` | Many2many → `tutor.profile` | computed, store=False |
| `coordinator_id` | Many2one → `res.users` | |

**Onchange methods:**
- `_onchange_subject_id` — auto-sets `category_id` from subject's category
- `_onchange_category_id` — clears `subject_id` if category changes
- `_compute_eligible_tutor_ids` — depends on `subject_id`, `grade_id`

### `tutor.profile` (`models/profile.py`)
| Field | Type | Notes |
|---|---|---|
| `subject_ids` | Many2many → `subject.master` | DB table: `subject_master_tutor_profile_rel` |
| `grade_ids` | Many2many → `grade.master` | DB table: `grade_master_tutor_profile_rel` |
| `category_ids` | Many2many → `subject.category` | computed+stored via `_compute_teaching_matrix` |
| `tutor_subject_rate_ids` | One2many → `tutor.subject.rate` | pricing matrix |

**`_compute_teaching_matrix`** — runs when `tutor_subject_rate_ids` changes; writes `category_ids` and `subject_ids` from active rates.

### `subject.master` (`models/master.py` — `SubjectMasterExt` inherits)
| Field | Type |
|---|---|
| `category_id` | Many2one → `subject.category` |

---

## Database Tables (Many2many relations)
| Table | Columns |
|---|---|
| `subject_master_tutor_profile_rel` | `tutor_profile_id`, `subject_master_id` |
| `grade_master_tutor_profile_rel` | `tutor_profile_id`, `grade_master_id` |
| `course_master_tutor_rel` | `course_id`, `tutor_id` (for `tutor_ids`) |
| `subject_category_tutor_profile_rel` | tutor ↔ category |

---

## Test Data (as of 2 May 2026)
### Tutors
| id | name | subjects (id: name/category) | grades |
|---|---|---|---|
| 1 | Tutor1 | 1:Math/SAT, 6:English/SAT | Year 8, Year 9 |
| 2 | tutor english | 1:Math/SAT, 2:English/Language, 6:English/SAT | Year 5, Year 9 |
| 3 | tutor3 | 6:English/SAT | Year 9 |
| 4 | tutor4 | none | none |
| 5 | tutor2 | 1:Math/SAT, 6:English/SAT | Year 8, Year 9 |
| 6 | Tutor3 | 7:Malayalam/Regional Language | Year 9 |

### Subject Masters
| id | name | category_id | category name |
|---|---|---|---|
| 1 | Math | 1 | SAT |
| 2 | English | 2 | Language |
| 3 | Math | 3 | Elementary |
| 4 | Math | 5 | Middle School |
| 5 | Physics | 6 | High School |
| 6 | English | 1 | SAT |
| 7 | Malayalam | 7 | Regional Language |

### Grades
| id | name |
|---|---|
| 1 | Year 9 |
| 2 | Year 5 |
| 3 | Year 6 |
| 5 | Year 7 |
| 6 | Year 8 |

---

## View: `course_views.xml`

### Course Form — Tutor Domain (current working approach)
```xml
<field name="category_id"/>
<field name="subject_id" domain="[('category_id', '=', category_id)] if category_id else []"/>
<field name="grade_id"/>
<field name="tutor_id" string="Primary Tutor"
    domain="['&amp;', ('subject_ids', 'in', [subject_id]), '|', ('grade_ids', 'in', [grade_id]), ('grade_ids', '=', False)] if subject_id and grade_id else [('subject_ids', 'in', [subject_id])] if subject_id else []"/>
<field name="tutor_ids" string="All Tutors (Primary + Supporting)" widget="many2many_tags"
    domain="['&amp;', ('subject_ids', 'in', [subject_id]), '|', ('grade_ids', 'in', [grade_id]), ('grade_ids', '=', False)] if subject_id and grade_id else [('subject_ids', 'in', [subject_id])] if subject_id else []"
    options="{'no_create': True}"/>
```

> **Why direct domain (not `eligible_tutor_ids`)?**  
> In Odoo 19 OWL frontend, computed Many2many field values in domain context are serialized as write command tuples `[[6, 0, [ids]]]`, not flat ID lists. This caused `[('id', 'in', [[6,0,[...]]])]` to match nothing. Direct domain using `subject_id` and `grade_id` integers works reliably.

---

## Known Issues / Warnings (non-blocking)
- `_sql_constraints` model attribute deprecated in 19.0 → use `model.Constraint`
- `partner_id` on `student_profile` / `parent_profile` allows null (schema warning)
- `tutor_id` on `class_schedule` allows null
- `enquiry.name` / `enquiry.student_name` allow null
- `tuition.invoice.preview.wizard.line` has no access rules
- Two fields with same label in `tuition.subscription` (`Current Plan`, `Invoices`)
- FA icon `<i>` tags missing `title` attribute in several views

---

## Architecture Notes

### Odoo 19 Domain Evaluation in OWL Views
- `subject_id`, `grade_id` etc. (Many2one) → available as integer IDs in domain context ✅
- Computed non-stored Many2many fields → sent as write commands, NOT flat IDs in domain context ❌
- **Use direct field IDs in domains, avoid computed Many2many as domain sources**

### `_compute_teaching_matrix` Side-Effect
- Writes `subject_ids` to `tutor.profile` from active `tutor_subject_rate_ids`
- This is a side-effect write inside a compute for `category_ids`
- Data is authoritative in DB (`subject_master_tutor_profile_rel`)

### Module Upgrade Process
1. Edit files
2. `python3 odoo-bin -u tuition_management -d odoo-community-db --stop-after-init`
3. Restart: `python3 odoo-bin -d odoo-community-db &`

### psql Access
```bash
psql -d odoo-community-db
```

---

## File Map
```
addons/tuition_management/
├── models/
│   ├── course.py          # course.master — main course model
│   ├── profile.py         # tutor.profile, tutor.availability
│   ├── master.py          # subject.master (ext), grade.master, subject.category
│   ├── schedule.py        # class.schedule, class.schedule.occurrence
│   ├── billing.py         # tuition.subscription, billing models
│   └── ...
├── views/
│   ├── course_views.xml   # Course form/list — tutor domain logic here
│   ├── profile_views.xml  # Tutor profile form
│   ├── master_views.xml   # Subject/Grade/Category masters
│   └── ...
├── security/
│   └── ir.model.access.csv
├── controllers/
│   └── dashboard.py
└── CONTEXT.md             # ← this file
```

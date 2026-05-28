# -*- coding: utf-8 -*-
import base64
import csv
import io

from odoo import api, fields, models
from odoo.exceptions import UserError

# ---------------------------------------------------------------------------
# Column definitions – order determines CSV column order
# ---------------------------------------------------------------------------
COLUMNS = [
    # (csv_header, field_name, field_type, notes)
    ('Full Name',    'name',         'char', 'Required'),
    ('Email',        'email',        'char', ''),
    ('Country Code', 'country_code', 'char', 'e.g. +1'),
    ('Phone',        'phone',        'char', 'Digits only'),
    ('Timezone',     'timezone',     'char', 'e.g. UTC, America/New_York'),
    ('Status',       'status',       'char', 'active or inactive'),
    ('Categories',   'category_ids', 'm2m',  'Pipe-separated names e.g. Mathematics|Science'),
    ('Subjects',     'subject_ids',  'm2m',  'Pipe-separated names e.g. Calculus|Physics'),
    ('Grades',       'grade_ids',    'm2m',  'Pipe-separated names e.g. Grade 9|Grade 10'),
]

HEADERS = [c[0] for c in COLUMNS]

EXAMPLE_ROW = [
    'Jane Smith',
    'jane@example.com',
    '+1',
    '5551234567',
    'UTC',
    'active',
    'Mathematics',
    'Calculus|Algebra',
    'Grade 9|Grade 10',
]

M2M_MODELS = {
    'Categories': ('subject.category', 'name'),
    'Subjects':   ('subject.master',   'name'),
    'Grades':     ('grade.master',     'name'),
}


# ---------------------------------------------------------------------------
# Preview line model – one row per CSV data row
# ---------------------------------------------------------------------------

class TutorImportWizardLine(models.TransientModel):
    _name = 'tutor.import.wizard.line'
    _description = 'Tutor Import Preview Line'
    _order = 'row_num'

    wizard_id = fields.Many2one('tutor.import.wizard', ondelete='cascade')
    row_num = fields.Integer(string='Row #', readonly=True)

    # Editable data fields
    name = fields.Char(string='Full Name')
    email = fields.Char(string='Email')
    country_code = fields.Char(string='Country Code')
    phone = fields.Char(string='Phone')
    timezone = fields.Char(string='Timezone')
    status = fields.Selection(
        selection=[('active', 'Active'), ('inactive', 'Inactive')],
        string='Status',
        default='active',
    )
    # Many2many stored as raw pipe-separated strings for easy inline editing
    categories = fields.Char(string='Categories',
                              help='Pipe-separated e.g. Mathematics|Science')
    subjects = fields.Char(string='Subjects',
                            help='Pipe-separated e.g. Calculus|Algebra')
    grades = fields.Char(string='Grades',
                         help='Pipe-separated e.g. Grade 9|Grade 10')

    # Status flags (set during preview parse, readonly)
    action = fields.Selection(
        selection=[('create', 'Create'), ('update', 'Update')],
        string='Action',
        readonly=True,
        help='Whether this row will create a new tutor or update an existing one.',
    )
    warning = fields.Char(string='Notes / Warnings', readonly=True)
    has_error = fields.Boolean(readonly=True)


# ---------------------------------------------------------------------------
# Main wizard model
# ---------------------------------------------------------------------------

class TutorImportWizard(models.TransientModel):
    _name = 'tutor.import.wizard'
    _description = 'Tutor Import / Export Wizard'

    # Import inputs
    import_file = fields.Binary(string='Upload CSV File', attachment=False)
    import_filename = fields.Char()

    # Preview lines
    preview_line_ids = fields.One2many(
        'tutor.import.wizard.line', 'wizard_id', string='Preview')
    preview_count = fields.Integer(
        string='Total Rows', compute='_compute_preview_stats')
    preview_create_count = fields.Integer(
        string='To Create', compute='_compute_preview_stats')
    preview_update_count = fields.Integer(
        string='To Update', compute='_compute_preview_stats')
    preview_error_count = fields.Integer(
        string='Rows with Issues', compute='_compute_preview_stats')

    # Output (template / export download)
    output_file = fields.Binary(string='Download File', readonly=True, attachment=False)
    output_filename = fields.Char(readonly=True)

    # Import result summary
    result_log = fields.Text(string='Import Result', readonly=True)

    state = fields.Selection(
        selection=[
            ('ready',       'Ready'),
            ('preview',     'Preview'),
            ('export_done', 'Download Ready'),
            ('import_done', 'Import Done'),
        ],
        default='ready',
        readonly=True,
    )

    # ── Computed stats ────────────────────────────────────────────────────────

    @api.depends('preview_line_ids', 'preview_line_ids.action',
                 'preview_line_ids.has_error')
    def _compute_preview_stats(self):
        for rec in self:
            lines = rec.preview_line_ids
            rec.preview_count = len(lines)
            rec.preview_create_count = len(lines.filtered(
                lambda l: l.action == 'create'))
            rec.preview_update_count = len(lines.filtered(
                lambda l: l.action == 'update'))
            rec.preview_error_count = len(lines.filtered(lambda l: l.has_error))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_csv(self, rows):
        buf = io.StringIO()
        csv.writer(buf, quoting=csv.QUOTE_MINIMAL).writerows(rows)
        return base64.b64encode(buf.getvalue().encode('utf-8'))

    def _resolve_m2m_ids(self, model, name_field, names_str):
        """Resolve pipe-separated names → (ids, unresolved_names)."""
        if not names_str or not names_str.strip():
            return [], []
        ids, unresolved = [], []
        for raw in names_str.split('|'):
            nm = raw.strip()
            if not nm:
                continue
            rec = self.env[model].search([(name_field, '=ilike', nm)], limit=1)
            if rec:
                ids.append(rec.id)
            else:
                unresolved.append(nm)
        return ids, unresolved

    def _m2m_names(self, records):
        return '|'.join(r.name for r in records)

    def _find_existing(self, email, name):
        """Return existing tutor only when email AND name both match."""
        if not email or not name:
            return self.env['tutor.profile']
        return self.env['tutor.profile'].search(
            [('email', '=', email), ('name', '=ilike', name)], limit=1)

    # ── Export / Template ─────────────────────────────────────────────────────

    def action_download_template(self):
        notes_row = ['# ' + c[3] for c in COLUMNS]
        self.write({
            'output_file': self._build_csv([HEADERS, notes_row, EXAMPLE_ROW]),
            'output_filename': 'tutor_import_template.csv',
            'state': 'export_done',
        })
        return self._reopen()

    def action_export_tutors(self):
        tutors = self.env['tutor.profile'].search([], order='name')
        rows = [HEADERS] + [
            [
                t.name or '',
                t.email or '',
                t.country_code or '',
                t.phone or '',
                t.timezone or '',
                t.status or 'active',
                self._m2m_names(t.category_ids),
                self._m2m_names(t.subject_ids),
                self._m2m_names(t.grade_ids),
            ]
            for t in tutors
        ]
        self.write({
            'output_file': self._build_csv(rows),
            'output_filename': 'tutors_export.csv',
            'state': 'export_done',
        })
        return self._reopen()

    # ── Preview ───────────────────────────────────────────────────────────────

    def action_preview(self):
        """Parse the uploaded CSV and show data as editable preview rows."""
        if not self.import_file:
            raise UserError("Please upload a CSV file first.")

        try:
            raw = base64.b64decode(self.import_file)
            text = raw.decode('utf-8-sig')
        except Exception as exc:
            raise UserError("Could not read the file:\n%s" % str(exc))

        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames or []

        missing = set(HEADERS) - set(fieldnames)
        if missing:
            raise UserError(
                "Missing columns:\n  %s\n\n"
                "Please use the template from 'Download Import Template'."
                % ', '.join(sorted(missing))
            )

        # Clear previous preview
        self.preview_line_ids.unlink()

        line_vals = []
        for row_num, row in enumerate(reader, start=2):
            first_val = (row.get('Full Name') or '').strip()
            # Skip comment rows inserted by the template
            if first_val.startswith('#'):
                continue

            name = first_val
            email = (row.get('Email') or '').strip() or False
            raw_status = (row.get('Status') or 'active').strip().lower()
            status = raw_status if raw_status in ('active', 'inactive') else 'active'

            row_warnings = []
            has_error = False

            if not name:
                row_warnings.append("Full Name is required.")
                has_error = True

            if raw_status and raw_status not in ('active', 'inactive'):
                row_warnings.append(
                    "Unknown status '%s' → will use 'active'." % raw_status)

            # Warn about unresolvable many2many values
            for col_header, (model, name_fld) in M2M_MODELS.items():
                raw_val = row.get(col_header, '')
                if raw_val and raw_val.strip():
                    _, unresolved = self._resolve_m2m_ids(model, name_fld, raw_val)
                    if unresolved:
                        row_warnings.append(
                            "%s not found: %s" % (col_header, ', '.join(unresolved)))

            existing = (
                self._find_existing(email, name) if name
                else self.env['tutor.profile']
            )
            action = 'update' if existing else 'create'

            line_vals.append({
                'wizard_id': self.id,
                'row_num': row_num,
                'name': name or False,
                'email': email,
                'country_code': (row.get('Country Code') or '+1').strip(),
                'phone': (row.get('Phone') or '').strip() or False,
                'timezone': (row.get('Timezone') or 'UTC').strip(),
                'status': status,
                'categories': (row.get('Categories') or '').strip() or False,
                'subjects': (row.get('Subjects') or '').strip() or False,
                'grades': (row.get('Grades') or '').strip() or False,
                'action': action,
                'warning': ' | '.join(row_warnings) if row_warnings else False,
                'has_error': has_error,
            })

        if not line_vals:
            raise UserError("No data rows found in the uploaded file.")

        self.env['tutor.import.wizard.line'].create(line_vals)
        self.state = 'preview'
        return self._reopen()

    # ── Confirm import ────────────────────────────────────────────────────────

    def action_confirm_import(self):
        """Process preview lines (after user review) and write to tutor.profile."""
        valid_lines = self.preview_line_ids.filtered(lambda l: not l.has_error)
        error_lines = self.preview_line_ids.filtered(lambda l: l.has_error)

        created = 0
        updated = 0
        skipped = len(error_lines)
        warnings = []

        for line in valid_lines:
            name = (line.name or '').strip()
            if not name:
                skipped += 1
                continue

            cat_ids, cat_bad = self._resolve_m2m_ids(
                'subject.category', 'name', line.categories or '')
            sub_ids, sub_bad = self._resolve_m2m_ids(
                'subject.master', 'name', line.subjects or '')
            grade_ids, grade_bad = self._resolve_m2m_ids(
                'grade.master', 'name', line.grades or '')

            for label, bad in [('Categories', cat_bad),
                                ('Subjects', sub_bad),
                                ('Grades', grade_bad)]:
                if bad:
                    warnings.append(
                        "Row %d (%s): %s not found — ignored: %s"
                        % (line.row_num, name, label, ', '.join(bad))
                    )

            vals = {
                'name': name,
                'email': (line.email or '').strip() or False,
                'country_code': (line.country_code or '+1').strip(),
                'phone': (line.phone or '').strip() or False,
                'timezone': (line.timezone or 'UTC').strip(),
                'status': line.status or 'active',
                'category_ids': [(6, 0, cat_ids)],
                'subject_ids': [(6, 0, sub_ids)],
                'grade_ids': [(6, 0, grade_ids)],
            }

            try:
                existing = self._find_existing(vals.get('email'), name)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    self.env['tutor.profile'].create(vals)
                    created += 1
            except Exception as exc:
                warnings.append(
                    "Row %d (%s): Error — %s" % (line.row_num, name, str(exc)))
                skipped += 1

        for line in error_lines:
            warnings.append(
                "Row %d (%s): Skipped — %s"
                % (line.row_num, line.name or '?', line.warning or 'validation error')
            )

        log_lines = [
            "✅ Import complete.",
            "   Created : %d" % created,
            "   Updated : %d" % updated,
            "   Skipped : %d" % skipped,
        ]
        if warnings:
            log_lines += ["", "⚠️  Warnings (%d):" % len(warnings)]
            log_lines += ["   • " + w for w in warnings]

        self.write({
            'result_log': '\n'.join(log_lines),
            'state': 'import_done',
        })
        return self._reopen()

    # ── Reset ─────────────────────────────────────────────────────────────────

    def action_reset(self):
        self.preview_line_ids.unlink()
        self.write({
            'import_file': False,
            'import_filename': False,
            'output_file': False,
            'output_filename': False,
            'result_log': False,
            'state': 'ready',
        })
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

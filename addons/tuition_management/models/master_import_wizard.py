# -*- coding: utf-8 -*-
import base64
import csv
import io

from odoo import api, fields, models
from odoo.exceptions import UserError


# ═══════════════════════════════════════════════════════════════════════════════
#  SUBJECT CATEGORY  Import / Export
# ═══════════════════════════════════════════════════════════════════════════════

SC_COLUMNS = [
    ('Category Name', 'name',        'char', 'Required'),
    ('Description',   'description', 'char', ''),
    ('Grades',        'grades',      'm2m',  'Pipe-separated e.g. Grade 9|Grade 10'),
]
SC_HEADERS = [c[0] for c in SC_COLUMNS]
SC_EXAMPLE = ['Mathematics', 'Core mathematics curriculum', 'Grade 9|Grade 10']


class SubjectCategoryImportWizardLine(models.TransientModel):
    _name = 'subject.category.import.wizard.line'
    _description = 'Subject Category Import Preview Line'
    _order = 'row_num'

    wizard_id = fields.Many2one('subject.category.import.wizard', ondelete='cascade')
    row_num = fields.Integer(string='Row #', readonly=True)
    name = fields.Char(string='Category Name')
    description = fields.Char(string='Description')
    grades = fields.Char(string='Grades', help='Pipe-separated grade names')
    action = fields.Selection([('create', 'Create'), ('update', 'Update')],
                              string='Action', readonly=True)
    warning = fields.Char(string='Notes / Warnings', readonly=True)
    has_error = fields.Boolean(readonly=True)


class SubjectCategoryImportWizard(models.TransientModel):
    _name = 'subject.category.import.wizard'
    _description = 'Subject Category Import / Export Wizard'

    import_file = fields.Binary(string='Upload CSV File', attachment=False)
    import_filename = fields.Char()
    preview_line_ids = fields.One2many(
        'subject.category.import.wizard.line', 'wizard_id', string='Preview')
    preview_count = fields.Integer(compute='_compute_stats')
    preview_create_count = fields.Integer(compute='_compute_stats')
    preview_update_count = fields.Integer(compute='_compute_stats')
    preview_error_count = fields.Integer(compute='_compute_stats')
    output_file = fields.Binary(attachment=False)
    output_filename = fields.Char()
    result_log = fields.Text(readonly=True)
    state = fields.Selection(
        [('ready', 'Ready'), ('preview', 'Preview'),
         ('export_done', 'Download Ready'), ('import_done', 'Import Done')],
        default='ready', readonly=True)

    @api.depends('preview_line_ids', 'preview_line_ids.action', 'preview_line_ids.has_error')
    def _compute_stats(self):
        for rec in self:
            lines = rec.preview_line_ids
            rec.preview_count = len(lines)
            rec.preview_create_count = len(lines.filtered(lambda l: l.action == 'create'))
            rec.preview_update_count = len(lines.filtered(lambda l: l.action == 'update'))
            rec.preview_error_count = len(lines.filtered(lambda l: l.has_error))

    def _build_csv(self, rows):
        buf = io.StringIO()
        csv.writer(buf, quoting=csv.QUOTE_MINIMAL).writerows(rows)
        return base64.b64encode(buf.getvalue().encode('utf-8'))

    def _resolve_grade_ids(self, names_str):
        if not names_str or not names_str.strip():
            return [], []
        ids, unresolved = [], []
        for nm in names_str.split('|'):
            nm = nm.strip()
            if not nm:
                continue
            rec = self.env['grade.master'].search([('name', '=ilike', nm)], limit=1)
            if rec:
                ids.append(rec.id)
            else:
                unresolved.append(nm)
        return ids, unresolved

    def _find_existing(self, name):
        if not name:
            return self.env['subject.category']
        return self.env['subject.category'].search([('name', '=ilike', name)], limit=1)

    def action_download_template(self):
        notes = ['# ' + c[3] for c in SC_COLUMNS]
        self.write({
            'output_file': self._build_csv([SC_HEADERS, notes, SC_EXAMPLE]),
            'output_filename': 'subject_category_import_template.csv',
            'state': 'export_done',
        })
        return self._reopen()

    def action_export(self):
        records = self.env['subject.category'].search([], order='name')
        rows = [SC_HEADERS] + [
            [r.name or '', r.description or '',
             '|'.join(g.name for g in r.grade_ids)]
            for r in records
        ]
        self.write({
            'output_file': self._build_csv(rows),
            'output_filename': 'subject_categories_export.csv',
            'state': 'export_done',
        })
        return self._reopen()

    def action_preview(self):
        if not self.import_file:
            raise UserError("Please upload a CSV file first.")
        try:
            text = base64.b64decode(self.import_file).decode('utf-8-sig')
        except Exception as exc:
            raise UserError("Could not read the file:\n%s" % str(exc))

        reader = csv.DictReader(io.StringIO(text))
        missing = set(SC_HEADERS) - set(reader.fieldnames or [])
        if missing:
            raise UserError("Missing columns:\n  %s\n\nUse the template."
                            % ', '.join(sorted(missing)))

        self.preview_line_ids.unlink()
        line_vals = []
        for row_num, row in enumerate(reader, start=2):
            name = (row.get('Category Name') or '').strip()
            if name.startswith('#'):
                continue
            warnings, has_error = [], False
            if not name:
                warnings.append("Category Name is required.")
                has_error = True

            grades_str = (row.get('Grades') or '').strip()
            if grades_str:
                _, unresolved = self._resolve_grade_ids(grades_str)
                if unresolved:
                    warnings.append("Grades not found: %s" % ', '.join(unresolved))

            existing = self._find_existing(name)
            line_vals.append({
                'wizard_id': self.id,
                'row_num': row_num,
                'name': name or False,
                'description': (row.get('Description') or '').strip() or False,
                'grades': grades_str or False,
                'action': 'update' if existing else 'create',
                'warning': ' | '.join(warnings) if warnings else False,
                'has_error': has_error,
            })

        if not line_vals:
            raise UserError("No data rows found.")
        self.env['subject.category.import.wizard.line'].create(line_vals)
        self.state = 'preview'
        return self._reopen()

    def action_confirm_import(self):
        valid = self.preview_line_ids.filtered(lambda l: not l.has_error)
        error = self.preview_line_ids.filtered(lambda l: l.has_error)
        created = updated = 0
        skipped = len(error)
        warnings = []

        for line in valid:
            name = (line.name or '').strip()
            if not name:
                skipped += 1
                continue
            grade_ids, bad = self._resolve_grade_ids(line.grades or '')
            if bad:
                warnings.append("Row %d (%s): Grades not found — %s"
                                % (line.row_num, name, ', '.join(bad)))
            vals = {
                'name': name,
                'description': (line.description or '').strip() or False,
                'grade_ids': [(6, 0, grade_ids)],
            }
            try:
                existing = self._find_existing(name)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    self.env['subject.category'].create(vals)
                    created += 1
            except Exception as exc:
                warnings.append("Row %d (%s): Error — %s" % (line.row_num, name, str(exc)))
                skipped += 1

        for line in error:
            warnings.append("Row %d (%s): Skipped — %s"
                            % (line.row_num, line.name or '?', line.warning or 'error'))

        log = ["✅ Import complete.",
               "   Created : %d" % created,
               "   Updated : %d" % updated,
               "   Skipped : %d" % skipped]
        if warnings:
            log += ["", "⚠️  Warnings (%d):" % len(warnings)]
            log += ["   • " + w for w in warnings]

        self.write({'result_log': '\n'.join(log), 'state': 'import_done'})
        return self._reopen()

    def action_reset(self):
        self.preview_line_ids.unlink()
        self.write({
            'import_file': False, 'import_filename': False,
            'output_file': False, 'output_filename': False,
            'result_log': False, 'state': 'ready',
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


# ═══════════════════════════════════════════════════════════════════════════════
#  SUBJECT  Import / Export
# ═══════════════════════════════════════════════════════════════════════════════

SUB_COLUMNS = [
    ('Subject Name', 'name',        'char', 'Required'),
    ('Category',     'category',    'char', 'Required – must match an existing Subject Category'),
    ('Description',  'description', 'char', ''),
]
SUB_HEADERS = [c[0] for c in SUB_COLUMNS]
SUB_EXAMPLE = ['Calculus', 'Mathematics', 'Differential and integral calculus']


class SubjectImportWizardLine(models.TransientModel):
    _name = 'subject.import.wizard.line'
    _description = 'Subject Import Preview Line'
    _order = 'row_num'

    wizard_id = fields.Many2one('subject.import.wizard', ondelete='cascade')
    row_num = fields.Integer(string='Row #', readonly=True)
    name = fields.Char(string='Subject Name')
    category = fields.Char(string='Category')
    description = fields.Char(string='Description')
    action = fields.Selection([('create', 'Create'), ('update', 'Update')],
                              string='Action', readonly=True)
    warning = fields.Char(string='Notes / Warnings', readonly=True)
    has_error = fields.Boolean(readonly=True)


class SubjectImportWizard(models.TransientModel):
    _name = 'subject.import.wizard'
    _description = 'Subject Import / Export Wizard'

    import_file = fields.Binary(string='Upload CSV File', attachment=False)
    import_filename = fields.Char()
    preview_line_ids = fields.One2many(
        'subject.import.wizard.line', 'wizard_id', string='Preview')
    preview_count = fields.Integer(compute='_compute_stats')
    preview_create_count = fields.Integer(compute='_compute_stats')
    preview_update_count = fields.Integer(compute='_compute_stats')
    preview_error_count = fields.Integer(compute='_compute_stats')
    output_file = fields.Binary(attachment=False)
    output_filename = fields.Char()
    result_log = fields.Text(readonly=True)
    state = fields.Selection(
        [('ready', 'Ready'), ('preview', 'Preview'),
         ('export_done', 'Download Ready'), ('import_done', 'Import Done')],
        default='ready', readonly=True)

    @api.depends('preview_line_ids', 'preview_line_ids.action', 'preview_line_ids.has_error')
    def _compute_stats(self):
        for rec in self:
            lines = rec.preview_line_ids
            rec.preview_count = len(lines)
            rec.preview_create_count = len(lines.filtered(lambda l: l.action == 'create'))
            rec.preview_update_count = len(lines.filtered(lambda l: l.action == 'update'))
            rec.preview_error_count = len(lines.filtered(lambda l: l.has_error))

    def _build_csv(self, rows):
        buf = io.StringIO()
        csv.writer(buf, quoting=csv.QUOTE_MINIMAL).writerows(rows)
        return base64.b64encode(buf.getvalue().encode('utf-8'))

    def _find_category(self, name):
        if not name:
            return self.env['subject.category']
        return self.env['subject.category'].search([('name', '=ilike', name)], limit=1)

    def _find_existing(self, name, category_id):
        if not name or not category_id:
            return self.env['subject.master']
        return self.env['subject.master'].search(
            [('name', '=ilike', name), ('category_id', '=', category_id)], limit=1)

    def action_download_template(self):
        notes = ['# ' + c[3] for c in SUB_COLUMNS]
        self.write({
            'output_file': self._build_csv([SUB_HEADERS, notes, SUB_EXAMPLE]),
            'output_filename': 'subject_import_template.csv',
            'state': 'export_done',
        })
        return self._reopen()

    def action_export(self):
        records = self.env['subject.master'].search([], order='category_id, name')
        rows = [SUB_HEADERS] + [
            [r.name or '', r.category_id.name or '', r.description or '']
            for r in records
        ]
        self.write({
            'output_file': self._build_csv(rows),
            'output_filename': 'subjects_export.csv',
            'state': 'export_done',
        })
        return self._reopen()

    def action_preview(self):
        if not self.import_file:
            raise UserError("Please upload a CSV file first.")
        try:
            text = base64.b64decode(self.import_file).decode('utf-8-sig')
        except Exception as exc:
            raise UserError("Could not read the file:\n%s" % str(exc))

        reader = csv.DictReader(io.StringIO(text))
        missing = set(SUB_HEADERS) - set(reader.fieldnames or [])
        if missing:
            raise UserError("Missing columns:\n  %s\n\nUse the template."
                            % ', '.join(sorted(missing)))

        self.preview_line_ids.unlink()
        line_vals = []
        for row_num, row in enumerate(reader, start=2):
            name = (row.get('Subject Name') or '').strip()
            if name.startswith('#'):
                continue
            category_str = (row.get('Category') or '').strip()
            warnings, has_error = [], False

            if not name:
                warnings.append("Subject Name is required.")
                has_error = True
            if not category_str:
                warnings.append("Category is required.")
                has_error = True
            else:
                cat = self._find_category(category_str)
                if not cat:
                    warnings.append("Category '%s' not found." % category_str)
                    has_error = True

            cat = self._find_category(category_str) if category_str else self.env['subject.category']
            existing = self._find_existing(name, cat.id) if name and cat else self.env['subject.master']

            line_vals.append({
                'wizard_id': self.id,
                'row_num': row_num,
                'name': name or False,
                'category': category_str or False,
                'description': (row.get('Description') or '').strip() or False,
                'action': 'update' if existing else 'create',
                'warning': ' | '.join(warnings) if warnings else False,
                'has_error': has_error,
            })

        if not line_vals:
            raise UserError("No data rows found.")
        self.env['subject.import.wizard.line'].create(line_vals)
        self.state = 'preview'
        return self._reopen()

    def action_confirm_import(self):
        valid = self.preview_line_ids.filtered(lambda l: not l.has_error)
        error = self.preview_line_ids.filtered(lambda l: l.has_error)
        created = updated = 0
        skipped = len(error)
        warnings = []

        for line in valid:
            name = (line.name or '').strip()
            if not name:
                skipped += 1
                continue
            cat = self._find_category(line.category or '')
            if not cat:
                warnings.append("Row %d (%s): Category '%s' not found — skipped."
                                % (line.row_num, name, line.category or ''))
                skipped += 1
                continue
            vals = {
                'name': name,
                'category_id': cat.id,
                'description': (line.description or '').strip() or False,
            }
            try:
                existing = self._find_existing(name, cat.id)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    self.env['subject.master'].create(vals)
                    created += 1
            except Exception as exc:
                warnings.append("Row %d (%s): Error — %s" % (line.row_num, name, str(exc)))
                skipped += 1

        for line in error:
            warnings.append("Row %d (%s): Skipped — %s"
                            % (line.row_num, line.name or '?', line.warning or 'error'))

        log = ["✅ Import complete.",
               "   Created : %d" % created,
               "   Updated : %d" % updated,
               "   Skipped : %d" % skipped]
        if warnings:
            log += ["", "⚠️  Warnings (%d):" % len(warnings)]
            log += ["   • " + w for w in warnings]

        self.write({'result_log': '\n'.join(log), 'state': 'import_done'})
        return self._reopen()

    def action_reset(self):
        self.preview_line_ids.unlink()
        self.write({
            'import_file': False, 'import_filename': False,
            'output_file': False, 'output_filename': False,
            'result_log': False, 'state': 'ready',
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


# ═══════════════════════════════════════════════════════════════════════════════
#  GRADE  Import / Export
# ═══════════════════════════════════════════════════════════════════════════════

GR_COLUMNS = [
    ('Grade Name',  'name',       'char', 'Required'),
    ('Sequence',    'sequence',   'char', 'Integer, default 10'),
    ('Categories',  'categories', 'm2m',  'Pipe-separated e.g. Mathematics|Science'),
]
GR_HEADERS = [c[0] for c in GR_COLUMNS]
GR_EXAMPLE = ['Grade 10', '10', 'Mathematics|Science']


class GradeImportWizardLine(models.TransientModel):
    _name = 'grade.import.wizard.line'
    _description = 'Grade Import Preview Line'
    _order = 'row_num'

    wizard_id = fields.Many2one('grade.import.wizard', ondelete='cascade')
    row_num = fields.Integer(string='Row #', readonly=True)
    name = fields.Char(string='Grade Name')
    sequence = fields.Char(string='Sequence')
    categories = fields.Char(string='Categories', help='Pipe-separated category names')
    action = fields.Selection([('create', 'Create'), ('update', 'Update')],
                              string='Action', readonly=True)
    warning = fields.Char(string='Notes / Warnings', readonly=True)
    has_error = fields.Boolean(readonly=True)


class GradeImportWizard(models.TransientModel):
    _name = 'grade.import.wizard'
    _description = 'Grade Import / Export Wizard'

    import_file = fields.Binary(string='Upload CSV File', attachment=False)
    import_filename = fields.Char()
    preview_line_ids = fields.One2many(
        'grade.import.wizard.line', 'wizard_id', string='Preview')
    preview_count = fields.Integer(compute='_compute_stats')
    preview_create_count = fields.Integer(compute='_compute_stats')
    preview_update_count = fields.Integer(compute='_compute_stats')
    preview_error_count = fields.Integer(compute='_compute_stats')
    output_file = fields.Binary(attachment=False)
    output_filename = fields.Char()
    result_log = fields.Text(readonly=True)
    state = fields.Selection(
        [('ready', 'Ready'), ('preview', 'Preview'),
         ('export_done', 'Download Ready'), ('import_done', 'Import Done')],
        default='ready', readonly=True)

    @api.depends('preview_line_ids', 'preview_line_ids.action', 'preview_line_ids.has_error')
    def _compute_stats(self):
        for rec in self:
            lines = rec.preview_line_ids
            rec.preview_count = len(lines)
            rec.preview_create_count = len(lines.filtered(lambda l: l.action == 'create'))
            rec.preview_update_count = len(lines.filtered(lambda l: l.action == 'update'))
            rec.preview_error_count = len(lines.filtered(lambda l: l.has_error))

    def _build_csv(self, rows):
        buf = io.StringIO()
        csv.writer(buf, quoting=csv.QUOTE_MINIMAL).writerows(rows)
        return base64.b64encode(buf.getvalue().encode('utf-8'))

    def _resolve_category_ids(self, names_str):
        if not names_str or not names_str.strip():
            return [], []
        ids, unresolved = [], []
        for nm in names_str.split('|'):
            nm = nm.strip()
            if not nm:
                continue
            rec = self.env['subject.category'].search([('name', '=ilike', nm)], limit=1)
            if rec:
                ids.append(rec.id)
            else:
                unresolved.append(nm)
        return ids, unresolved

    def _find_existing(self, name):
        if not name:
            return self.env['grade.master']
        return self.env['grade.master'].search([('name', '=ilike', name)], limit=1)

    def action_download_template(self):
        notes = ['# ' + c[3] for c in GR_COLUMNS]
        self.write({
            'output_file': self._build_csv([GR_HEADERS, notes, GR_EXAMPLE]),
            'output_filename': 'grade_import_template.csv',
            'state': 'export_done',
        })
        return self._reopen()

    def action_export(self):
        records = self.env['grade.master'].search([], order='sequence, name')
        rows = [GR_HEADERS] + [
            [r.name or '', str(r.sequence), '|'.join(c.name for c in r.category_ids)]
            for r in records
        ]
        self.write({
            'output_file': self._build_csv(rows),
            'output_filename': 'grades_export.csv',
            'state': 'export_done',
        })
        return self._reopen()

    def action_preview(self):
        if not self.import_file:
            raise UserError("Please upload a CSV file first.")
        try:
            text = base64.b64decode(self.import_file).decode('utf-8-sig')
        except Exception as exc:
            raise UserError("Could not read the file:\n%s" % str(exc))

        reader = csv.DictReader(io.StringIO(text))
        missing = set(GR_HEADERS) - set(reader.fieldnames or [])
        if missing:
            raise UserError("Missing columns:\n  %s\n\nUse the template."
                            % ', '.join(sorted(missing)))

        self.preview_line_ids.unlink()
        line_vals = []
        for row_num, row in enumerate(reader, start=2):
            name = (row.get('Grade Name') or '').strip()
            if name.startswith('#'):
                continue
            warnings, has_error = [], False

            if not name:
                warnings.append("Grade Name is required.")
                has_error = True

            seq_str = (row.get('Sequence') or '10').strip()
            try:
                int(seq_str)
            except ValueError:
                warnings.append("Sequence '%s' is not an integer — will use 10." % seq_str)
                seq_str = '10'

            cats_str = (row.get('Categories') or '').strip()
            if cats_str:
                _, unresolved = self._resolve_category_ids(cats_str)
                if unresolved:
                    warnings.append("Categories not found: %s" % ', '.join(unresolved))

            existing = self._find_existing(name)
            line_vals.append({
                'wizard_id': self.id,
                'row_num': row_num,
                'name': name or False,
                'sequence': seq_str,
                'categories': cats_str or False,
                'action': 'update' if existing else 'create',
                'warning': ' | '.join(warnings) if warnings else False,
                'has_error': has_error,
            })

        if not line_vals:
            raise UserError("No data rows found.")
        self.env['grade.import.wizard.line'].create(line_vals)
        self.state = 'preview'
        return self._reopen()

    def action_confirm_import(self):
        valid = self.preview_line_ids.filtered(lambda l: not l.has_error)
        error = self.preview_line_ids.filtered(lambda l: l.has_error)
        created = updated = 0
        skipped = len(error)
        warnings = []

        for line in valid:
            name = (line.name or '').strip()
            if not name:
                skipped += 1
                continue
            try:
                seq = int(line.sequence or '10')
            except ValueError:
                seq = 10
            cat_ids, bad = self._resolve_category_ids(line.categories or '')
            if bad:
                warnings.append("Row %d (%s): Categories not found — %s"
                                % (line.row_num, name, ', '.join(bad)))
            vals = {
                'name': name,
                'sequence': seq,
                'category_ids': [(6, 0, cat_ids)],
            }
            try:
                existing = self._find_existing(name)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    self.env['grade.master'].create(vals)
                    created += 1
            except Exception as exc:
                warnings.append("Row %d (%s): Error — %s" % (line.row_num, name, str(exc)))
                skipped += 1

        for line in error:
            warnings.append("Row %d (%s): Skipped — %s"
                            % (line.row_num, line.name or '?', line.warning or 'error'))

        log = ["✅ Import complete.",
               "   Created : %d" % created,
               "   Updated : %d" % updated,
               "   Skipped : %d" % skipped]
        if warnings:
            log += ["", "⚠️  Warnings (%d):" % len(warnings)]
            log += ["   • " + w for w in warnings]

        self.write({'result_log': '\n'.join(log), 'state': 'import_done'})
        return self._reopen()

    def action_reset(self):
        self.preview_line_ids.unlink()
        self.write({
            'import_file': False, 'import_filename': False,
            'output_file': False, 'output_filename': False,
            'result_log': False, 'state': 'ready',
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

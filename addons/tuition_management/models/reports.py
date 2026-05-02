# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

from odoo import api, fields, models, tools
from odoo.exceptions import UserError


class TuitionReportMixin(models.AbstractModel):
    _name = 'tuition.report.mixin'
    _description = 'Tuition Report Drill-down Helpers'

    def _date_domain(self):
        self.ensure_one()
        start = datetime.combine(self.report_date, time.min)
        end = start + timedelta(days=1)
        return [('start_datetime', '>=', start), ('start_datetime', '<', end)]

    def _dimension_domain(self):
        return []

    def _occurrence_action(self, name, metric_domain):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'class.schedule.occurrence',
            'view_mode': 'list,form,calendar',
            'domain': self._date_domain() + self._dimension_domain() + metric_domain,
            'context': {'create': False},
        }

    def action_open_scheduled_classes(self):
        return self._occurrence_action('Scheduled Classes', [('is_demo', '=', False)])

    def action_open_demos(self):
        return self._occurrence_action('Demo Classes', [('is_demo', '=', True)])

    def action_open_completed_classes(self):
        return self._occurrence_action(
            'Completed Classes',
            [('is_demo', '=', False), ('lesson_status', '=', 'completed')],
        )

    def action_open_cancelled_classes(self):
        return self._occurrence_action(
            'Cancelled Classes',
            [('is_demo', '=', False), ('lesson_status', '=', 'cancelled')],
        )

    def action_open_rescheduled_classes(self):
        return self._occurrence_action(
            'Rescheduled Classes',
            [('is_demo', '=', False), '|', ('is_rescheduled', '=', True), ('lesson_status', '=', 'rescheduled')],
        )

    def action_open_effective_classes(self):
        return self._occurrence_action(
            'Effective Classes',
            [
                '|',
                '&', ('is_demo', '=', False), ('lesson_status', '=', 'completed'),
                '&', ('is_demo', '=', True), ('lesson_status', '!=', 'cancelled'),
            ],
        )

    def action_open_total_sessions(self):
        return self._occurrence_action('Total Sessions', [])

    def action_open_happened_classes(self):
        return self.action_open_completed_classes()

    def action_open_billable_classes(self):
        return self.action_open_completed_classes()

    def init(self):
        self.env.cr.execute(
            """
            CREATE INDEX IF NOT EXISTS tuition_report_occurrence_start_idx
                ON class_schedule_occurrence (start_datetime);
            CREATE INDEX IF NOT EXISTS tuition_report_occurrence_course_idx
                ON class_schedule_occurrence (course_id);
            CREATE INDEX IF NOT EXISTS tuition_report_occurrence_tutor_idx
                ON class_schedule_occurrence (tutor_id);
            CREATE INDEX IF NOT EXISTS tuition_report_occurrence_metrics_idx
                ON class_schedule_occurrence (lesson_status, is_demo, is_rescheduled);
            """
        )


class TuitionClassStatusReport(models.Model):
    _name = 'tuition.class.status.report'
    _description = 'Class Status Report'
    _inherit = 'tuition.report.mixin'
    _auto = False
    _order = 'report_date desc'

    report_date = fields.Date(string='Class Date', readonly=True)
    total_scheduled_classes = fields.Integer(string='Scheduled Classes', readonly=True)
    total_demos = fields.Integer(string='Demos', readonly=True)
    completed_classes = fields.Integer(string='Completed Classes', readonly=True)
    cancelled_classes = fields.Integer(string='Cancelled Classes', readonly=True)
    rescheduled_classes = fields.Integer(string='Rescheduled Classes', readonly=True)
    happened_classes = fields.Integer(string='Classes Happened', readonly=True)
    billable_actual_classes = fields.Integer(string='Billable Actual Classes', readonly=True)

    def init(self):
        super().init()
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW tuition_class_status_report AS (
                SELECT
                    ((occ.start_datetime::date - DATE '1970-01-01')::integer + 1) AS id,
                    occ.start_datetime::date AS report_date,
                    COUNT(*) FILTER (WHERE NOT COALESCE(occ.is_demo, FALSE))::integer AS total_scheduled_classes,
                    COUNT(*) FILTER (WHERE COALESCE(occ.is_demo, FALSE))::integer AS total_demos,
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status = 'completed'
                    )::integer AS completed_classes,
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status = 'cancelled'
                    )::integer AS cancelled_classes,
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND (COALESCE(occ.is_rescheduled, FALSE) OR occ.lesson_status = 'rescheduled')
                    )::integer AS rescheduled_classes,
                    (
                        COUNT(*) FILTER (
                            WHERE NOT COALESCE(occ.is_demo, FALSE)
                              AND occ.lesson_status = 'completed'
                        )
                        - COUNT(*) FILTER (
                            WHERE NOT COALESCE(occ.is_demo, FALSE)
                              AND occ.lesson_status = 'cancelled'
                        )
                    )::integer AS happened_classes,
                    (
                        COUNT(*) FILTER (
                            WHERE NOT COALESCE(occ.is_demo, FALSE)
                              AND occ.lesson_status = 'completed'
                        )
                        - COUNT(*) FILTER (
                            WHERE NOT COALESCE(occ.is_demo, FALSE)
                              AND occ.lesson_status = 'cancelled'
                        )
                    )::integer AS billable_actual_classes
                FROM class_schedule_occurrence occ
                WHERE occ.start_datetime IS NOT NULL
                GROUP BY occ.start_datetime::date
            )
            """
        )


class TuitionSubjectWiseReport(models.Model):
    _name = 'tuition.subject.wise.report'
    _description = 'Subject-wise Report'
    _inherit = 'tuition.report.mixin'
    _auto = False
    _order = 'category_id, subject_id, report_date desc'

    report_date = fields.Date(string='Class Date', readonly=True)
    category_id = fields.Many2one('subject.category', string='Category', readonly=True)
    subject_id = fields.Many2one('subject.master', string='Subject', readonly=True)
    total_classes = fields.Integer(string='Classes', readonly=True)
    total_demos = fields.Integer(string='Demos', readonly=True)
    total_sessions = fields.Integer(string='Total', readonly=True)

    def _dimension_domain(self):
        domain = []
        if self.category_id:
            domain += [
                '|',
                ('course_id.category_id', '=', self.category_id.id),
                '&', ('course_id.category_id', '=', False), ('course_id.subject_id.category_id', '=', self.category_id.id),
            ]
        if self.subject_id:
            domain.append(('course_id.subject_id', '=', self.subject_id.id))
        return domain

    def init(self):
        super().init()
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW tuition_subject_wise_report AS (
                WITH base AS (
                    SELECT
                        occ.start_datetime::date AS report_date,
                        COALESCE(course.category_id, subject.category_id) AS category_id,
                        course.subject_id AS subject_id,
                        COALESCE(occ.is_demo, FALSE) AS is_demo
                    FROM class_schedule_occurrence occ
                    JOIN course_master course ON course.id = occ.course_id
                    LEFT JOIN subject_master subject ON subject.id = course.subject_id
                    WHERE occ.start_datetime IS NOT NULL
                )
                SELECT
                    (
                        ('x' || substr(md5(
                            report_date::text || '-' || COALESCE(category_id::text, '0') || '-' || COALESCE(subject_id::text, '0')
                        ), 1, 8))::bit(32)::bigint % 2147483647
                    )::integer + 1 AS id,
                    report_date,
                    category_id,
                    subject_id,
                    COUNT(*) FILTER (WHERE NOT is_demo)::integer AS total_classes,
                    COUNT(*) FILTER (WHERE is_demo)::integer AS total_demos,
                    COUNT(*)::integer AS total_sessions
                FROM base
                GROUP BY report_date, category_id, subject_id
            )
            """
        )


class TuitionTutorWiseReport(models.Model):
    _name = 'tuition.tutor.wise.report'
    _description = 'Tutor-wise Report'
    _inherit = 'tuition.report.mixin'
    _auto = False
    _order = 'tutor_id, category_id, subject_id, report_date desc'

    report_date = fields.Date(string='Class Date', readonly=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', readonly=True)
    category_id = fields.Many2one('subject.category', string='Category', readonly=True)
    subject_id = fields.Many2one('subject.master', string='Subject', readonly=True)
    category_subject = fields.Char(string='Category + Subject', readonly=True)
    total_classes = fields.Integer(string='Classes', readonly=True)
    total_demos = fields.Integer(string='Demos', readonly=True)
    completed_classes = fields.Integer(string='Completed', readonly=True)
    cancelled_classes = fields.Integer(string='Cancelled', readonly=True)
    effective_classes = fields.Integer(string='Effective', readonly=True)

    def _dimension_domain(self):
        domain = []
        if self.tutor_id:
            domain.append(('tutor_id', '=', self.tutor_id.id))
        if self.category_id:
            domain += [
                '|',
                ('course_id.category_id', '=', self.category_id.id),
                '&', ('course_id.category_id', '=', False), ('course_id.subject_id.category_id', '=', self.category_id.id),
            ]
        if self.subject_id:
            domain.append(('course_id.subject_id', '=', self.subject_id.id))
        return domain

    def init(self):
        super().init()
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW tuition_tutor_wise_report AS (
                WITH base AS (
                    SELECT
                        occ.start_datetime::date AS report_date,
                        occ.tutor_id AS tutor_id,
                        COALESCE(course.category_id, subject.category_id) AS category_id,
                        course.subject_id AS subject_id,
                        COALESCE(category.name, 'Uncategorised') || ' - ' || COALESCE(subject.name, 'No Subject') AS category_subject,
                        COALESCE(occ.is_demo, FALSE) AS is_demo,
                        occ.lesson_status
                    FROM class_schedule_occurrence occ
                    JOIN course_master course ON course.id = occ.course_id
                    LEFT JOIN subject_master subject ON subject.id = course.subject_id
                    LEFT JOIN subject_category category ON category.id = COALESCE(course.category_id, subject.category_id)
                    WHERE occ.start_datetime IS NOT NULL
                )
                SELECT
                    (
                        ('x' || substr(md5(
                            report_date::text || '-' || COALESCE(tutor_id::text, '0') || '-'
                            || COALESCE(category_id::text, '0') || '-' || COALESCE(subject_id::text, '0')
                        ), 1, 8))::bit(32)::bigint % 2147483647
                    )::integer + 1 AS id,
                    report_date,
                    tutor_id,
                    category_id,
                    subject_id,
                    category_subject,
                    COUNT(*) FILTER (WHERE NOT is_demo)::integer AS total_classes,
                    COUNT(*) FILTER (WHERE is_demo)::integer AS total_demos,
                    COUNT(*) FILTER (WHERE NOT is_demo AND lesson_status = 'completed')::integer AS completed_classes,
                    COUNT(*) FILTER (WHERE NOT is_demo AND lesson_status = 'cancelled')::integer AS cancelled_classes,
                    (
                        COUNT(*) FILTER (WHERE NOT is_demo AND lesson_status = 'completed')
                        + COUNT(*) FILTER (WHERE is_demo)
                        - COUNT(*) FILTER (WHERE NOT is_demo AND lesson_status = 'cancelled')
                    )::integer AS effective_classes
                FROM base
                GROUP BY report_date, tutor_id, category_id, subject_id, category_subject
            )
            """
        )


class TuitionDateRangeWizardMixin(models.AbstractModel):
    _name = 'tuition.date.range.wizard.mixin'
    _description = 'Tuition Date Range Report Helpers'

    from_date = fields.Date(string='From Date', required=True)
    to_date = fields.Date(string='To Date', required=True, default=fields.Date.context_today)

    def _check_date_range(self):
        for rec in self:
            if rec.from_date and rec.to_date and rec.from_date > rec.to_date:
                raise UserError('From Date must be on or before To Date.')

    def _date_range_domain(self):
        self.ensure_one()
        self._check_date_range()
        return [
            ('start_datetime', '>=', datetime.combine(self.from_date, time.min)),
            ('start_datetime', '<=', datetime.combine(self.to_date, time.max)),
        ]

    def _subject_dimension_domain(self, category, subject):
        domain = []
        if category:
            domain += [
                '|',
                ('course_id.category_id', '=', category.id),
                '&',
                ('course_id.category_id', '=', False),
                ('course_id.subject_id.category_id', '=', category.id),
            ]
        if subject:
            domain.append(('course_id.subject_id', '=', subject.id))
        return domain

    def _open_occurrences(self, name, domain):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'class.schedule.occurrence',
            'view_mode': 'list,form,calendar',
            'domain': self._date_range_domain() + domain,
            'context': {'create': False},
        }


class TuitionClassStatusWizard(models.TransientModel):
    _name = 'tuition.class.status.wizard'
    _description = 'Class Status Report'
    _inherit = 'tuition.date.range.wizard.mixin'

    from_date = fields.Date(
        string='From Date',
        required=True,
        default=lambda self: fields.Date.context_today(self) - timedelta(days=30),
    )
    total_scheduled_classes = fields.Integer(string='Scheduled Classes', compute='_compute_totals')
    total_demos = fields.Integer(string='Demos', compute='_compute_totals')
    completed_classes = fields.Integer(string='Completed Classes', compute='_compute_totals')
    cancelled_classes = fields.Integer(string='Cancelled Classes', compute='_compute_totals')
    rescheduled_classes = fields.Integer(string='Rescheduled Classes', compute='_compute_totals')
    happened_classes = fields.Integer(string='Classes Happened', compute='_compute_totals')
    billable_actual_classes = fields.Integer(string='Billable Actual Classes', compute='_compute_totals')

    def _metric_domain(self, metric):
        metric_domains = {
            'scheduled': [('is_demo', '=', False)],
            'demos': [('is_demo', '=', True)],
            'completed': [('is_demo', '=', False), ('lesson_status', '=', 'completed')],
            'cancelled': [('is_demo', '=', False), ('lesson_status', '=', 'cancelled')],
            'rescheduled': [
                ('is_demo', '=', False),
                '|',
                ('is_rescheduled', '=', True),
                ('lesson_status', '=', 'rescheduled'),
            ],
            'happened': [('is_demo', '=', False), ('lesson_status', '=', 'completed')],
            'billable': [('is_demo', '=', False), ('lesson_status', '=', 'completed')],
        }
        return metric_domains[metric]

    @api.depends('from_date', 'to_date')
    def _compute_totals(self):
        Occurrence = self.env['class.schedule.occurrence']
        for rec in self:
            values = {
                'total_scheduled_classes': 0,
                'total_demos': 0,
                'completed_classes': 0,
                'cancelled_classes': 0,
                'rescheduled_classes': 0,
                'happened_classes': 0,
                'billable_actual_classes': 0,
            }
            if rec.from_date and rec.to_date and rec.from_date <= rec.to_date:
                base_domain = rec._date_range_domain()
                values['total_scheduled_classes'] = Occurrence.search_count(base_domain + rec._metric_domain('scheduled'))
                values['total_demos'] = Occurrence.search_count(base_domain + rec._metric_domain('demos'))
                values['completed_classes'] = Occurrence.search_count(base_domain + rec._metric_domain('completed'))
                values['cancelled_classes'] = Occurrence.search_count(base_domain + rec._metric_domain('cancelled'))
                values['rescheduled_classes'] = Occurrence.search_count(base_domain + rec._metric_domain('rescheduled'))
                values['happened_classes'] = values['completed_classes'] - values['cancelled_classes']
                values['billable_actual_classes'] = values['completed_classes'] - values['cancelled_classes']
            for field_name, value in values.items():
                rec[field_name] = value

    def action_refresh(self):
        self.ensure_one()
        self._check_date_range()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Class Status Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def _open_metric(self, metric, title):
        return self._open_occurrences(title, self._metric_domain(metric))

    def action_open_scheduled_classes(self):
        return self._open_metric('scheduled', 'Scheduled Classes')

    def action_open_demos(self):
        return self._open_metric('demos', 'Demos')

    def action_open_completed_classes(self):
        return self._open_metric('completed', 'Completed Classes')

    def action_open_cancelled_classes(self):
        return self._open_metric('cancelled', 'Cancelled Classes')

    def action_open_rescheduled_classes(self):
        return self._open_metric('rescheduled', 'Rescheduled Classes')

    def action_open_happened_classes(self):
        return self._open_metric('happened', 'Classes Happened')

    def action_open_billable_classes(self):
        return self._open_metric('billable', 'Billable Actual Classes')


class TuitionSubjectWiseWizard(models.TransientModel):
    _name = 'tuition.subject.wise.wizard'
    _description = 'Subject-wise Report'
    _inherit = 'tuition.date.range.wizard.mixin'

    from_date = fields.Date(
        string='From Date',
        required=True,
        default=lambda self: fields.Date.context_today(self) - timedelta(days=30),
    )
    line_ids = fields.One2many('tuition.subject.wise.wizard.line', 'wizard_id', string='Lines')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        from_date = fields.Date.to_date(vals.get('from_date')) or fields.Date.context_today(self) - timedelta(days=30)
        to_date = fields.Date.to_date(vals.get('to_date')) or fields.Date.context_today(self)
        if 'line_ids' in fields_list:
            vals['line_ids'] = [(0, 0, line) for line in self._get_line_values(from_date, to_date)]
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._refresh_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {'from_date', 'to_date'} & set(vals):
            self._refresh_lines()
        return res

    def _get_line_values(self, from_date, to_date):
        if from_date > to_date:
            return []
        self.env.cr.execute(
            """
            SELECT
                COALESCE(course.category_id, subject.category_id) AS category_id,
                course.subject_id AS subject_id,
                COUNT(*) FILTER (WHERE NOT COALESCE(occ.is_demo, FALSE))::integer AS total_classes,
                COUNT(*) FILTER (WHERE COALESCE(occ.is_demo, FALSE))::integer AS total_demos,
                COUNT(*)::integer AS total_sessions
            FROM class_schedule_occurrence occ
            JOIN course_master course ON course.id = occ.course_id
            LEFT JOIN subject_master subject ON subject.id = course.subject_id
            WHERE occ.start_datetime >= %s
              AND occ.start_datetime <= %s
            GROUP BY COALESCE(course.category_id, subject.category_id), course.subject_id
            ORDER BY COALESCE(course.category_id, subject.category_id), course.subject_id
            """,
            (
                datetime.combine(from_date, time.min),
                datetime.combine(to_date, time.max),
            ),
        )
        return [
            {
                'category_id': category_id,
                'subject_id': subject_id,
                'total_classes': total_classes,
                'total_demos': total_demos,
                'total_sessions': total_sessions,
            }
            for category_id, subject_id, total_classes, total_demos, total_sessions in self.env.cr.fetchall()
        ]

    def _refresh_lines(self):
        for rec in self:
            rec._check_date_range()
            rec.line_ids.unlink()
            for line in self._get_line_values(rec.from_date, rec.to_date):
                line['wizard_id'] = rec.id
                self.env['tuition.subject.wise.wizard.line'].create(line)

    def action_refresh(self):
        self.ensure_one()
        self._refresh_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Subject-wise Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }


class TuitionSubjectWiseWizardLine(models.TransientModel):
    _name = 'tuition.subject.wise.wizard.line'
    _description = 'Subject-wise Report Line'
    _order = 'category_id, subject_id'

    wizard_id = fields.Many2one('tuition.subject.wise.wizard', required=True, ondelete='cascade')
    category_id = fields.Many2one('subject.category', string='Category', readonly=True)
    subject_id = fields.Many2one('subject.master', string='Subject', readonly=True)
    total_classes = fields.Integer(string='Classes', readonly=True)
    total_demos = fields.Integer(string='Demos', readonly=True)
    total_sessions = fields.Integer(string='Total', readonly=True)

    def _dimension_domain(self):
        self.ensure_one()
        return self.wizard_id._subject_dimension_domain(self.category_id, self.subject_id)

    def action_open_classes(self):
        return self.wizard_id._open_occurrences(
            'Subject Classes',
            self._dimension_domain() + [('is_demo', '=', False)],
        )

    def action_open_demos(self):
        return self.wizard_id._open_occurrences(
            'Subject Demos',
            self._dimension_domain() + [('is_demo', '=', True)],
        )

    def action_open_total(self):
        return self.wizard_id._open_occurrences('Subject Total Sessions', self._dimension_domain())


class TuitionTutorWiseWizard(models.TransientModel):
    _name = 'tuition.tutor.wise.wizard'
    _description = 'Tutor-wise Report'
    _inherit = 'tuition.date.range.wizard.mixin'

    from_date = fields.Date(
        string='From Date',
        required=True,
        default=lambda self: fields.Date.context_today(self) - timedelta(days=7),
    )
    line_ids = fields.One2many('tuition.tutor.wise.wizard.line', 'wizard_id', string='Lines')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        from_date = fields.Date.to_date(vals.get('from_date')) or fields.Date.context_today(self) - timedelta(days=7)
        to_date = fields.Date.to_date(vals.get('to_date')) or fields.Date.context_today(self)
        if 'line_ids' in fields_list:
            vals['line_ids'] = [(0, 0, line) for line in self._get_line_values(from_date, to_date)]
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._refresh_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {'from_date', 'to_date'} & set(vals):
            self._refresh_lines()
        return res

    def _get_line_values(self, from_date, to_date):
        if from_date > to_date:
            return []
        self.env.cr.execute(
            """
            SELECT
                occ.tutor_id,
                COALESCE(course.category_id, subject.category_id) AS category_id,
                course.subject_id,
                COALESCE(category.name, 'Uncategorised') || ' - ' || COALESCE(subject.name, 'No Subject') AS category_subject,
                COUNT(*) FILTER (WHERE NOT COALESCE(occ.is_demo, FALSE))::integer AS total_classes,
                COUNT(*) FILTER (WHERE COALESCE(occ.is_demo, FALSE))::integer AS total_demos,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND occ.lesson_status = 'completed'
                )::integer AS completed_classes,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND occ.lesson_status = 'cancelled'
                )::integer AS cancelled_classes,
                (
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status = 'completed'
                    )
                    + COUNT(*) FILTER (WHERE COALESCE(occ.is_demo, FALSE))
                    - COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status = 'cancelled'
                    )
                )::integer AS effective_classes
            FROM class_schedule_occurrence occ
            JOIN course_master course ON course.id = occ.course_id
            LEFT JOIN subject_master subject ON subject.id = course.subject_id
            LEFT JOIN subject_category category ON category.id = COALESCE(course.category_id, subject.category_id)
            WHERE occ.start_datetime >= %s
              AND occ.start_datetime <= %s
            GROUP BY
                occ.tutor_id,
                COALESCE(course.category_id, subject.category_id),
                course.subject_id,
                COALESCE(category.name, 'Uncategorised') || ' - ' || COALESCE(subject.name, 'No Subject')
            ORDER BY occ.tutor_id, category_subject
            """,
            (
                datetime.combine(from_date, time.min),
                datetime.combine(to_date, time.max),
            ),
        )
        return [
            {
                'tutor_id': tutor_id,
                'category_id': category_id,
                'subject_id': subject_id,
                'category_subject': category_subject,
                'total_classes': total_classes,
                'total_demos': total_demos,
                'completed_classes': completed_classes,
                'cancelled_classes': cancelled_classes,
                'effective_classes': effective_classes,
            }
            for (
                tutor_id,
                category_id,
                subject_id,
                category_subject,
                total_classes,
                total_demos,
                completed_classes,
                cancelled_classes,
                effective_classes,
            ) in self.env.cr.fetchall()
        ]

    def _refresh_lines(self):
        for rec in self:
            rec._check_date_range()
            rec.line_ids.unlink()
            for line in self._get_line_values(rec.from_date, rec.to_date):
                line['wizard_id'] = rec.id
                self.env['tuition.tutor.wise.wizard.line'].create(line)

    def action_refresh(self):
        self.ensure_one()
        self._refresh_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tutor-wise Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }


class TuitionTutorWiseWizardLine(models.TransientModel):
    _name = 'tuition.tutor.wise.wizard.line'
    _description = 'Tutor-wise Report Line'
    _order = 'tutor_id, category_subject'

    wizard_id = fields.Many2one('tuition.tutor.wise.wizard', required=True, ondelete='cascade')
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', readonly=True)
    category_id = fields.Many2one('subject.category', string='Category', readonly=True)
    subject_id = fields.Many2one('subject.master', string='Subject', readonly=True)
    category_subject = fields.Char(string='Category + Subject', readonly=True)
    total_classes = fields.Integer(string='Classes', readonly=True)
    total_demos = fields.Integer(string='Demos', readonly=True)
    completed_classes = fields.Integer(string='Completed', readonly=True)
    cancelled_classes = fields.Integer(string='Cancelled', readonly=True)
    effective_classes = fields.Integer(string='Effective', readonly=True)

    def _dimension_domain(self):
        self.ensure_one()
        domain = self.wizard_id._subject_dimension_domain(self.category_id, self.subject_id)
        if self.tutor_id:
            domain.append(('tutor_id', '=', self.tutor_id.id))
        return domain

    def action_open_classes(self):
        return self.wizard_id._open_occurrences(
            'Tutor Classes',
            self._dimension_domain() + [('is_demo', '=', False)],
        )

    def action_open_demos(self):
        return self.wizard_id._open_occurrences(
            'Tutor Demos',
            self._dimension_domain() + [('is_demo', '=', True)],
        )

    def action_open_completed(self):
        return self.wizard_id._open_occurrences(
            'Tutor Completed Classes',
            self._dimension_domain() + [('is_demo', '=', False), ('lesson_status', '=', 'completed')],
        )

    def action_open_cancelled(self):
        return self.wizard_id._open_occurrences(
            'Tutor Cancelled Classes',
            self._dimension_domain() + [('is_demo', '=', False), ('lesson_status', '=', 'cancelled')],
        )

    def action_open_effective(self):
        return self.wizard_id._open_occurrences(
            'Tutor Effective Classes',
            self._dimension_domain() + [
                '|',
                '&', ('is_demo', '=', False), ('lesson_status', '=', 'completed'),
                '&', ('is_demo', '=', True), ('lesson_status', '!=', 'cancelled'),
            ],
        )

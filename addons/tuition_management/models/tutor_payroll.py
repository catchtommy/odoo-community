# -*- coding: utf-8 -*-
from datetime import datetime, time

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class TutorSubjectRate(models.Model):
    _name = 'tutor.subject.rate'
    _description = 'Tutor Subject Rate'
    _order = 'tutor_id, category_id, subject_id, effective_from desc'

    tutor_id = fields.Many2one('tutor.profile', string='Tutor', required=True, ondelete='cascade')
    category_id = fields.Many2one('subject.category', string='Category', required=True)
    subject_id = fields.Many2one(
        'subject.master',
        string='Subject',
        required=True,
        domain="[('category_id', '=', category_id)]",
    )
    standard_hourly_rate = fields.Float(string='Standard Hourly Rate', required=True)
    demo_rate_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('custom', 'Custom'),
    ], string='Demo Rate Type', required=True, default='percentage')
    demo_percentage = fields.Float(string='Demo Percentage')
    demo_hourly_rate = fields.Float(string='Demo Hourly Rate')
    effective_from = fields.Date(string='Effective From', required=True, default=fields.Date.context_today)
    effective_to = fields.Date(string='Effective To')
    active_flag = fields.Boolean(string='Active', default=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    @api.onchange('category_id')
    def _onchange_category_id(self):
        self.subject_id = False
        return {'domain': {'subject_id': [('category_id', '=', self.category_id.id)] if self.category_id else []}}

    @api.constrains(
        'tutor_id', 'category_id', 'subject_id', 'standard_hourly_rate',
        'demo_rate_type', 'demo_percentage', 'demo_hourly_rate',
        'effective_from', 'effective_to', 'active_flag',
    )
    def _check_rate_rules(self):
        for rec in self:
            if rec.standard_hourly_rate <= 0:
                raise ValidationError("Standard hourly rate must be greater than zero.")
            if rec.subject_id and rec.category_id and rec.subject_id.category_id != rec.category_id:
                raise ValidationError("Subject must belong to the selected category.")
            if rec.effective_to and rec.effective_to < rec.effective_from:
                raise ValidationError("Effective To must be on or after Effective From.")
            if rec.demo_rate_type == 'percentage':
                if not rec.demo_percentage:
                    raise ValidationError("Demo percentage is required for percentage demo rates.")
                if rec.demo_percentage < 1 or rec.demo_percentage > 100:
                    raise ValidationError("Demo percentage must be between 1 and 100.")
            if rec.demo_rate_type == 'custom':
                if rec.demo_hourly_rate <= 0:
                    raise ValidationError("Demo hourly rate must be greater than zero for custom demo rates.")
            if rec.active_flag:
                overlap_domain = [
                    ('id', '!=', rec.id),
                    ('tutor_id', '=', rec.tutor_id.id),
                    ('category_id', '=', rec.category_id.id),
                    ('subject_id', '=', rec.subject_id.id),
                    ('active_flag', '=', True),
                    ('effective_from', '<=', rec.effective_to or fields.Date.to_date('9999-12-31')),
                    '|',
                    ('effective_to', '=', False),
                    ('effective_to', '>=', rec.effective_from),
                ]
                if self.search_count(overlap_domain):
                    raise ValidationError(
                        "An active tutor/category/subject rate already exists for an overlapping date range."
                    )


class CourseMasterTutorPricing(models.Model):
    _inherit = 'course.master'

    category_id = fields.Many2one('subject.category', string='Category')
    eligible_tutor_ids = fields.Many2many(
        'tutor.profile',
        string='Eligible Tutors',
        compute='_compute_eligible_tutors',
        store=False,
    )

    @api.onchange('category_id')
    def _onchange_category_id(self):
        self.subject_id = False
        self.tutor_id = False
        return {'domain': {'subject_id': [('category_id', '=', self.category_id.id)] if self.category_id else []}}

    @api.onchange('subject_id')
    def _onchange_subject_id_category(self):
        if self.subject_id and not self.category_id:
            self.category_id = self.subject_id.category_id
        self.tutor_id = False

    @api.depends('category_id', 'subject_id', 'start_date')
    def _compute_eligible_tutors(self):
        tutor_model = self.env['tutor.profile']
        for rec in self:
            rec.eligible_tutor_ids = tutor_model.get_eligible_tutors(
                rec.category_id,
                rec.subject_id,
                rec.start_date or fields.Date.today(),
            ) if rec.category_id and rec.subject_id else tutor_model.browse()

    @api.onchange('category_id', 'subject_id', 'eligible_tutor_ids')
    def _onchange_tutor_domain(self):
        tutor_ids = self.eligible_tutor_ids.ids
        return {'domain': {'tutor_id': [('id', 'in', tutor_ids)] if tutor_ids else []}}

    @api.constrains('category_id', 'subject_id', 'tutor_id', 'start_date')
    def _check_tutor_matches_course_matrix(self):
        for rec in self.filtered(lambda c: c.category_id and c.subject_id):
            if rec.subject_id.category_id != rec.category_id:
                raise ValidationError("Course subject must belong to the selected category.")
        for rec in self.filtered(lambda c: c.category_id and c.subject_id and c.tutor_id):
            eligible = self.env['tutor.profile'].get_eligible_tutors(
                rec.category_id,
                rec.subject_id,
                rec.start_date or fields.Date.today(),
            )
            if rec.tutor_id not in eligible:
                raise ValidationError("Selected tutor is not configured for this course category and subject.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('subject_id') and not vals.get('category_id'):
                subject = self.env['subject.master'].browse(vals['subject_id'])
                vals['category_id'] = subject.category_id.id if subject.category_id else False
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('subject_id') and not vals.get('category_id'):
            subject = self.env['subject.master'].browse(vals['subject_id'])
            vals = dict(vals, category_id=subject.category_id.id if subject.category_id else False)
        return super().write(vals)


class ClassScheduleOccurrenceTutorPayment(models.Model):
    _inherit = 'class.schedule.occurrence'

    tutor_rate_used = fields.Float(string='Tutor Rate Used', readonly=True, copy=False)
    payable_hours = fields.Float(string='Payable Hours', readonly=True, copy=False)
    tutor_calculated_amount = fields.Float(string='Tutor Calculated Amount', readonly=True, copy=False)
    tutor_payment_line_id = fields.Many2one(
        'tutor.payment.line',
        string='Tutor Payment Line',
        readonly=True,
        copy=False,
        ondelete='set null',
    )
    tutor_payment_status = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
    ], string='Tutor Payment Status', readonly=True, copy=False)


class TutorPaymentEngine(models.AbstractModel):
    _name = 'tutor.payment.engine'
    _description = 'Tutor Payment Calculation Engine'

    @api.model
    def resolve_tutor_rate(self, tutor, category, subject, is_demo=False, lesson_date=None):
        lesson_date = fields.Date.to_date(lesson_date) if lesson_date else fields.Date.today()
        rate = self.env['tutor.subject.rate'].search([
            ('tutor_id', '=', tutor.id),
            ('category_id', '=', category.id),
            ('subject_id', '=', subject.id),
            ('active_flag', '=', True),
            ('effective_from', '<=', lesson_date),
            '|', ('effective_to', '=', False), ('effective_to', '>=', lesson_date),
        ], order='effective_from desc, id desc', limit=1)
        if not rate:
            raise UserError(
                "No tutor rate is configured for %s / %s / %s on %s."
                % (tutor.display_name, category.display_name, subject.display_name, lesson_date)
            )
        if not is_demo:
            return rate, rate.standard_hourly_rate
        if rate.demo_rate_type == 'percentage':
            return rate, rate.standard_hourly_rate * (rate.demo_percentage / 100.0)
        return rate, rate.demo_hourly_rate

    @api.model
    def resolveTutorRate(self, tutor, category, subject, isDemo=False, lessonDate=None):
        return self.resolve_tutor_rate(tutor, category, subject, isDemo, lessonDate)

    @api.model
    def get_lesson_hours(self, lesson):
        start = lesson.start_datetime
        stop = lesson.stop_datetime or getattr(lesson, 'end_datetime', False)
        if not start or not stop or stop <= start:
            return 0.0
        return (stop - start).total_seconds() / 3600.0

    @api.model
    def calculate_lesson_payment(self, lesson):
        course = lesson.course_id
        category = course.category_id or course.subject_id.category_id
        if not lesson.tutor_id or not course or not category or not course.subject_id:
            raise UserError("Lesson %s is missing tutor, category, or subject for payroll." % lesson.display_name)
        rate_record, hourly_rate = self.resolve_tutor_rate(
            lesson.tutor_id,
            category,
            course.subject_id,
            lesson.is_demo,
            lesson.start_datetime.date() if lesson.start_datetime else fields.Date.today(),
        )
        hours = self.get_lesson_hours(lesson)
        if hours <= 0:
            raise UserError("Lesson %s has no payable duration." % lesson.display_name)
        return {
            'rate_record': rate_record,
            'category': category,
            'subject': course.subject_id,
            'hours': hours,
            'rate_used': hourly_rate,
            'amount': hours * hourly_rate,
        }


class TutorPaymentRun(models.Model):
    _name = 'tutor.payment.run'
    _description = 'Tutor Payroll Run'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'payment_period_from desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    payment_period_from = fields.Date(string='Period From', required=True, tracking=True)
    payment_period_to = fields.Date(string='Period To', required=True, tracking=True)
    run_status = fields.Selection([
        ('draft', 'Draft'),
        ('preview', 'Preview'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
    ], string='Status', default='draft', required=True, tracking=True)
    summary_ids = fields.One2many('tutor.payment.summary', 'payment_run_id', string='Tutor Summaries')
    line_ids = fields.One2many('tutor.payment.line', 'payment_run_id', string='Payment Lines')
    total_tutors = fields.Integer(string='Total Tutors', compute='_compute_totals', store=True)
    total_hours = fields.Float(string='Total Hours', compute='_compute_totals', store=True)
    total_gross_pay = fields.Float(string='Total Gross Pay', compute='_compute_totals', store=True)
    created_by = fields.Many2one('res.users', string='Created By', default=lambda self: self.env.user, readonly=True)
    created_date = fields.Datetime(string='Created Date', default=fields.Datetime.now, readonly=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    approved_date = fields.Datetime(string='Approved Date', readonly=True)
    paid_by = fields.Many2one('res.users', string='Paid By', readonly=True)
    paid_date = fields.Datetime(string='Paid Date', readonly=True)

    @api.depends('summary_ids.gross_pay', 'summary_ids.regular_hours', 'summary_ids.demo_hours', 'summary_ids.tutor_id')
    def _compute_totals(self):
        for rec in self:
            rec.total_tutors = len(rec.summary_ids.mapped('tutor_id'))
            rec.total_hours = sum(rec.summary_ids.mapped('regular_hours')) + sum(rec.summary_ids.mapped('demo_hours'))
            rec.total_gross_pay = sum(rec.summary_ids.mapped('gross_pay'))

    @api.constrains('payment_period_from', 'payment_period_to')
    def _check_period(self):
        for rec in self:
            if rec.payment_period_from and rec.payment_period_to and rec.payment_period_to < rec.payment_period_from:
                raise ValidationError("Payment Period To must be on or after Payment Period From.")
            duplicate = self.search([
                ('id', '!=', rec.id),
                ('payment_period_from', '=', rec.payment_period_from),
                ('payment_period_to', '=', rec.payment_period_to),
            ], limit=1)
            if duplicate and not self.env.context.get('allow_duplicate_payroll_run'):
                raise ValidationError("A payroll run already exists for this exact period.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('tutor.payment.run') or 'New'
        return super().create(vals_list)

    @api.model
    def generate_tutor_payroll_run(self, start_date, end_date):
        run = self.create({
            'payment_period_from': start_date,
            'payment_period_to': end_date,
        })
        run.action_generate_preview()
        return run

    @api.model
    def generateTutorPayrollRun(self, startDate, endDate):
        return self.generate_tutor_payroll_run(startDate, endDate)

    @api.model
    def finalize_tutor_payments(self, run_id):
        run = self.browse(run_id).exists()
        if not run:
            raise UserError("Payroll run not found.")
        run.action_approve()
        return run

    @api.model
    def finalizeTutorPayments(self, runId):
        return self.finalize_tutor_payments(runId)

    def action_generate_preview(self):
        for run in self:
            if run.run_status not in ('draft', 'preview'):
                raise UserError("Only Draft or Preview runs can be regenerated.")
            run.summary_ids.unlink()
            lessons = run._find_payable_lessons()
            if not lessons:
                raise UserError("No completed payable lessons were found for this period.")
            summaries_by_tutor = {}
            engine = self.env['tutor.payment.engine']
            for lesson in lessons:
                calc = engine.calculate_lesson_payment(lesson)
                summary = summaries_by_tutor.get(lesson.tutor_id.id)
                if not summary:
                    summary = self.env['tutor.payment.summary'].create({
                        'payment_run_id': run.id,
                        'tutor_id': lesson.tutor_id.id,
                    })
                    summaries_by_tutor[lesson.tutor_id.id] = summary
                self.env['tutor.payment.line'].create({
                    'payment_run_id': run.id,
                    'tutor_payment_summary_id': summary.id,
                    'lesson_id': lesson.id,
                    'category_id': calc['category'].id,
                    'subject_id': calc['subject'].id,
                    'hours_worked': calc['hours'],
                    'rate_used': calc['rate_used'],
                    'amount': calc['amount'],
                    'demo_flag': lesson.is_demo,
                    'tutor_rate_id': calc['rate_record'].id,
                })
            run.write({'run_status': 'preview'})
        return True

    def _find_payable_lessons(self):
        self.ensure_one()
        start_dt = datetime.combine(fields.Date.to_date(self.payment_period_from), time.min)
        end_dt = datetime.combine(fields.Date.to_date(self.payment_period_to), time.max)
        paid_line_lessons = self.env['tutor.payment.line'].search([
            ('lesson_id', '!=', False),
            ('payment_run_id.run_status', 'in', ['approved', 'paid']),
        ]).mapped('lesson_id').ids
        existing_preview_lessons = self.env['tutor.payment.line'].search([
            ('payment_run_id', '!=', self.id),
            ('payment_run_id.run_status', 'in', ['draft', 'preview']),
            ('lesson_id', '!=', False),
        ]).mapped('lesson_id').ids
        excluded_ids = list(set(paid_line_lessons + existing_preview_lessons))
        domain = [
            ('lesson_status', '=', 'completed'),
            ('tutor_id', '!=', False),
            ('course_id', '!=', False),
            ('start_datetime', '>=', start_dt),
            ('start_datetime', '<=', end_dt),
        ]
        if excluded_ids:
            domain.append(('id', 'not in', excluded_ids))
        return self.env['class.schedule.occurrence'].search(domain, order='tutor_id, start_datetime')

    def action_approve(self):
        for run in self:
            if run.run_status != 'preview':
                raise UserError("Only Preview runs can be approved.")
            if not run.line_ids:
                raise UserError("Generate payroll preview before approval.")
            paid_lessons = self.env['tutor.payment.line'].search([
                ('payment_run_id', '!=', run.id),
                ('payment_run_id.run_status', 'in', ['approved', 'paid']),
                ('lesson_id', 'in', run.line_ids.mapped('lesson_id').ids),
            ], limit=1)
            if paid_lessons:
                raise UserError("One or more lessons in this run are already attached to an approved or paid run.")
            run.line_ids.filtered(lambda line: line.payment_status == 'draft').write({'payment_status': 'approved'})
            run.summary_ids.write({'payment_status': 'approved'})
            run.line_ids._sync_lesson_payment_snapshot()
            run.write({
                'run_status': 'approved',
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })
        return True

    def action_mark_paid(self):
        for run in self:
            if run.run_status != 'approved':
                raise UserError("Only Approved runs can be marked Paid.")
            run.line_ids.with_context(payroll_finalize_write=True).write({'payment_status': 'paid'})
            run.summary_ids.write({'payment_status': 'paid'})
            run.line_ids._sync_lesson_payment_snapshot()
            run.write({
                'run_status': 'paid',
                'paid_by': self.env.user.id,
                'paid_date': fields.Datetime.now(),
            })
        return True

    def action_reset_to_draft(self):
        for run in self:
            if run.run_status not in ('draft', 'preview'):
                raise UserError("Only Draft or Preview runs can be reset.")
            run.summary_ids.unlink()
            run.write({'run_status': 'draft'})
        return True

    def write(self, vals):
        protected_fields = {'payment_period_from', 'payment_period_to'}
        if protected_fields & set(vals):
            locked = self.filtered(lambda run: run.run_status in ('approved', 'paid'))
            if locked:
                raise UserError("Approved or paid payroll run periods cannot be changed.")
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda run: run.run_status in ('approved', 'paid')):
            raise UserError("Approved or paid payroll runs cannot be deleted.")
        return super().unlink()


class TutorPaymentSummary(models.Model):
    _name = 'tutor.payment.summary'
    _description = 'Tutor Payment Summary'
    _order = 'tutor_id'

    payment_run_id = fields.Many2one('tutor.payment.run', string='Payment Run', required=True, ondelete='cascade')
    run_status = fields.Selection(related='payment_run_id.run_status', string='Run Status', store=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', required=True)
    line_ids = fields.One2many('tutor.payment.line', 'tutor_payment_summary_id', string='Lesson Lines')
    regular_hours = fields.Float(string='Regular Hours', compute='_compute_amounts', store=True)
    demo_hours = fields.Float(string='Demo Hours', compute='_compute_amounts', store=True)
    regular_pay = fields.Float(string='Regular Pay', compute='_compute_amounts', store=True)
    demo_pay = fields.Float(string='Demo Pay', compute='_compute_amounts', store=True)
    gross_pay = fields.Float(string='Gross Pay', compute='_compute_amounts', store=True)
    payment_status = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
    ], default='draft', string='Payment Status')
    currency_id = fields.Many2one(related='payment_run_id.currency_id', store=True)

    @api.depends('line_ids.hours_worked', 'line_ids.amount', 'line_ids.demo_flag', 'line_ids.payment_status')
    def _compute_amounts(self):
        for rec in self:
            active_lines = rec.line_ids.filtered(lambda line: line.payment_status != 'rejected')
            regular_lines = active_lines.filtered(lambda line: not line.demo_flag)
            demo_lines = active_lines.filtered('demo_flag')
            rec.regular_hours = sum(regular_lines.mapped('hours_worked'))
            rec.demo_hours = sum(demo_lines.mapped('hours_worked'))
            rec.regular_pay = sum(regular_lines.mapped('amount'))
            rec.demo_pay = sum(demo_lines.mapped('amount'))
            rec.gross_pay = rec.regular_pay + rec.demo_pay


class TutorPaymentLine(models.Model):
    _name = 'tutor.payment.line'
    _description = 'Tutor Payment Line'
    _order = 'lesson_id, id'

    payment_run_id = fields.Many2one('tutor.payment.run', string='Payment Run', required=True, ondelete='cascade')
    run_status = fields.Selection(related='payment_run_id.run_status', string='Run Status', store=True)
    tutor_payment_summary_id = fields.Many2one(
        'tutor.payment.summary',
        string='Tutor Summary',
        required=True,
        ondelete='cascade',
    )
    tutor_id = fields.Many2one(related='tutor_payment_summary_id.tutor_id', string='Tutor', store=True)
    lesson_id = fields.Many2one('class.schedule.occurrence', string='Lesson', required=True, ondelete='restrict')
    category_id = fields.Many2one('subject.category', string='Category', required=True)
    subject_id = fields.Many2one('subject.master', string='Subject', required=True)
    hours_worked = fields.Float(string='Hours Worked', required=True)
    rate_used = fields.Float(string='Rate Used', required=True)
    amount = fields.Float(string='Amount', required=True)
    demo_flag = fields.Boolean(string='Demo')
    tutor_rate_id = fields.Many2one('tutor.subject.rate', string='Rate Rule')
    payment_status = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
    ], default='draft', string='Line Status')
    adjustment_reason = fields.Char(string='Adjustment / Rejection Reason')
    currency_id = fields.Many2one(related='payment_run_id.currency_id', store=True)

    _sql_constraints = [
        ('unique_lesson_per_run', 'unique(payment_run_id, lesson_id)', 'A lesson can only appear once in a payroll run.'),
    ]

    @api.onchange('hours_worked', 'rate_used')
    def _onchange_amount(self):
        for line in self:
            line.amount = (line.hours_worked or 0.0) * (line.rate_used or 0.0)

    @api.constrains('hours_worked', 'rate_used', 'amount')
    def _check_positive_amounts(self):
        for line in self:
            if line.payment_status != 'rejected':
                if line.hours_worked <= 0:
                    raise ValidationError("Payment line hours must be greater than zero.")
                if line.rate_used <= 0:
                    raise ValidationError("Payment line rate must be greater than zero.")
                if line.amount < 0:
                    raise ValidationError("Payment line amount cannot be negative.")

    @api.constrains('lesson_id', 'payment_run_id')
    def _check_lesson_not_paid_twice(self):
        for rec in self:
            existing = self.search([
                ('id', '!=', rec.id),
                ('lesson_id', '=', rec.lesson_id.id),
                ('payment_run_id.run_status', 'in', ['approved', 'paid']),
            ], limit=1)
            if existing and rec.payment_run_id.run_status in ('approved', 'paid', 'preview'):
                raise ValidationError("This lesson is already attached to an approved or paid payroll run.")

    def action_reject_line(self):
        for line in self:
            if line.payment_run_id.run_status not in ('draft', 'preview'):
                raise UserError("Only Draft or Preview payment lines can be rejected.")
            line.payment_status = 'rejected'
        return True

    def write(self, vals):
        protected_fields = {
            'lesson_id', 'category_id', 'subject_id', 'hours_worked',
            'rate_used', 'amount', 'demo_flag', 'tutor_rate_id', 'payment_status',
        }
        if protected_fields & set(vals) and not self.env.context.get('payroll_finalize_write'):
            locked = self.filtered(lambda line: line.payment_run_id.run_status in ('approved', 'paid'))
            if locked:
                raise UserError("Approved or paid payroll lines cannot be edited.")
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.payment_run_id.run_status in ('approved', 'paid')):
            raise UserError("Approved or paid payroll lines cannot be deleted.")
        return super().unlink()

    def _sync_lesson_payment_snapshot(self):
        for line in self:
            if line.lesson_id:
                line.lesson_id.write({
                    'tutor_rate_used': line.rate_used,
                    'payable_hours': line.hours_worked,
                    'tutor_calculated_amount': line.amount,
                    'tutor_payment_line_id': line.id,
                    'tutor_payment_status': line.payment_status,
                })

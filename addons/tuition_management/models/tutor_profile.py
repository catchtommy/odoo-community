# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from .tz_utils import get_tz_selection, DEFAULT_TIMEZONE
from .user_permission import require_permission, user_has_permission
from .phone_codes import COUNTRY_PHONE_CODES


class TutorAvailability(models.Model):
    _name = 'tutor.availability'
    _description = 'Tutor Availability'

    tutor_id = fields.Many2one('tutor.profile', string='Tutor', required=True, ondelete='cascade')
    day_of_week = fields.Selection([
        ('monday', 'Monday'), ('tuesday', 'Tuesday'), ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'), ('friday', 'Friday'), ('saturday', 'Saturday'), ('sunday', 'Sunday'),
    ], string='Day of Week', required=True)
    start_time = fields.Float(string='Start Time')
    end_time = fields.Float(string='End Time')


class TutorAvailabilityMatrixLine(models.TransientModel):
    _name = 'tutor.availability.matrix.line'
    _description = 'Availability Matrix Line'

    wizard_id = fields.Many2one('tutor.availability.matrix.wizard', ondelete='cascade')
    mon = fields.Char('Monday', help='Format: HH:MM-HH:MM  e.g. 09:00-17:00')
    tue = fields.Char('Tuesday', help='Format: HH:MM-HH:MM')
    wed = fields.Char('Wednesday', help='Format: HH:MM-HH:MM')
    thu = fields.Char('Thursday', help='Format: HH:MM-HH:MM')
    fri = fields.Char('Friday', help='Format: HH:MM-HH:MM')
    sat = fields.Char('Saturday', help='Format: HH:MM-HH:MM')
    sun = fields.Char('Sunday', help='Format: HH:MM-HH:MM')


class TutorAvailabilityMatrixWizard(models.TransientModel):
    _name = 'tutor.availability.matrix.wizard'
    _description = 'Tutor Availability Matrix Wizard'

    tutor_id = fields.Many2one('tutor.profile', string='Tutor', required=True)
    line_ids = fields.One2many('tutor.availability.matrix.line', 'wizard_id', string='Slots')

    @staticmethod
    def _fmt_time(t):
        h = int(t)
        m = int(round((t - h) * 60))
        return '%02d:%02d' % (h, m)

    @staticmethod
    def _parse_time(s):
        """'09:30' → 9.5"""
        parts = s.strip().split(':')
        if len(parts) != 2:
            raise ValidationError("Invalid time '%s'. Use HH:MM format." % s)
        return int(parts[0]) + int(parts[1]) / 60.0

    @classmethod
    def _parse_slot(cls, val, day_label):
        """'09:00-17:00' → (9.0, 17.0) or None if blank."""
        if not val or not val.strip():
            return None
        raw = val.strip()
        sep = '–' if '–' in raw else '-'
        parts = raw.split(sep)
        if len(parts) != 2:
            raise ValidationError(
                "Invalid format '%s' for %s. Use HH:MM-HH:MM (e.g. 09:00-17:00)." % (val, day_label)
            )
        start = cls._parse_time(parts[0])
        end = cls._parse_time(parts[1])
        if end <= start:
            raise ValidationError(
                "End time must be after start time for %s (got '%s')." % (day_label, val)
            )
        return (start, end)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        tutor_id = self.env.context.get('default_tutor_id')
        if tutor_id:
            tutor = self.env['tutor.profile'].browse(tutor_id)
            days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            day_keys = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
            slots = {d: [] for d in days}
            for av in tutor.availability_ids:
                if av.day_of_week in slots:
                    slots[av.day_of_week].append((av.start_time, av.end_time))
            for d in days:
                slots[d].sort()
            max_rows = max((len(slots[d]) for d in days), default=0)
            lines = []
            for i in range(max(max_rows, 3)):
                line_vals = {}
                for d, key in zip(days, day_keys):
                    day_slots = slots[d]
                    if i < len(day_slots):
                        s, e = day_slots[i]
                        line_vals[key] = '%s-%s' % (self._fmt_time(s), self._fmt_time(e))
                    else:
                        line_vals[key] = ''
                lines.append((0, 0, line_vals))
            res['line_ids'] = lines
        return res

    def action_save(self):
        self.ensure_one()
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_keys = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        day_labels = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        all_slots = {d: [] for d in days}
        for line in self.line_ids:
            for d, key, label in zip(days, day_keys, day_labels):
                val = getattr(line, key)
                slot = self._parse_slot(val, label)
                if slot:
                    all_slots[d].append(slot)

        for d, label in zip(days, day_labels):
            sorted_slots = sorted(all_slots[d])
            for i in range(len(sorted_slots) - 1):
                _, end_a = sorted_slots[i]
                start_b, _ = sorted_slots[i + 1]
                if end_a > start_b:
                    raise ValidationError(
                        "Overlapping availability on %s: %s-%s overlaps with %s-%s." % (
                            label,
                            self._fmt_time(sorted_slots[i][0]), self._fmt_time(end_a),
                            self._fmt_time(start_b), self._fmt_time(sorted_slots[i + 1][1]),
                        )
                    )

        self.tutor_id.availability_ids.unlink()
        new_vals = []
        for d, label in zip(days, day_labels):
            for start, end in sorted(all_slots[d]):
                new_vals.append({
                    'tutor_id': self.tutor_id.id,
                    'day_of_week': d,
                    'start_time': start,
                    'end_time': end,
                })
        if new_vals:
            self.env['tutor.availability'].create(new_vals)
        return {'type': 'ir.actions.act_window_close'}


class TutorAvailabilityOverview(models.TransientModel):
    _name = 'tutor.availability.overview'
    _description = 'Tutor Availability Overview'

    tutor_id = fields.Many2one('tutor.profile', string='Filter by Tutor',
                               help='Leave blank and click "Show All" to view all tutors')
    show_all = fields.Boolean(default=False)
    result_html = fields.Html(
        string='Availability Schedule',
        compute='_compute_result_html',
        sanitize=False,
        store=False,
    )

    @api.depends('tutor_id', 'show_all')
    def _compute_result_html(self):
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_labels = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        def fmt_time(t):
            h = int(t)
            m = int(round((t - h) * 60))
            return '%02d:%02d' % (h, m)

        for rec in self:
            if not rec.tutor_id and not rec.show_all:
                rec.result_html = (
                    '<div class="alert alert-info" role="alert" style="margin-top:16px;">'
                    'Select a tutor above and click <strong>Search</strong>, '
                    'or click <strong>Show All Tutors</strong> to view the full schedule.'
                    '</div>'
                )
                continue

            tutors = rec.tutor_id if rec.tutor_id else self.env['tutor.profile'].search([('active', '=', True)], order='name')

            if not tutors:
                rec.result_html = '<p class="text-muted">No tutors found.</p>'
                continue

            th_day  = 'padding:8px 10px;background:#2E86AB;color:#fff;text-align:center;font-weight:bold;border:1px solid #ccc;min-width:120px;'
            th_name = 'padding:8px 12px;background:#1a5276;color:#fff;text-align:left;font-weight:bold;border:1px solid #ccc;min-width:160px;'
            td_slot = 'padding:5px 8px;text-align:center;border:1px solid #ddd;vertical-align:middle;white-space:nowrap;'
            td_name = 'padding:5px 10px;text-align:left;border:1px solid #ddd;font-weight:600;vertical-align:middle;background:#f0f4f8;'
            td_none = 'padding:5px 8px;text-align:center;border:1px solid #ddd;color:#bbb;'

            html = [
                '<div style="overflow-x:auto;">',
                '<table style="border-collapse:collapse;width:100%;font-size:13px;">',
                '<thead><tr>',
                '<th style="%s">Tutor</th>' % th_name,
            ]
            for label in day_labels:
                html.append('<th style="%s">%s</th>' % (th_day, label))
            html.append('</tr></thead><tbody>')

            for tutor in tutors:
                slots = {d: [] for d in days}
                for av in tutor.availability_ids:
                    if av.day_of_week in slots:
                        slots[av.day_of_week].append((av.start_time, av.end_time))
                for d in days:
                    slots[d].sort()

                max_rows = max((len(slots[d]) for d in days), default=0)
                tutor_label = '%s<br/><span style="font-size:11px;color:#666;">%s</span>' % (
                    tutor.name, tutor.timezone or 'UTC'
                )

                if max_rows == 0:
                    html.append('<tr>')
                    html.append('<td style="%s">%s</td>' % (td_name, tutor_label))
                    for d in days:
                        html.append('<td style="%s">—</td>' % td_none)
                    html.append('</tr>')
                else:
                    for i in range(max_rows):
                        html.append('<tr>')
                        if i == 0:
                            html.append('<td style="%s" rowspan="%d">%s</td>' % (td_name, max_rows, tutor_label))
                        for d in days:
                            day_slots = slots[d]
                            if i < len(day_slots):
                                s, e = day_slots[i]
                                html.append('<td style="%s">%s – %s</td>' % (td_slot, fmt_time(s), fmt_time(e)))
                            else:
                                html.append('<td style="%s">—</td>' % td_none)
                        html.append('</tr>')

            html.append('</tbody></table></div>')
            rec.result_html = ''.join(html)

    @api.model
    def action_open(self):
        rec = self.create({})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tutor Availability',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': rec.id,
            'target': 'current',
            'flags': {'mode': 'readonly'},
        }

    def _return_self(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tutor Availability',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_search(self):
        self.ensure_one()
        self.write({'show_all': False})
        return self._return_self()

    def action_show_all(self):
        self.ensure_one()
        self.write({'show_all': True, 'tutor_id': False})
        return self._return_self()


class TutorProfile(models.Model):
    _name = 'tutor.profile'
    _description = 'Tutor Profile'

    name = fields.Char(string='Full Name', required=True)
    email = fields.Char(string='Email')
    country_code = fields.Selection(COUNTRY_PHONE_CODES, string='Country Code', default='+1')
    phone = fields.Char(string='Phone')
    timezone = fields.Selection(selection=get_tz_selection, string='Timezone', default=DEFAULT_TIMEZONE)
    status = fields.Selection(
        selection=[('active', 'Active'), ('inactive', 'Inactive')],
        string='Status',
        default='active',
        required=True,
    )
    subject_ids = fields.Many2many('subject.master', string='Subjects')
    category_ids = fields.Many2many('subject.category', string='Categories')
    tutor_subject_rate_ids = fields.One2many('tutor.subject.rate', 'tutor_id', string='Tutor Pricing Matrix')
    grade_ids = fields.Many2many('grade.master', string='Grades')
    availability_ids = fields.One2many('tutor.availability', 'tutor_id', string='Availability')
    availability_matrix_html = fields.Html(
        string='Availability Matrix',
        compute='_compute_availability_matrix',
        sanitize=False,
        store=False,
    )
    partner_id = fields.Many2one('res.partner', string='Contact')
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        ondelete='set null',
        help="Link to the HR employee record for this tutor.",
    )
    active = fields.Boolean(default=True)
    portal_user_id = fields.Many2one('res.users', string='Portal User', compute='_compute_portal_access', store=False)
    portal_login = fields.Char(string='Portal Login', compute='_compute_portal_access', store=False)
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_portal_access', store=False)
    can_edit_tutor = fields.Boolean(string='Can Edit Tutor', compute='_compute_can_edit_tutor')

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            self.name = self.employee_id.name or self.name
            self.email = self.employee_id.work_email or self.email
            self.phone = self.employee_id.work_phone or self.phone
            self.timezone = self.employee_id.tz or self.timezone

    @api.depends_context('uid')
    def _compute_can_edit_tutor(self):
        can_edit = (
            self.env.user.has_group('base.group_system') or
            user_has_permission(self.env.user, 'tutor_edit')
        )
        for rec in self:
            rec.can_edit_tutor = can_edit

    @api.depends('availability_ids', 'availability_ids.day_of_week',
                 'availability_ids.start_time', 'availability_ids.end_time')
    def _compute_availability_matrix(self):
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_labels = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        def fmt_time(t):
            h = int(t)
            m = int(round((t - h) * 60))
            return '%02d:%02d' % (h, m)

        for rec in self:
            slots = {d: [] for d in days}
            for av in rec.availability_ids:
                if av.day_of_week in slots:
                    slots[av.day_of_week].append((av.start_time, av.end_time))
            for d in days:
                slots[d].sort()

            max_rows = max((len(slots[d]) for d in days), default=0)

            if max_rows == 0:
                rec.availability_matrix_html = '<p class="text-muted">No availability defined.</p>'
                continue

            tz_label = rec.timezone or 'UTC'
            th_style = 'padding:8px 12px;background:#2E86AB;color:#fff;text-align:center;font-weight:bold;border:1px solid #ccc;min-width:110px;'
            td_style = 'padding:6px 10px;text-align:center;border:1px solid #ddd;vertical-align:middle;'
            td_empty = 'padding:6px 10px;text-align:center;border:1px solid #ddd;color:#bbb;'

            html = [
                '<div style="overflow-x:auto;">',
                '<p style="font-size:12px;color:#666;margin-bottom:6px;">Times shown in tutor\'s local timezone: <strong>%s</strong></p>' % tz_label,
                '<table style="border-collapse:collapse;width:100%;font-size:13px;">',
            ]
            html.append('<thead><tr>')
            for label in day_labels:
                html.append('<th style="%s">%s</th>' % (th_style, label))
            html.append('</tr></thead>')
            html.append('<tbody>')
            for i in range(max_rows):
                html.append('<tr>')
                for d in days:
                    day_slots = slots[d]
                    if i < len(day_slots):
                        start, end = day_slots[i]
                        html.append('<td style="%s">%s – %s</td>' % (td_style, fmt_time(start), fmt_time(end)))
                    else:
                        html.append('<td style="%s">—</td>' % td_empty)
                html.append('</tr>')
            html.append('</tbody></table></div>')
            rec.availability_matrix_html = ''.join(html)

    @api.model
    def get_eligible_tutors(self, category, subject, lesson_date=None):
        category_id = category.id if hasattr(category, 'id') else category
        subject_id = subject.id if hasattr(subject, 'id') else subject
        if not category_id or not subject_id:
            return self.browse()
        target_date = fields.Date.to_date(lesson_date) if lesson_date else fields.Date.today()
        rate_domain = [
            ('category_id', '=', category_id),
            ('subject_id', '=', subject_id),
            ('active_flag', '=', True),
            ('effective_from', '<=', target_date),
            '|', ('effective_to', '=', False), ('effective_to', '>=', target_date),
        ]
        return self.search([('tutor_subject_rate_ids', 'in', self.env['tutor.subject.rate'].search(rate_domain).ids)])

    @api.model
    def getEligibleTutors(self, category, subject):
        return self.get_eligible_tutors(category, subject)

    @api.depends('partner_id')
    def _compute_portal_access(self):
        for rec in self:
            user = self.env['res.users'].sudo().search([('partner_id', '=', rec.partner_id.id)], limit=1) if rec.partner_id else self.env['res.users']
            rec.portal_user_id = user.id if user else False
            rec.portal_login = user.login if user else ''
            rec.has_portal_access = bool(user)

    def action_open_availability_matrix(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Edit Availability Matrix',
            'res_model': 'tutor.availability.matrix.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_tutor_id': self.id},
        }

    def action_invite_to_portal(self):
        self.ensure_one()
        if not self.email:
            raise UserError("Email is required to create a portal login.")
        ctx = {'default_profile_model': 'tutor.profile', 'default_profile_id': self.id,
               'default_name': self.name, 'default_email': self.email, 'default_login': self.email}
        if self.partner_id:
            user = self.env['res.users'].sudo().search([('partner_id', '=', self.partner_id.id)], limit=1)
            if user:
                ctx.update({'default_is_existing_user': True, 'default_existing_user_id': user.id, 'default_login': user.login})
        return {'type': 'ir.actions.act_window', 'name': 'Manage Portal Access',
                'res_model': 'portal.access.wizard', 'view_mode': 'form', 'target': 'new', 'context': ctx}

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.partner_id:
                # sudo(): auto-provisioning a linked Contact is an internal
                # implementation detail, not something that should require the
                # acting user to separately hold Sales/Contact-Creation access.
                partner = self.env['res.partner'].sudo().create({
                    'name': rec.name,
                    'email': rec.email,
                    'phone': '%s%s' % (rec.country_code or '', rec.phone or '') if rec.phone else False,
                })
                rec.partner_id = partner.id
        return records

    def write(self, vals):
        syncing = self.env.context.get('syncing_tutor_employee')
        if not syncing:
            require_permission(self.env.user, 'tutor_edit')
        res = super().write(vals)
        _emp_sync = [('name', 'name'), ('email', 'work_email'), ('phone', 'work_phone'), ('timezone', 'tz')]
        emp_vals = {ef: vals[tf] for tf, ef in _emp_sync if tf in vals}
        for rec in self:
            if rec.partner_id:
                partner_vals = {}
                if 'name' in vals: partner_vals['name'] = rec.name
                if 'email' in vals: partner_vals['email'] = rec.email
                if 'phone' in vals or 'country_code' in vals:
                    partner_vals['phone'] = '%s%s' % (rec.country_code or '', rec.phone or '')
                if partner_vals:
                    rec.partner_id.write(partner_vals)
            if emp_vals and rec.employee_id and not syncing:
                rec.employee_id.with_context(syncing_tutor_employee=True).write(emp_vals)
        return res

    def unlink(self):
        require_permission(self.env.user, 'tutor_delete')
        return super().unlink()

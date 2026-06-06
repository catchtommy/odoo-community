# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from .tz_utils import get_tz_selection, DEFAULT_TIMEZONE
from .user_permission import require_permission, user_has_permission


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

    # ------------------------------------------------------------------ helpers
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
        # support both '-' and '–' as separator
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

    # ------------------------------------------------------------------ default_get
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

    # ------------------------------------------------------------------ action_save
    def action_save(self):
        self.ensure_one()
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_keys = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        day_labels = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        # Collect all slots per day
        all_slots = {d: [] for d in days}
        for line in self.line_ids:
            for d, key, label in zip(days, day_keys, day_labels):
                val = getattr(line, key)
                slot = self._parse_slot(val, label)
                if slot:
                    all_slots[d].append(slot)

        # Validate: no overlapping slots within the same day
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

        # Persist: remove old, create new
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
        """Pre-create a transient record so buttons always work, then open the form."""
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
    country_code = fields.Char(string='Country Code', default='+1')
    phone = fields.Char(string='Phone')
    timezone = fields.Selection(selection=get_tz_selection, string='Timezone', default=DEFAULT_TIMEZONE)
    status = fields.Selection(
        selection=[('active', 'Active'), ('inactive', 'Inactive')],
        string='Status',
        default='active',
        required=True,
    )
    subject_ids = fields.Many2many('subject.master', string='Subjects')
    category_ids = fields.Many2many(
        'subject.category',
        string='Categories',
    )
    tutor_subject_rate_ids = fields.One2many(
        'tutor.subject.rate',
        'tutor_id',
        string='Tutor Pricing Matrix',
    )
    grade_ids = fields.Many2many('grade.master', string='Grades')
    availability_ids = fields.One2many('tutor.availability', 'tutor_id', string='Availability')
    availability_matrix_html = fields.Html(
        string='Availability Matrix',
        compute='_compute_availability_matrix',
        sanitize=False,
        store=False,
    )
    partner_id = fields.Many2one('res.partner', string='Contact')
    active = fields.Boolean(default=True)
    portal_user_id = fields.Many2one('res.users', string='Portal User', compute='_compute_portal_access', store=False)
    portal_login = fields.Char(string='Portal Login', compute='_compute_portal_access', store=False)
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_portal_access', store=False)
    can_edit_tutor = fields.Boolean(string='Can Edit Tutor', compute='_compute_can_edit_tutor')

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
            # Build dict: day -> sorted list of (start, end)
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

            # Build HTML table
            th_style = 'padding:8px 12px;background:#2E86AB;color:#fff;text-align:center;font-weight:bold;border:1px solid #ccc;min-width:110px;'
            td_style = 'padding:6px 10px;text-align:center;border:1px solid #ddd;vertical-align:middle;'
            td_empty = 'padding:6px 10px;text-align:center;border:1px solid #ddd;color:#bbb;'

            html = [
                '<div style="overflow-x:auto;">',
                '<p style="font-size:12px;color:#666;margin-bottom:6px;">Times shown in tutor\'s local timezone: <strong>%s</strong></p>' % tz_label,
                '<table style="border-collapse:collapse;width:100%;font-size:13px;">',
            ]
            # Header row
            html.append('<thead><tr>')
            for label in day_labels:
                html.append('<th style="%s">%s</th>' % (th_style, label))
            html.append('</tr></thead>')
            # Data rows
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
        """Return tutors configured for both category and subject on lesson_date."""
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
                partner = self.env['res.partner'].create({
                    'name': rec.name,
                    'email': rec.email,
                    'phone': '%s%s' % (rec.country_code or '', rec.phone or '') if rec.phone else False,
                })
                rec.partner_id = partner.id
            # Portal user creation is intentionally NOT automatic.
            # Use the "Invite to Portal" button to grant access manually.
        return records

    def write(self, vals):
        require_permission(self.env.user, 'tutor_edit')
        res = super().write(vals)
        for rec in self:
            if rec.partner_id:
                partner_vals = {}
                if 'name' in vals: partner_vals['name'] = rec.name
                if 'email' in vals: partner_vals['email'] = rec.email
                if 'phone' in vals or 'country_code' in vals:
                    partner_vals['phone'] = '%s%s' % (rec.country_code or '', rec.phone or '')
                if partner_vals:
                    rec.partner_id.write(partner_vals)
        return res

    def unlink(self):
        require_permission(self.env.user, 'tutor_delete')
        return super().unlink()


class StudentProfile(models.Model):
    _name = 'student.profile'
    _description = 'Student Profile'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Full Name', required=True)
    partner_id = fields.Many2one('res.partner', string='Contact', required=True, ondelete='cascade')
    email = fields.Char(string='Email')
    country_code = fields.Char(string='Country Code', default='+1')
    phone = fields.Char(string='Phone')
    age = fields.Integer(string='Age')
    grade_id = fields.Many2one('grade.master', string='Grade', required=True)
    subjects_ids = fields.Many2many('subject.master', string='Subjects')
    parent_id = fields.Many2one('parent.profile', string='Parent')
    enrollment_ids = fields.One2many('course.enrollment', 'student_id', string='Enrollments')
    subscription_ids = fields.One2many('tuition.subscription', 'student_id', string='Subscriptions')
    progress_report_ids = fields.One2many('progress.report', 'student_id', string='Progress Reports')
    timezone = fields.Selection(selection=get_tz_selection, string='Timezone', required=True, default=DEFAULT_TIMEZONE)
    status = fields.Selection(
        selection=[('active', 'Active'), ('inactive', 'Inactive')],
        string='Status',
        default='active',
        required=True,
    )
    address_line_1 = fields.Char(string='Address Line 1')
    address_line_2 = fields.Char(string='Address Line 2')
    address_line_3 = fields.Char(string='Address Line 3')
    address_line_4 = fields.Char(string='Address Line 4')
    zip_code = fields.Char(string='Zip Code')
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_portal_access', store=True)

    @api.constrains('email', 'phone', 'parent_id')
    def _check_contact_info(self):
        for rec in self:
            if not rec.email and not rec.phone and not rec.parent_id:
                raise ValidationError("Please provide either an email address, a phone number, or a parent for the student.")
            if rec.phone and not rec.country_code:
                raise ValidationError("Please provide a country code when providing a phone number.")

    @api.depends('partner_id.user_ids')
    def _compute_portal_access(self):
        for rec in self:
            rec.has_portal_access = bool(rec.partner_id.user_ids)

    def action_invite_to_portal(self):
        self.ensure_one()
        if not self.email:
            raise UserError("Email is required to create a portal login.")
        ctx = {'default_profile_model': 'student.profile', 'default_profile_id': self.id,
               'default_name': self.name, 'default_email': self.email, 'default_login': self.email}
        if self.partner_id:
            user = self.env['res.users'].sudo().search([('partner_id', '=', self.partner_id.id)], limit=1)
            if user:
                ctx.update({'default_is_existing_user': True, 'default_existing_user_id': user.id, 'default_login': user.login})
        return {'type': 'ir.actions.act_window', 'name': 'Manage Portal Access',
                'res_model': 'portal.access.wizard', 'view_mode': 'form', 'target': 'new', 'context': ctx}

    def action_view_parent(self):
        self.ensure_one()
        if self.parent_id:
            return {'type': 'ir.actions.act_window', 'name': 'Parent', 'res_model': 'parent.profile',
                    'view_mode': 'form', 'res_id': self.parent_id.id}

    @api.onchange('parent_id')
    def _onchange_parent_id(self):
        if self.parent_id:
            if self.parent_id.email and not self.email:
                self.email = self.parent_id.email
            if self.parent_id.timezone:
                self.timezone = self.parent_id.timezone

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('partner_id'):
                partner_vals = {
                    'name': vals.get('name', 'Unknown Student'),
                    'email': vals.get('email'),
                    'phone': '%s%s' % (vals.get('country_code', ''), vals.get('phone', '')) if vals.get('phone') else False,
                }
                partner = self.env['res.partner'].create(partner_vals)
                vals['partner_id'] = partner.id

        records = super().create(vals_list)
        # Portal user creation is intentionally NOT automatic.
        # Use the "Invite to Portal" button to grant access manually.
        return records

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            if rec.partner_id:
                partner_vals = {}
                if 'name' in vals: partner_vals['name'] = rec.name
                if 'email' in vals: partner_vals['email'] = rec.email
                if 'phone' in vals or 'country_code' in vals:
                    partner_vals['phone'] = '%s%s' % (rec.country_code or '', rec.phone or '')
                if partner_vals:
                    rec.partner_id.write(partner_vals)
        return res

    def unlink(self):
        require_permission(self.env.user, 'student_delete')
        return super().unlink()


class ParentProfile(models.Model):
    _name = 'parent.profile'
    _description = 'Parent Profile'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Full Name', required=True)
    partner_id = fields.Many2one('res.partner', string='Contact', required=True, ondelete='cascade')
    email = fields.Char(string='Email')
    phone = fields.Char(string='Phone')
    country_code = fields.Char(string='Country Code', default='+1')
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_portal_access', store=True)
    timezone = fields.Selection(selection=get_tz_selection, string='Timezone', required=True, default=DEFAULT_TIMEZONE)
    status = fields.Selection(
        selection=[('active', 'Active'), ('inactive', 'Inactive')],
        string='Status',
        default='active',
        required=True,
    )
    address_line_1 = fields.Char(string='Address Line 1')
    address_line_2 = fields.Char(string='Address Line 2')
    address_line_3 = fields.Char(string='Address Line 3')
    address_line_4 = fields.Char(string='Address Line 4')
    zip_code = fields.Char(string='Zip Code')
    student_ids = fields.One2many('student.profile', 'parent_id', string='Children')
    notes = fields.Text(string='Notes')

    @api.depends('partner_id.user_ids')
    def _compute_portal_access(self):
        for rec in self:
            rec.has_portal_access = bool(rec.partner_id.user_ids)

    def action_invite_to_portal(self):
        self.ensure_one()
        if not self.email:
            raise UserError("Email is required to create a portal login.")
        ctx = {'default_profile_model': 'parent.profile', 'default_profile_id': self.id,
               'default_name': self.name, 'default_email': self.email, 'default_login': self.email}
        if self.partner_id:
            user = self.env['res.users'].sudo().search([('partner_id', '=', self.partner_id.id)], limit=1)
            if user:
                ctx.update({'default_is_existing_user': True, 'default_existing_user_id': user.id, 'default_login': user.login})
        return {'type': 'ir.actions.act_window', 'name': 'Manage Portal Access',
                'res_model': 'portal.access.wizard', 'view_mode': 'form', 'target': 'new', 'context': ctx}

    @api.constrains('email', 'phone')
    def _check_contact_info(self):
        for rec in self:
            if not rec.email and not rec.phone:
                raise ValidationError("Please provide either an email address or a phone number for the parent.")
            if rec.phone and not rec.country_code:
                raise ValidationError("Please provide a country code when providing a phone number.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('partner_id'):
                partner_vals = {
                    'name': vals.get('name', 'Unknown Parent'),
                    'email': vals.get('email'),
                    'phone': '%s%s' % (vals.get('country_code', ''), vals.get('phone', '')) if vals.get('phone') else False,
                }
                partner = self.env['res.partner'].create(partner_vals)
                vals['partner_id'] = partner.id

        records = super().create(vals_list)
        # Portal user creation is intentionally NOT automatic.
        # Use the "Invite to Portal" button to grant access manually.
        return records

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            if rec.partner_id:
                partner_vals = {}
                if 'name' in vals: partner_vals['name'] = rec.name
                if 'email' in vals: partner_vals['email'] = rec.email
                if 'phone' in vals or 'country_code' in vals:
                    partner_vals['phone'] = '%s%s' % (rec.country_code or '', rec.phone or '')
                if partner_vals:
                    rec.partner_id.write(partner_vals)
        return res

    def unlink(self):
        require_permission(self.env.user, 'parent_delete')
        return super().unlink()


class PortalAccessWizard(models.TransientModel):
    _name = 'portal.access.wizard'
    _description = 'Portal Access Wizard'

    profile_model = fields.Char(string='Profile Model', required=True)
    profile_id = fields.Integer(string='Profile ID', required=True)
    name = fields.Char(string='Name', readonly=True)
    email = fields.Char(string='Email', readonly=True)
    login = fields.Char(string='Login (Username)', required=True)
    password = fields.Char(string='Password', required=True)
    confirm_password = fields.Char(string='Confirm Password', required=True)
    is_existing_user = fields.Boolean(string='Existing User', readonly=True)
    existing_user_id = fields.Many2one('res.users', string='Existing Portal User', readonly=True)

    @api.model
    def _generate_login_from_name(self, name):
        import re
        base_login = re.sub(r'[^a-z0-9]', '', (name or 'user').lower()) or 'user'
        login, counter = base_login, 1
        while self.env['res.users'].sudo().with_context(active_test=False).search([('login', '=', login)], limit=1):
            counter += 1
            login = '%s%d' % (base_login, counter)
        return login

    @api.model
    def _generate_password(self):
        import random
        words = ['apple', 'brave', 'cloud', 'delta', 'eagle', 'flame', 'grace', 'honey',
                 'ivory', 'jewel', 'knack', 'lemon', 'mango', 'noble', 'ocean', 'pearl',
                 'quest', 'river', 'solar', 'tiger', 'ultra', 'vivid', 'whale', 'xenon',
                 'yacht', 'zebra', 'amber', 'blaze', 'coral', 'drift', 'ember', 'frost']
        return '%s%s@%d' % (random.choice(words).capitalize(), random.choice(words).capitalize(), random.randint(1000, 9999))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        profile_model = res.get('profile_model') or self.env.context.get('default_profile_model')
        profile_id = res.get('profile_id') or self.env.context.get('default_profile_id')
        profile_name = res.get('name') or self.env.context.get('default_name', '')
        if profile_model and profile_id:
            profile = self.env[profile_model].browse(profile_id)
            if profile.exists() and profile.partner_id:
                user = self.env['res.users'].sudo().search([('partner_id', '=', profile.partner_id.id)], limit=1)
                if user:
                    pwd = self._generate_password()
                    res.update({'is_existing_user': True, 'existing_user_id': user.id,
                                'login': user.login, 'password': pwd, 'confirm_password': pwd})
                    return res
        if not res.get('login') or res.get('login') == res.get('email'):
            res['login'] = self._generate_login_from_name(profile_name)
        pwd = self._generate_password()
        res.update({'password': pwd, 'confirm_password': pwd})
        return res

    def action_generate_password(self):
        self.ensure_one()
        pwd = self._generate_password()
        self.write({'password': pwd, 'confirm_password': pwd})
        return {'type': 'ir.actions.act_window', 'res_model': 'portal.access.wizard',
                'view_mode': 'form', 'res_id': self.id, 'target': 'new'}

    def _assign_portal_group(self, user):
        group_portal = self.env.ref('base.group_portal')
        user.sudo().write({'group_ids': [(6, 0, [group_portal.id])]})
        self.env.invalidate_all()

    def action_create_portal_user(self):
        self.ensure_one()
        if self.password != self.confirm_password:
            raise UserError("Passwords do not match.")
        if len(self.password) < 6:
            raise UserError("Password must be at least 6 characters.")
        profile = self.env[self.profile_model].browse(self.profile_id)
        if not profile.exists():
            raise UserError("Profile record not found.")
        domain = [('login', '=', self.login)]
        if self.is_existing_user and self.existing_user_id:
            domain.append(('id', '!=', self.existing_user_id.id))
        duplicate = self.env['res.users'].sudo().with_context(active_test=False).search(domain, limit=1)
        if duplicate:
            raise UserError(f"The username '{self.login}' is already taken by {duplicate.name}.")
        if self.is_existing_user and self.existing_user_id:
            user = self.existing_user_id.sudo()
            update_vals = {'password': self.password, 'active': True}
            if self.login and self.login != user.login:
                update_vals['login'] = self.login
                if user.partner_id: user.partner_id.sudo().write({'email': self.login})
                if hasattr(profile, 'email'): profile.sudo().write({'email': self.login})
            user.write(update_vals)
            self._assign_portal_group(user)
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Portal Access Updated', 'message': f'Updated for {self.name}. Login: {self.login}',
                               'type': 'success', 'sticky': False, 'next': {'type': 'ir.actions.act_window_close'}}}
        
        if not profile.partner_id:
            country = getattr(profile, 'country_code', '') or ''
            phonen = getattr(profile, 'phone', '') or ''
            partner = self.env['res.partner'].create({
                'name': profile.name, 'email': profile.email,
                'phone': f"{country}{phonen}"
            })
            profile.partner_id = partner.id
        else:
            partner = profile.partner_id
            if not partner.email: partner.email = profile.email
        existing_user = self.env['res.users'].sudo().with_context(active_test=False).search([('partner_id', '=', partner.id)], limit=1)
        if existing_user:
            existing_user.sudo().write({'login': self.login, 'password': self.password, 'active': True})
            self._assign_portal_group(existing_user.sudo())
        else:
            new_user = self.env['res.users'].sudo().with_context(no_reset_password=True).create(
                {'partner_id': partner.id, 'login': self.login, 'password': self.password, 'active': True})
            self._assign_portal_group(new_user)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': 'Portal Access Activated', 'message': f'Created for {self.name}. Login: {self.login}',
                           'type': 'success', 'sticky': False, 'next': {'type': 'ir.actions.act_window_close'}}}

    def action_deactivate_portal_user(self):
        self.ensure_one()
        if self.is_existing_user and self.existing_user_id:
            self.existing_user_id.sudo().write({'active': False})
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Deactivated', 'message': f'Access disabled for {self.name}.',
                               'type': 'warning', 'sticky': False, 'next': {'type': 'ir.actions.act_window_close'}}}
        raise UserError("No existing portal user found to deactivate.")

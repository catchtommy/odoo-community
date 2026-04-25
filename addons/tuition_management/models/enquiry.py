from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class EnquiryStage(models.Model):
    _name = 'enquiry.stage'
    _description = 'Enquiry Stage'
    _order = 'sequence'

    name = fields.Char(string='Stage Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    is_enrolled_stage = fields.Boolean(string='Is Enrolled Stage', default=False)


class Enquiry(models.Model):
    _name = 'enquiry'
    _description = 'Enquiry'

    enquiry_name = fields.Char(string='Enquiry Name', readonly=True, copy=False, default='New')
    name = fields.Char(string='Parent Name', required=True)
    student_name = fields.Char(string='Student Name')
    email = fields.Char(string='Email')
    country_code = fields.Char(string='Country Code', default='+1')
    phone = fields.Char(string='Phone')
    subject_id = fields.Many2one('subject.master', string='Subject')
    grade_id = fields.Many2one('grade.master', string='Grade')
    stage_id = fields.Many2one('enquiry.stage', string='Stage', group_expand='_read_group_stage_ids',
                                default=lambda self: self.env['enquiry.stage'].search([], limit=1))
    enquiry_date = fields.Date(string='Enquiry Date', default=fields.Date.today)
    notes = fields.Text(string='Notes')
    partner_id = fields.Many2one('res.partner', string='Contact')

    # Enrollment fields
    is_enrolled_stage = fields.Boolean(related='stage_id.is_enrolled_stage', string='Is Enrolled Stage')
    is_enrolled = fields.Boolean(string='Is Enrolled', default=False)
    course_id = fields.Many2one('course.master', string='Course')
    enrollment_id = fields.Many2one('course.enrollment', string='Enrollment')
    parent_profile_id = fields.Many2one('parent.profile', string='Parent Profile')
    student_profile_id = fields.Many2one('student.profile', string='Student Profile')

    demo_session_ids = fields.One2many('demo.session', 'enquiry_id', string='Demo Sessions')

    _stages_cleaned = False  # reset to re-run cleanup after code change

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        if not Enquiry._stages_cleaned:
            self._cleanup_stages()
            Enquiry._stages_cleaned = True
        return self.env['enquiry.stage'].search([], order='sequence')

    @api.model
    def _cleanup_stages(self):
        """One-time cleanup of duplicate/non-official enquiry stages."""
        cr = self.env.cr
        _logger.info("=== ENQUIRY STAGE LAZY CLEANUP ===")

        # Dedup: keep MIN(id) per name
        cr.execute("""
            SELECT name, MIN(id) as keep_id, array_agg(id ORDER BY id) as all_ids
            FROM enquiry_stage GROUP BY name HAVING COUNT(*) > 1
        """)
        for name, keep_id, all_ids in cr.fetchall():
            delete_ids = [i for i in all_ids if i != keep_id]
            if delete_ids:
                cr.execute("UPDATE enquiry SET stage_id = %s WHERE stage_id = ANY(%s)", (keep_id, delete_ids))
                cr.execute("DELETE FROM ir_model_data WHERE model='enquiry.stage' AND res_id = ANY(%s)", (delete_ids,))
                cr.execute("DELETE FROM enquiry_stage WHERE id = ANY(%s)", (delete_ids,))

        # Remove non-official
        official = ['New', 'Demo Scheduled', 'Demo Completed', 'Enrolled', 'Lost']
        cr.execute("SELECT id FROM enquiry_stage WHERE name != ALL(%s)", (official,))
        bad = [r[0] for r in cr.fetchall()]
        if bad:
            cr.execute("SELECT id FROM enquiry_stage WHERE name='New' ORDER BY id LIMIT 1")
            new_id = cr.fetchone()
            if new_id:
                cr.execute("UPDATE enquiry SET stage_id = %s WHERE stage_id = ANY(%s)", (new_id[0], bad))
            cr.execute("DELETE FROM ir_model_data WHERE model='enquiry.stage' AND res_id = ANY(%s)", (bad,))
            cr.execute("DELETE FROM enquiry_stage WHERE id = ANY(%s)", (bad,))

        # Ensure all 5 exist and fix sequences
        official_defs = [('New',10,False),('Demo Scheduled',20,False),('Demo Completed',30,False),('Enrolled',40,True),('Lost',50,False)]
        for name, seq, is_enr in official_defs:
            cr.execute("SELECT id FROM enquiry_stage WHERE name=%s", (name,))
            row = cr.fetchone()
            if not row:
                cr.execute(
                    "INSERT INTO enquiry_stage (name,sequence,is_enrolled_stage,create_uid,write_uid,create_date,write_date) VALUES (%s,%s,%s,1,1,now(),now())",
                    (name, seq, is_enr))
            else:
                cr.execute(
                    "UPDATE enquiry_stage SET sequence=%s, is_enrolled_stage=%s WHERE id=%s",
                    (seq, is_enr, row[0]))

        cr.execute("SELECT id, name FROM enquiry_stage ORDER BY sequence")
        _logger.info("After cleanup: %s", cr.fetchall())
        self.env.cr.commit()

    def _register_hook(self):
        return super()._register_hook()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('enquiry_name', 'New') == 'New':
                vals['enquiry_name'] = self.env['ir.sequence'].next_by_code('enquiry') or 'New'
        records = super().create(vals_list)
        for rec in records:
            rec._auto_create_parent_and_student()
        return records

    def write(self, vals):
        res = super().write(vals)
        # Sync parent fields if changed
        parent_fields = {'name', 'email', 'phone', 'country_code'}
        student_fields = {'student_name', 'grade_id'}
        if parent_fields & set(vals.keys()):
            for rec in self:
                if rec.parent_profile_id:
                    parent_vals = {}
                    if 'name' in vals:
                        parent_vals['name'] = rec.name
                    if 'email' in vals:
                        parent_vals['email'] = rec.email
                    if 'phone' in vals:
                        parent_vals['phone'] = rec.phone
                    if 'country_code' in vals:
                        parent_vals['country_code'] = rec.country_code
                    if parent_vals:
                        rec.parent_profile_id.write(parent_vals)
        if student_fields & set(vals.keys()):
            for rec in self:
                if rec.student_profile_id:
                    student_vals = {}
                    if 'student_name' in vals:
                        student_vals['name'] = rec.student_name
                    if 'grade_id' in vals:
                        student_vals['grade_id'] = rec.grade_id.id if rec.grade_id else False
                    if student_vals:
                        rec.student_profile_id.write(student_vals)
        return res

    @api.onchange('parent_profile_id')
    def _onchange_parent_profile_id(self):
        if self.parent_profile_id:
            self.name = self.parent_profile_id.name
            self.email = self.parent_profile_id.email
            self.phone = self.parent_profile_id.phone
            self.country_code = self.parent_profile_id.country_code
            self.partner_id = self.parent_profile_id.partner_id.id
            if self.student_profile_id and self.student_profile_id not in self.parent_profile_id.student_ids:
                self.student_profile_id = False

    @api.onchange('student_profile_id')
    def _onchange_student_profile_id(self):
        if self.student_profile_id:
            self.student_name = self.student_profile_id.name
            if self.student_profile_id.grade_id:
                self.grade_id = self.student_profile_id.grade_id.id
            if not self.parent_profile_id and self.student_profile_id.parent_id:
                self.parent_profile_id = self.student_profile_id.parent_id.id

    def _auto_create_parent_and_student(self):
        """Auto-create parent profile, student profile, and contacts on enquiry creation."""
        self.ensure_one()

        # --- Parent ---
        if not self.parent_profile_id:
            parent = self._find_or_create_parent()
            self.parent_profile_id = parent.id

        # --- Student ---
        if not self.student_profile_id and self.student_name:
            student = self._find_or_create_student(self.parent_profile_id)
            self.student_profile_id = student.id

    def _find_or_create_parent(self):
        """Find existing parent by email/phone or create a new one with contact."""
        Parent = self.env['parent.profile']
        Partner = self.env['res.partner']

        # Try to find existing parent by email
        if self.email:
            existing = Parent.search([('email', '=', self.email)], limit=1)
            if existing:
                return existing

        # Try to find existing parent by phone
        if self.phone:
            existing = Parent.search([
                ('phone', '=', self.phone),
                ('country_code', '=', self.country_code or '+1'),
            ], limit=1)
            if existing:
                return existing

        # Create contact (res.partner)
        phone_full = '%s%s' % (self.country_code or '', self.phone or '')
        partner = Partner.create({
            'name': self.name,
            'email': self.email,
            'phone': phone_full,
            'type': 'contact',
            'company_type': 'person',
        })

        # Also link enquiry partner_id if not set
        if not hasattr(self, 'partner_id') or not self.partner_id:
            self.partner_id = partner.id

        # Create parent profile
        parent_vals = {
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'country_code': self.country_code or '+1',
            'partner_id': partner.id,
        }
        parent = Parent.create(parent_vals)
        return parent

    def _find_or_create_student(self, parent):
        """Find existing student under same parent or create a new one with contact."""
        Student = self.env['student.profile']
        Partner = self.env['res.partner']

        existing = False
        if parent:
            existing = Student.search([
                ('name', '=', self.student_name),
                ('parent_id', '=', parent.id),
            ], limit=1)
            if existing:
                return existing
        else:
            existing = Student.search([
                ('name', '=', self.student_name),
            ], limit=1)
            if existing:
                if parent:
                    # student already existed, link parent if we newly found one
                    existing.write({'parent_id': parent.id})
                return existing

        student_partner_vals = {
            'name': self.student_name,
            'type': 'contact',
            'company_type': 'person',
        }
        if parent and parent.partner_id:
            student_partner_vals['parent_id'] = parent.partner_id.id
        student_partner = Partner.create(student_partner_vals)

        student_vals = {
            'name': self.student_name,
            'grade_id': self.grade_id.id if self.grade_id else False,
            'partner_id': student_partner.id,
            'parent_id': parent.id if parent else False,
        }
            
        student = Student.create(student_vals)
        return student

    def action_enroll_to_course(self):
        """Convert enquiry to a course with enrollment, reusing existing parent/student."""
        self.ensure_one()

        # Ensure parent exists (should already be created on enquiry creation)
        if not self.parent_profile_id:
            self.parent_profile_id = self._find_or_create_parent()

        # Ensure student exists
        if not self.student_profile_id:
            if self.student_name:
                self.student_profile_id = self._find_or_create_student(self.parent_profile_id)
            else:
                # Fallback: create student from parent name
                self.student_name = self.name
                self.student_profile_id = self._find_or_create_student(self.parent_profile_id)

        # Create course if not exists
        if not self.course_id:
            course = self.env['course.master'].create({
                'name': f"{self.subject_id.name or 'Course'} - {self.student_name or self.name}",
                'subject_id': self.subject_id.id if self.subject_id else False,
                'grade_id': self.grade_id.id if self.grade_id else False,
                'status': 'active',
            })
            self.course_id = course.id

        # Create enrollment
        if not self.enrollment_id:
            enrollment = self.env['course.enrollment'].create({
                'course_id': self.course_id.id,
                'student_id': self.student_profile_id.id,
            })
            self.enrollment_id = enrollment.id

        self.is_enrolled = True

        # Move to "Enrolled" stage automatically
        enrolled_stage = self.env['enquiry.stage'].search([
            ('is_enrolled_stage', '=', True)
        ], limit=1)
        if enrolled_stage:
            self.stage_id = enrolled_stage.id

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Enrolled Successfully',
                'message': f'{self.student_name or self.name} has been enrolled in {self.course_id.name}.',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_delete_enquiry(self):
        """Delete the enquiry."""
        self.unlink()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Enquiries',
            'res_model': 'enquiry',
            'view_mode': 'kanban,list,form',
        }


class DemoSession(models.Model):
    _name = 'demo.session'
    _description = 'Demo Session'

    enquiry_id = fields.Many2one('enquiry', string='Enquiry', required=True, ondelete='cascade')
    subject_id = fields.Many2one('subject.master', string='Subject')
    tutor_id = fields.Many2one('tutor.profile', string='Tutor')
    scheduled_datetime = fields.Datetime(string='Scheduled Date & Time')
    timezone = fields.Selection([
        ('US/Eastern', 'US/Eastern'),
        ('US/Central', 'US/Central'),
        ('US/Mountain', 'US/Mountain'),
        ('US/Pacific', 'US/Pacific'),
        ('Europe/London', 'Europe/London'),
        ('Europe/Paris', 'Europe/Paris'),
        ('Asia/Kolkata', 'Asia/Kolkata'),
        ('Asia/Tokyo', 'Asia/Tokyo'),
        ('Australia/Sydney', 'Australia/Sydney'),
        ('UTC', 'UTC'),
    ], string='Timezone', default='UTC')
    duration_minutes = fields.Integer(string='Duration (Minutes)', default=30)
    status = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ], string='Status', default='scheduled')
    rating = fields.Selection([
        ('1', '1 - Poor'),
        ('2', '2 - Fair'),
        ('3', '3 - Good'),
        ('4', '4 - Very Good'),
        ('5', '5 - Excellent'),
    ], string='Rating')
    feedback = fields.Text(string='Feedback')
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
        return super().create(vals_list)

    def action_enroll_to_course(self):
        """Convert enquiry to a course with enrollment."""
        self.ensure_one()
        # Create parent profile if not exists
        if not self.parent_profile_id:
            parent = self.env['parent.profile'].create({
                'name': self.name,
                'email': self.email,
                'country_code': self.country_code,
                'phone': self.phone,
                'partner_id': self.partner_id.id if self.partner_id else False,
            })
            self.parent_profile_id = parent.id

        # Create student profile if not exists
        if not self.student_profile_id:
            student = self.env['student.profile'].create({
                'name': self.student_name or self.name,
                'grade_id': self.grade_id.id if self.grade_id else False,
                'parent_id': self.parent_profile_id.id,
            })
            self.student_profile_id = student.id

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
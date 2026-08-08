from markupsafe import Markup
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging
from .tz_utils import get_tz_selection, DEFAULT_TIMEZONE
from .user_permission import require_permission, user_has_permission

_logger = logging.getLogger(__name__)


class EnquiryStage(models.Model):
    _name = 'enquiry.stage'
    _description = 'Enquiry Stage'
    _order = 'sequence'

    name = fields.Char(string='Stage Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    is_enrolled_stage = fields.Boolean(string='Is Enrolled Stage', default=False)


class EnquiryBatch(models.Model):
    """Groups sibling `enquiry` records created together from a single
    multi-student submission (website or backend), so staff can navigate
    between a family's enquiries. Only created for submissions with 2+
    students — single-student submissions never get a batch."""
    _name = 'enquiry.batch'
    _description = 'Enquiry Submission Batch'

    source = fields.Selection([
        ('website', 'Website'),
        ('backend', 'Backend'),
    ], string='Source', required=True)
    enquiry_ids = fields.One2many('enquiry', 'enquiry_batch_id', string='Enquiries')


class Enquiry(models.Model):
    _name = 'enquiry'
    _description = 'Enquiry'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'enquiry_name'
    _order = 'enquiry_date desc, id desc'

    _STATUS_STAGE_MAP = {
        'new': 'New',
        'demo_scheduled': 'Demo Scheduled',
        'demo_completed': 'Demo Completed',
        'enrolled': 'Enrolled',
        'lost': 'Lost',
    }

    enquiry_name = fields.Char(string='Enquiry Name', readonly=True, copy=False, default='New')
    name = fields.Char(string='Parent Name', required=True)
    student_name = fields.Char(string='Student Name', required=True)
    student_age = fields.Integer(string='Student Age')
    email = fields.Char(string='Email')
    country_code = fields.Char(string='Country Code', default='+1')
    phone = fields.Char(string='Phone')
    category_id = fields.Many2one('subject.category', string='Category')
    subject_id = fields.Many2one('subject.master', string='Subject', required=True)
    grade_id = fields.Many2one('grade.master', string='Grade', required=True)

    @api.onchange('category_id')
    def _onchange_enquiry_category_id(self):
        if self.category_id:
            # Clear subject if it doesn't belong to the selected category
            if self.subject_id and self.subject_id.category_id != self.category_id:
                self.subject_id = False
            # Clear grade if it doesn't belong to the selected category
            if self.grade_id and self.category_id not in self.grade_id.category_ids:
                self.grade_id = False
        else:
            self.subject_id = False
            self.grade_id = False
    stage_id = fields.Many2one(
        'enquiry.stage',
        string='Stage',
        group_expand='_read_group_stage_ids',
        default=lambda self: self.env['enquiry.stage'].search([], limit=1),
        tracking=True,
    )
    status = fields.Selection([
        ('new', 'New'),
        ('demo_scheduled', 'Demo Scheduled'),
        ('demo_completed', 'Demo Completed'),
        ('enrolled', 'Enrolled'),
        ('lost', 'Lost'),
    ], string='Status', compute='_compute_status', inverse='_inverse_status', store=True, tracking=True)
    enquiry_date = fields.Date(string='Enquiry Date', default=fields.Date.today)
    notes = fields.Text(string='Notes')
    partner_id = fields.Many2one('res.partner', string='Contact')
    assigned_user_id = fields.Many2one(
        'res.users',
        string='Assigned To',
        default=lambda self: self.env.user,
        tracking=True,
    )
    enquiry_source = fields.Selection([
        ('website', 'Website'),
        ('referral', 'Referral'),
        ('phone', 'Phone'),
        ('email', 'Email'),
        ('social_media', 'Social Media'),
        ('walk_in', 'Walk-in'),
        ('other', 'Other'),
    ], string='Source', tracking=True)

    # Enrollment fields
    is_enrolled_stage = fields.Boolean(related='stage_id.is_enrolled_stage', string='Is Enrolled Stage')
    is_enrolled = fields.Boolean(string='Is Enrolled', default=False)
    course_id = fields.Many2one('course.master', string='Course')
    enrollment_id = fields.Many2one('course.enrollment', string='Enrollment')
    parent_profile_id = fields.Many2one('parent.profile', string='Parent Profile', tracking=True)
    student_profile_id = fields.Many2one('student.profile', string='Student Profile', tracking=True)
    possible_duplicate_parent_id = fields.Many2one(
        'parent.profile', string='Possible Duplicate Parent', readonly=True, copy=False,
        help='Set automatically when this enquiry\'s email/phone matches an existing parent, '
             'and no parent/student profile has been auto-created yet. Staff must resolve this '
             '(attach to the existing parent, or create a new one) from the Enquiry form.',
    )
    possible_duplicate_parent_email = fields.Char(related='possible_duplicate_parent_id.email', string='Matched Email')
    possible_duplicate_parent_phone = fields.Char(related='possible_duplicate_parent_id.phone', string='Matched Phone')

    can_convert_course = fields.Boolean(compute='_compute_can_convert_course')
    can_edit_enquiry = fields.Boolean(string='Can Edit Enquiry', compute='_compute_can_edit_enquiry')

    enquiry_batch_id = fields.Many2one(
        'enquiry.batch', string='Submission Batch', copy=False, index=True, readonly=True,
        help='Set when this enquiry was created together with sibling enquiries for other '
             'students of the same parent in one multi-student submission.',
    )
    sibling_enquiry_ids = fields.Many2many('enquiry', compute='_compute_sibling_enquiry_ids', string='Related Enquiries')
    sibling_enquiry_count = fields.Integer(compute='_compute_sibling_enquiry_ids', string='Related Enquiry Count')

    @api.depends('enquiry_batch_id', 'enquiry_batch_id.enquiry_ids')
    def _compute_sibling_enquiry_ids(self):
        for rec in self:
            siblings = (rec.enquiry_batch_id.enquiry_ids - rec) if rec.enquiry_batch_id else self.env['enquiry']
            rec.sibling_enquiry_ids = siblings
            rec.sibling_enquiry_count = len(siblings)

    def action_view_sibling_enquiries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Related Enquiries',
            'res_model': 'enquiry',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.sibling_enquiry_ids.ids)],
        }

    @api.depends_context('uid')
    def _compute_can_edit_enquiry(self):
        can_edit = (
            self.env.user.has_group('base.group_system') or
            user_has_permission(self.env.user, 'enquiry_edit')
        )
        for rec in self:
            rec.can_edit_enquiry = can_edit

    @api.depends('stage_id', 'is_enrolled')
    def _compute_can_convert_course(self):
        for rec in self:
            rec.can_convert_course = rec.stage_id and rec.stage_id.name != 'New' and not rec.is_enrolled

    @api.depends('stage_id', 'stage_id.name')
    def _compute_status(self):
        reverse_map = {stage_name: status for status, stage_name in self._STATUS_STAGE_MAP.items()}
        for rec in self:
            rec.status = reverse_map.get(rec.stage_id.name, 'new')

    def _inverse_status(self):
        for rec in self:
            stage_name = rec._STATUS_STAGE_MAP.get(rec.status)
            if stage_name:
                stage = rec.env['enquiry.stage'].search([('name', '=', stage_name)], limit=1)
                if stage:
                    rec.stage_id = stage.id

    @api.model
    def _stage_id_from_status(self, status):
        stage_name = self._STATUS_STAGE_MAP.get(status)
        if not stage_name:
            return False
        stage = self.env['enquiry.stage'].search([('name', '=', stage_name)], limit=1)
        return stage.id if stage else False

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
            if vals.get('status') and not vals.get('stage_id'):
                stage_id = self._stage_id_from_status(vals.pop('status'))
                if stage_id:
                    vals['stage_id'] = stage_id

            if vals.get('enquiry_name', 'New') == 'New':
                # Use standard ir.sequence and provide a robust fallback if XML sequence is missing
                seq = self.env['ir.sequence'].next_by_code('enquiry')
                vals['enquiry_name'] = seq if seq else 'ENQ/' + fields.Datetime.now().strftime('%Y%m%d%H%M%S')

            # Ensure parent data auto-fills on create if they just selected the parent dropdown
            if vals.get('parent_profile_id') and not vals.get('name'):
                parent = self.env['parent.profile'].browse(vals['parent_profile_id'])
                vals['name'] = parent.name
                vals['email'] = parent.email
                vals['phone'] = parent.phone
                vals['country_code'] = parent.country_code
                vals['partner_id'] = parent.partner_id.id
            
            # Ensure student data auto-fills on create
            if vals.get('student_profile_id') and not vals.get('student_name'):
                student = self.env['student.profile'].browse(vals['student_profile_id'])
                vals['student_name'] = student.name
                if student.grade_id:
                    vals['grade_id'] = student.grade_id.id

        records = super().create(vals_list)
        for rec in records:
            rec._auto_create_parent_and_student()
            rec._subscribe_related_partners()
            rec.message_post(
                body='Enquiry created for %s.' % (rec.student_name or rec.name),
                subtype_xmlid='mail.mt_note',
            )
            rec._schedule_enquiry_followup_activity()
        return records

    def write(self, vals):
        # Skip the manual permission check for sudo'd writes (e.g. the public
        # enquiry form auto-provisioning a parent/student profile via
        # _auto_create_parent_and_student() as a public/unauthenticated
        # visitor) — sudo() is exactly how trusted internal flows are meant
        # to bypass business-level checks intended for logged-in staff.
        if not self.env.su:
            require_permission(self.env.user, 'enquiry_edit')
        if vals.get('status') and not vals.get('stage_id'):
            vals = dict(vals)
            stage_id = self._stage_id_from_status(vals.pop('status'))
            if stage_id:
                vals['stage_id'] = stage_id
        old_stage_names = {rec.id: rec.stage_id.name for rec in self}
        old_tutor_by_course = {rec.id: rec.course_id.tutor_id for rec in self if rec.course_id}
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
        if {'parent_profile_id', 'student_profile_id'} & set(vals.keys()):
            for rec in self:
                rec._subscribe_related_partners()
        if 'stage_id' in vals:
            for rec in self:
                rec._post_stage_event(old_stage_names.get(rec.id))
        if 'is_enrolled' in vals or 'course_id' in vals or 'enrollment_id' in vals:
            for rec in self.filtered('is_enrolled'):
                rec.message_post(
                    body='Student enrolled%s.' % ((' in %s' % rec.course_id.name) if rec.course_id else ''),
                    subtype_xmlid='mail.mt_note',
                )
        if old_tutor_by_course:
            for rec in self.filtered('course_id'):
                old_tutor = old_tutor_by_course.get(rec.id)
                if old_tutor != rec.course_id.tutor_id and rec.course_id.tutor_id:
                    rec.message_post(
                        body='Tutor assigned: %s.' % rec.course_id.tutor_id.name,
                        subtype_xmlid='mail.mt_note',
                    )
        return res

    def _subscribe_related_partners(self):
        for rec in self:
            partner_ids = []
            if rec.partner_id:
                partner_ids.append(rec.partner_id.id)
            if rec.parent_profile_id.partner_id:
                partner_ids.append(rec.parent_profile_id.partner_id.id)
            if rec.student_profile_id.partner_id:
                partner_ids.append(rec.student_profile_id.partner_id.id)
            if partner_ids:
                rec.message_subscribe(partner_ids=list(set(partner_ids)))

    def _schedule_enquiry_followup_activity(self):
        todo_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not todo_type:
            return
        for rec in self:
            user = rec.assigned_user_id or self.env.user
            rec.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=fields.Date.today(),
                summary='Follow up enquiry',
                note='Contact the parent or student and record the next step.',
                user_id=user.id,
            )

    def _post_stage_event(self, old_stage_name=False):
        self.ensure_one()
        if old_stage_name == self.stage_id.name:
            return
        if self.stage_id.name == 'Demo Scheduled':
            body = 'Demo scheduled.'
        elif self.stage_id.name == 'Demo Completed':
            body = 'Demo completed.'
        elif self.stage_id.name == 'Enrolled':
            body = 'Student enrolled.'
        elif self.stage_id.name == 'Lost':
            body = 'Enquiry marked as lost.'
        else:
            return
        self.message_post(body=body, subtype_xmlid='mail.mt_note')

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
        """Auto-create parent profile, student profile, and contacts on enquiry creation.

        If the email/phone matches an existing parent, no parent or student is
        created — `possible_duplicate_parent_id` is set instead and staff must
        resolve it from the Enquiry form (action_attach_existing_parent /
        action_create_new_parent_and_student) before either profile exists.
        Callers that already know they want a brand-new parent regardless of
        any match (e.g. the resolution action itself) pass `force_new_parent`
        in context to skip this check.
        """
        self.ensure_one()

        # --- Parent ---
        if not self.parent_profile_id:
            if not self.env.context.get('force_new_parent'):
                existing = self._search_existing_parent(self.email, self.phone, self.country_code)
                if existing:
                    self.possible_duplicate_parent_id = existing.id
                    return
            parent = self._find_or_create_parent()
            self.parent_profile_id = parent.id

        # --- Student ---
        if not self.student_profile_id and self.student_name:
            student = self._find_or_create_student(self.parent_profile_id)
            self.student_profile_id = student.id

    @api.model
    def _search_existing_parent(self, email, phone, country_code):
        """Find an existing parent.profile by exact email, then exact phone+country_code.

        Shared by `_find_or_create_parent` and the public enquiry controller's
        duplicate-confirmation step, so both use identical matching rules.
        Returns an empty recordset if nothing matches.
        """
        Parent = self.env['parent.profile']
        if email:
            existing = Parent.search([('email', '=', email)], limit=1)
            if existing:
                return existing
        if phone:
            existing = Parent.search([
                ('phone', '=', phone),
                ('country_code', '=', country_code or '+1'),
            ], limit=1)
            if existing:
                return existing
        return Parent.browse()

    def _find_or_create_parent(self):
        """Find existing parent by email/phone or create a new one with contact.

        Skips the existing-parent search entirely when called with
        `force_new_parent` in context — set by the public enquiry controller
        when the submitter has explicitly confirmed "this is a different
        person" after being shown a possible duplicate match.
        """
        Parent = self.env['parent.profile']
        Partner = self.env['res.partner']

        if not self.env.context.get('force_new_parent'):
            existing = self._search_existing_parent(self.email, self.phone, self.country_code)
            if existing:
                return existing

        # Create contact (res.partner). sudo(): auto-provisioning a linked
        # Contact is an internal implementation detail, not something that
        # should require the acting user to separately hold Sales/
        # Contact-Creation access (this runs from plain button clicks like
        # "Convert to Course", not just the sudo'd public-website flow).
        phone_full = '%s%s' % (self.country_code or '', self.phone or '')
        partner = Partner.sudo().create({
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
        # sudo(): see the matching comment in _find_or_create_parent above.
        student_partner = Partner.sudo().create(student_partner_vals)

        student_vals = {
            'name': self.student_name,
            'grade_id': self.grade_id.id if self.grade_id else False,
            'partner_id': student_partner.id,
            'parent_id': parent.id if parent else False,
            'subjects_ids': [(4, self.subject_id.id)] if self.subject_id else False,
        }

        student = Student.create(student_vals)
        return student

    def action_attach_existing_parent(self):
        """Staff clicked "Attach to Existing Parent": open a confirmation wizard
        showing exactly which parent this will attach to, and whether the
        student is a new profile or an existing match — nothing is changed
        until the wizard is confirmed."""
        self.ensure_one()
        if not self.possible_duplicate_parent_id:
            raise UserError('There is no possible duplicate to resolve on this enquiry.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirm Attach to Existing Parent',
            'res_model': 'enquiry.attach.parent.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_enquiry_id': self.id},
        }

    def _do_attach_existing_parent(self):
        """Actually perform the attach — called by EnquiryAttachParentWizard
        after the user confirms. Attaches this enquiry to the existing parent
        (never mutates the existing parent's own data) and finds-or-creates
        the student under that parent — reusing an existing student with a
        matching name if one exists, or adding a new student to that existing
        family otherwise.
        """
        self.ensure_one()
        if not self.possible_duplicate_parent_id:
            raise UserError('There is no possible duplicate to resolve on this enquiry.')
        self.parent_profile_id = self.possible_duplicate_parent_id.id
        self.possible_duplicate_parent_id = False
        if not self.student_profile_id and self.student_name:
            self.student_profile_id = self._find_or_create_student(self.parent_profile_id).id

    def action_create_new_parent_and_student(self):
        """Staff-resolved: the possible duplicate is NOT the same person —
        create a brand new parent/student despite the matching email/phone."""
        self.ensure_one()
        if not self.possible_duplicate_parent_id:
            raise UserError('There is no possible duplicate to resolve on this enquiry.')
        self.possible_duplicate_parent_id = False
        self.with_context(force_new_parent=True)._auto_create_parent_and_student()

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
            subject_name = self.subject_id.name if self.subject_id else "General"
            st_name = self.student_name or self.name or "Unknown Student"
            course_name = f"{subject_name} - {st_name}"
            
            course = self.env['course.master'].create({
                'name': course_name,
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

        # Removed automatic transition to 'Enrolled' stage as requested natively by the user.
        # enrolled_stage = self.env['enquiry.stage'].search([
        #    ('is_enrolled_stage', '=', True)
        # ], limit=1)
        # if enrolled_stage:
        #    self.stage_id = enrolled_stage.id

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

    def unlink(self):
        require_permission(self.env.user, 'enquiry_delete')
        return super().unlink()


class EnquiryAttachParentWizard(models.TransientModel):
    """Confirmation step for Enquiry.action_attach_existing_parent(): shows
    which parent the enquiry will attach to, and whether the student will be
    a newly-created profile or an existing match, before anything is changed.
    """
    _name = 'enquiry.attach.parent.wizard'
    _description = 'Confirm Attach Enquiry to Existing Parent'

    enquiry_id = fields.Many2one('enquiry', required=True, readonly=True)
    student_name = fields.Char(related='enquiry_id.student_name', readonly=True)

    parent_id = fields.Many2one('parent.profile', required=True, readonly=True)
    parent_email = fields.Char(related='parent_id.email', readonly=True)
    parent_phone = fields.Char(related='parent_id.phone', readonly=True)

    matching_student_id = fields.Many2one('student.profile', readonly=True)
    matching_student_grade_id = fields.Many2one(related='matching_student_id.grade_id', readonly=True)
    is_new_student = fields.Boolean(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        enquiry_id = res.get('enquiry_id') or self.env.context.get('default_enquiry_id')
        if enquiry_id:
            enquiry = self.env['enquiry'].browse(enquiry_id)
            parent = enquiry.possible_duplicate_parent_id
            res['parent_id'] = parent.id
            existing_student = self.env['student.profile'].search([
                ('name', '=', enquiry.student_name),
                ('parent_id', '=', parent.id),
            ], limit=1)
            res['matching_student_id'] = existing_student.id
            res['is_new_student'] = not bool(existing_student)
        return res

    def action_confirm(self):
        self.ensure_one()
        self.enquiry_id._do_attach_existing_parent()
        # If this enquiry was part of a multi-student batch submission, resolve
        # any sibling enquiries flagged with the same duplicate parent too, so
        # staff don't have to repeat this confirmation once per sibling.
        if self.enquiry_id.enquiry_batch_id:
            siblings = self.enquiry_id.sibling_enquiry_ids.filtered(
                lambda e: e.possible_duplicate_parent_id == self.parent_id)
            for sib in siblings:
                sib.parent_profile_id = self.parent_id.id
                sib.possible_duplicate_parent_id = False
                if not sib.student_profile_id and sib.student_name:
                    sib.student_profile_id = sib._find_or_create_student(self.parent_id).id
        return {'type': 'ir.actions.act_window_close'}


class EnquiryBatchWizard(models.TransientModel):
    """Lets staff enter multiple students for one parent in a single go from
    the backend, mirroring the public website's multi-student enquiry form.
    Creates one `enquiry` record per student line, all sharing the same
    parent, and (when there's more than one student) grouped under a new
    `enquiry.batch` so the resulting enquiries show up as "Related Enquiries"
    on each other's form.
    """
    _name = 'enquiry.batch.wizard'
    _description = 'New Enquiry (Multiple Students)'

    name = fields.Char(string='Parent / Guardian Name', required=True)
    email = fields.Char(string='Email')
    country_code = fields.Char(string='Country Code', default='+1')
    phone = fields.Char(string='Phone')
    parent_profile_id = fields.Many2one('parent.profile', string='Existing Parent')
    enquiry_source = fields.Selection([
        ('website', 'Website'),
        ('referral', 'Referral'),
        ('phone', 'Phone'),
        ('email', 'Email'),
        ('social_media', 'Social Media'),
        ('walk_in', 'Walk-in'),
        ('other', 'Other'),
    ], string='Source')
    notes = fields.Text(string='Notes')
    student_line_ids = fields.One2many('enquiry.batch.wizard.line', 'wizard_id', string='Students')

    @api.onchange('parent_profile_id')
    def _onchange_parent_profile_id(self):
        if self.parent_profile_id:
            self.name = self.parent_profile_id.name
            self.email = self.parent_profile_id.email
            self.phone = self.parent_profile_id.phone
            self.country_code = self.parent_profile_id.country_code

    def action_create_enquiries(self):
        self.ensure_one()
        if not self.student_line_ids:
            raise UserError('Add at least one student.')

        common = {
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'country_code': self.country_code,
            'parent_profile_id': self.parent_profile_id.id,
            'enquiry_source': self.enquiry_source,
            'notes': self.notes,
        }

        batch = False
        if len(self.student_line_ids) > 1:
            batch = self.env['enquiry.batch'].create({'source': 'backend'})

        first_line = self.student_line_ids[0]
        first = self.env['enquiry'].create(dict(
            common,
            enquiry_batch_id=batch.id if batch else False,
            student_name=first_line.student_name,
            student_age=first_line.student_age,
            category_id=first_line.category_id.id,
            subject_id=first_line.subject_id.id,
            grade_id=first_line.grade_id.id,
        ))

        # Forward the resolved parent to the remaining students so they attach
        # to the same parent instead of each running their own duplicate search.
        rest_common = dict(common, enquiry_batch_id=batch.id if batch else False)
        if first.parent_profile_id:
            rest_common['parent_profile_id'] = first.parent_profile_id.id

        rest_vals = [
            dict(
                rest_common,
                student_name=line.student_name,
                student_age=line.student_age,
                category_id=line.category_id.id,
                subject_id=line.subject_id.id,
                grade_id=line.grade_id.id,
            )
            for line in self.student_line_ids[1:]
        ]
        rest = self.env['enquiry'].create(rest_vals) if rest_vals else self.env['enquiry']

        enquiries = first + rest
        return {
            'type': 'ir.actions.act_window',
            'name': 'Created Enquiries',
            'res_model': 'enquiry',
            'view_mode': 'list,form',
            'domain': [('id', 'in', enquiries.ids)],
        }


class EnquiryBatchWizardLine(models.TransientModel):
    _name = 'enquiry.batch.wizard.line'
    _description = 'Enquiry Batch Wizard Student Line'

    wizard_id = fields.Many2one('enquiry.batch.wizard', required=True, ondelete='cascade')
    student_name = fields.Char(string='Student Name', required=True)
    student_age = fields.Integer(string='Student Age')
    category_id = fields.Many2one('subject.category', string='Category')
    subject_id = fields.Many2one('subject.master', string='Subject', required=True)
    grade_id = fields.Many2one('grade.master', string='Grade', required=True)

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.category_id:
            if self.subject_id and self.subject_id.category_id != self.category_id:
                self.subject_id = False
            if self.grade_id and self.category_id not in self.grade_id.category_ids:
                self.grade_id = False
        else:
            self.subject_id = False
            self.grade_id = False


class DemoSession(models.Model):
    _name = 'demo.session'
    _description = 'Demo Session'

    course_id = fields.Many2one('course.master', string='Course', required=True, ondelete='cascade')
    subject_id = fields.Many2one('subject.master', string='Subject')
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', required=True)

    @api.onchange('course_id')
    def _onchange_course_id(self):
        if self.course_id and self.course_id.subject_id:
            self.subject_id = self.course_id.subject_id.id

    @api.onchange('tutor_id')
    def _onchange_tutor_id_warn(self):
        """Warn when assigning a demo to a tutor different from existing course tutors."""
        if not self.tutor_id or not self.course_id:
            return
        course = self.course_id
        if not course.tutor_id:
            return
        if self.tutor_id not in course.tutor_ids:
            existing = ', '.join(t.name for t in course.tutor_ids)
            return {
                'warning': {
                    'title': 'Multiple Tutors',
                    'message': (
                        'This course is already managed by: %s.\n\n'
                        'Adding a demo with %s will give them portal access to this course '
                        'alongside the existing tutor(s).'
                    ) % (existing, self.tutor_id.name),
                }
            }

    def _sync_tutor_to_course(self):
        """Auto-set course tutor from demo session if not set; add to tutor_ids if new."""
        self.ensure_one()
        course = self.course_id
        if not course or not self.tutor_id:
            return
        if not course.tutor_id:
            course.sudo().write({
                'tutor_id': self.tutor_id.id,
                'tutor_ids': [(4, self.tutor_id.id)],
            })
            course.message_post(
                body='Primary tutor auto-set to <b>%s</b> from demo session.' % self.tutor_id.name,
                subtype_xmlid='mail.mt_note',
            )
        elif self.tutor_id not in course.tutor_ids:
            course.sudo().write({'tutor_ids': [(4, self.tutor_id.id)]})
            course.message_post(
                body=(
                    '&#8505; A demo session was added with tutor <b>%s</b>. '
                    'They have been added to the course and will have portal access alongside: <b>%s</b>.'
                ) % (
                    self.tutor_id.name,
                    ', '.join(t.name for t in course.tutor_ids - self.tutor_id),
                ),
                subtype_xmlid='mail.mt_note',
            )

    scheduled_datetime = fields.Datetime(string='Scheduled Date & Time', required=True)
    timezone = fields.Selection(
        selection=get_tz_selection,
        string='Timezone',
        default=lambda self: self.env.user.tz or DEFAULT_TIMEZONE,
    )
    duration_minutes = fields.Integer(string='Duration (Minutes)', default=30)
    available_tutor_ids = fields.Many2many('tutor.profile', compute='_compute_available_tutors', store=False)
    no_tutor_available = fields.Boolean(compute='_compute_available_tutors', store=False)
    
    @api.depends('scheduled_datetime', 'duration_minutes', 'subject_id', 'timezone')
    def _compute_available_tutors(self):
        for rec in self:
            if not rec.scheduled_datetime:
                rec.available_tutor_ids = self.env['tutor.profile'].search([])
                rec.no_tutor_available = False
                continue

            # scheduled_datetime is stored in UTC — convert to the enquiry's local timezone
            # before extracting hour/minute, so the comparison is in local time (matching
            # the tutor's stored availability which is in the tutor's local time).
            import pytz as _pytz
            enq_tz = _pytz.timezone(rec.timezone or 'UTC')
            local_dt = rec.scheduled_datetime.replace(tzinfo=_pytz.utc).astimezone(enq_tz)

            day_name = local_dt.strftime('%A').lower()
            start_float = local_dt.hour + (local_dt.minute / 60.0)
            end_float = start_float + (rec.duration_minutes / 60.0)

            # Initial domain filter: find tutors available on this day+time
            # (comparison against stored times which are in the tutor's local timezone)
            domain = [('availability_ids.day_of_week', '=', day_name),
                      ('availability_ids.start_time', '<=', start_float),
                      ('availability_ids.end_time', '>=', end_float),
                      ('active', '=', True)]
            if rec.subject_id:
                domain.append(('subject_ids', 'in', rec.subject_id.id))

            candidates = self.env['tutor.profile'].search(domain)

            # Secondary per-tutor filter: adjust for tutors whose timezone differs
            # from the enquiry timezone (convert start_float to each tutor's local time).
            available = self.env['tutor.profile']
            for tutor in candidates:
                tutor_tz_name = tutor.timezone or 'UTC'
                enq_tz_name = rec.timezone or 'UTC'
                if tutor_tz_name == enq_tz_name:
                    available |= tutor
                    continue
                # Convert enquiry local time to tutor's local time
                try:
                    tutor_tz = _pytz.timezone(tutor_tz_name)
                    tutor_dt = local_dt.astimezone(tutor_tz)
                    t_start = tutor_dt.hour + tutor_dt.minute / 60.0
                    t_end = t_start + (rec.duration_minutes / 60.0)
                    covers = tutor.availability_ids.filtered(
                        lambda a, d=day_name, st=t_start, et=t_end: a.day_of_week == d
                        and a.start_time <= st and a.end_time >= et
                    )
                    if covers:
                        available |= tutor
                except Exception:
                    available |= tutor  # include on error rather than silently exclude

            rec.available_tutor_ids = available
            rec.no_tutor_available = not bool(available)

    def _find_demo_conflicts(self):
        """Return existing non-cancelled occurrences that overlap this demo session."""
        self.ensure_one()
        if not self.tutor_id or not self.scheduled_datetime:
            return self.env['class.schedule.occurrence']
        duration = self.duration_minutes or 30
        end_dt = self.scheduled_datetime + timedelta(minutes=duration)
        domain = [
            ('tutor_id', '=', self.tutor_id.id),
            ('lesson_status', 'not in', ['cancelled']),
            ('start_datetime', '<', end_dt),
            ('stop_datetime', '>', self.scheduled_datetime),
        ]
        if self.schedule_occurrence_id:
            domain.append(('id', '!=', self.schedule_occurrence_id.id))
        return self.env['class.schedule.occurrence'].search(domain)

    @api.onchange('tutor_id', 'scheduled_datetime', 'duration_minutes')
    def _onchange_check_demo_overbooking(self):
        """Warn if the selected tutor is already booked at the same time."""
        if not self.tutor_id or not self.scheduled_datetime:
            return
        conflicts = self._find_demo_conflicts()
        if not conflicts:
            return
        lines = []
        for occ in conflicts[:5]:
            dt_str = occ.start_datetime.strftime('%a %d %b %Y %H:%M UTC') if occ.start_datetime else '?'
            lines.append('• %s  (%s)  —  Course: %s' % (occ.name or '?', dt_str, occ.course_id.name or '—'))
        if len(conflicts) > 5:
            lines.append('… and %d more conflict(s).' % (len(conflicts) - 5))
        return {
            'warning': {
                'title': 'Tutor Overbooking — %s' % self.tutor_id.name,
                'message': (
                    'This tutor already has a scheduled lesson at the same time:\n\n%s\n\n'
                    'Please choose a different tutor or time.'
                ) % '\n'.join(lines),
            }
        }

    @api.constrains('tutor_id', 'scheduled_datetime', 'duration_minutes', 'status')
    def _check_no_demo_overbooking(self):
        for rec in self:
            if not rec.tutor_id or not rec.scheduled_datetime or rec.status == 'cancelled':
                continue
            conflicts = rec._find_demo_conflicts()
            if conflicts:
                lines = []
                for c in conflicts[:5]:
                    dt_str = c.start_datetime.strftime('%a %d %b %Y %H:%M UTC') if c.start_datetime else '?'
                    lines.append('  • %s  (%s)  —  %s' % (c.name or '?', dt_str, c.course_id.name or '—'))
                raise ValidationError(
                    'Cannot save: tutor "%s" already has a lesson at the same time:\n\n%s\n\n'
                    'Please choose a different tutor or time.'
                    % (rec.tutor_id.name, '\n'.join(lines))
                )

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
    schedule_occurrence_id = fields.Many2one('class.schedule.occurrence', string='Linked Schedule', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super(DemoSession, self).create(vals_list)
        for rec in records:
            rec._sync_tutor_to_course()
            if rec.status == 'scheduled' and rec.scheduled_datetime and rec.tutor_id:
                rec._create_or_update_schedule()
            if rec.course_id:
                rec.course_id.message_post(
                    body=rec._build_demo_created_log(),
                    subtype_xmlid='mail.mt_note',
                )
        return records

    def _build_demo_created_log(self):
        self.ensure_one()
        if self.scheduled_datetime:
            tz_str = self.timezone or 'UTC'
            dt_str = self.scheduled_datetime.strftime('%d %b %Y %H:%M') + ' (%s)' % tz_str
        else:
            dt_str = '—'
        return Markup(
            '<b>Demo Session Created</b><br/>'
            'Created by: <b>%s</b><br/>'
            'Tutor: <b>%s</b><br/>'
            'Scheduled: <b>%s</b>'
        ) % (
            self.env.user.name,
            self.tutor_id.name if self.tutor_id else '—',
            dt_str,
        )

    def write(self, vals):
        old_statuses = {rec.id: rec.status for rec in self}
        res = super(DemoSession, self).write(vals)
        for rec in self:
            if any(k in vals for k in ['status', 'scheduled_datetime', 'duration_minutes', 'tutor_id']):
                rec._create_or_update_schedule()
            if rec.course_id and old_statuses.get(rec.id) != rec.status:
                if rec.status == 'completed':
                    rec.course_id.message_post(body='Demo completed.', subtype_xmlid='mail.mt_note')
                elif rec.status == 'cancelled':
                    rec.course_id.message_post(body='Demo cancelled.', subtype_xmlid='mail.mt_note')
        return res

    def _create_or_update_schedule(self):
        """Creates or updates a class schedule occurrence for this demo session so it appears on the calendar."""
        self.ensure_one()

        if self.status == 'cancelled' or not self.scheduled_datetime or not self.tutor_id:
            # delete existing schedule if applicable
            if self.schedule_occurrence_id:
                occ = self.schedule_occurrence_id
                self.schedule_occurrence_id = False
                occ.unlink()
            return

        from datetime import timedelta
        end_dt = self.scheduled_datetime + timedelta(minutes=self.duration_minutes)

        # Update or Create Occurrence natively without touching the master Course Schedules (class.schedule)
        occ_vals = {
            'name': f"Demo Class: {self.subject_id.name if self.subject_id else 'General'} - Demo",
            'course_id': self.course_id.id,
            'tutor_id': self.tutor_id.id,
            'start_datetime': self.scheduled_datetime,
            'stop_datetime': end_dt,
            'is_demo': True,
            'lesson_status': 'scheduled',
            'is_rescheduled': False,
        }

        if self.schedule_occurrence_id:
            self.schedule_occurrence_id.write(occ_vals)
        else:
            new_occ = self.env['class.schedule.occurrence'].create(occ_vals)
            self.schedule_occurrence_id = new_occ.id

    def unlink(self):
        """When a demo session is deleted:
        - If the linked occurrence has attendance marked, leave it intact (just detach).
        - If the linked occurrence has no attendance marked, force-delete it regardless of lesson status.
        Future lesson deletion is handled by ClassSchedule.unlink().
        """
        deletion_logs = []
        for rec in self:
            if rec.course_id:
                deletion_logs.append((rec.course_id, rec._build_demo_deleted_log()))
            occ = rec.schedule_occurrence_id
            if not occ:
                continue
            if occ.attendance_marked:
                # Attendance has been recorded — keep the occurrence, just detach the link
                occ.sudo().write({'schedule_id': False})
                rec.schedule_occurrence_id = False
            else:
                # No attendance — safe to delete regardless of lesson status
                occ.with_context(force_delete_lesson=True).sudo().unlink()
        result = super(DemoSession, self).unlink()
        for course, body in deletion_logs:
            course.message_post(body=body, subtype_xmlid='mail.mt_note')
        return result

    def _build_demo_deleted_log(self):
        self.ensure_one()
        if self.scheduled_datetime:
            tz_str = self.timezone or 'UTC'
            dt_str = self.scheduled_datetime.strftime('%d %b %Y %H:%M') + ' (%s)' % tz_str
        else:
            dt_str = '—'
        return Markup(
            '<b>Demo Session Deleted</b><br/>'
            'Deleted by: <b>%s</b><br/>'
            'Tutor: <b>%s</b><br/>'
            'Scheduled: <b>%s</b>'
        ) % (
            self.env.user.name,
            self.tutor_id.name if self.tutor_id else '—',
            dt_str,
        )

    def action_delete_demo(self):
        """Delete the demo session."""
        self.unlink()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Demo Sessions',
            'res_model': 'demo.session',
            'view_mode': 'kanban,list,form',
        }

# -*- coding: utf-8 -*-
"""
Tuition Management — Fine-Grained Permission Groups
====================================================
Model:  user.permission.group
        Wrapper that stores boolean permission flags and syncs membership
        to the corresponding pre-defined res.groups records in
        tuition_permission_security.xml.

Helper: user_has_permission(user, perm_code)   → bool
        require_permission(user, perm_code)     → raises AccessError
"""
from odoo import models, fields, api
from odoo.exceptions import AccessError

# ---------------------------------------------------------------------------
# Mapping: flag field name → XML ID suffix of the corresponding res.group
# ---------------------------------------------------------------------------
PERMISSION_GROUP_MAP = {
    'tutor_pricing_view':         'group_tuition_tutor_pricing_view',
    'tutor_pricing_edit':         'group_tuition_tutor_pricing_edit',
    'tutor_edit':                 'group_tuition_tutor_edit',
    'tutor_delete':               'group_tuition_tutor_delete',
    'tutor_rates_edit':           'group_tuition_tutor_rates_edit',
    'parent_delete':              'group_tuition_parent_delete',
    'student_delete':             'group_tuition_student_delete',
    'parent_invoice_view':           'group_tuition_parent_invoice_view',
    'parent_invoice_generate':       'group_tuition_parent_invoice_generate',
    'parent_invoice_approve':        'group_tuition_parent_invoice_approve',
    'tutor_payroll_view':            'group_tuition_payroll_view',
    'tutor_payroll_generate':        'group_tuition_payroll_generate',
    'tutor_payroll_approve':         'group_tuition_tutor_payroll_approve',
    'subscription_access':        'group_tuition_subscription_access',
    'subscription_add_plan':      'group_tuition_subscription_plan',
    'subscription_add_adjustment':'group_tuition_subscription_adjustment',
    'subscription_add_discount':  'group_tuition_subscription_discount',
    'subscription_plan_delete':        'group_tuition_subscription_plan_delete',
    'subscription_approve':            'group_tuition_subscription_approve',
    'subscription_edit_billing_date':  'group_tuition_subscription_edit_billing_date',
    'subject_edit':               'group_tuition_subject_edit',
    'subject_category_edit':      'group_tuition_subject_category_edit',
    'grades_edit':                'group_tuition_grades_edit',
    'enquiry_delete':             'group_tuition_enquiry_delete',
    'course_delete':              'group_tuition_course_delete',
    'course_cancel':              'group_tuition_course_cancel',
    'settings_access':            'group_tuition_settings_access',
    'reports_access':             'group_tuition_reports_access',
}

# Human-readable labels for error messages
PERMISSION_LABELS = {
    'tutor_pricing_view':         'View Tutor Pricing',
    'tutor_pricing_edit':         'Edit Tutor Pricing',
    'tutor_edit':                 'Edit Tutor Info',
    'tutor_delete':               'Delete Tutors',
    'tutor_rates_edit':           'Edit Tutor Rates',
    'parent_delete':              'Delete Parents',
    'student_delete':             'Delete Students',
    'parent_invoice_view':           'View Parent Invoices',
    'parent_invoice_generate':       'Generate Parent Invoices',
    'parent_invoice_approve':        'Approve Parent Invoicing Runs',
    'tutor_payroll_view':            'View Tutor Payroll',
    'tutor_payroll_generate':        'Generate Tutor Payroll',
    'tutor_payroll_approve':         'Approve Tutor Payroll Runs',
    'subscription_access':        'Access Billing',
    'subscription_add_plan':      'Add Subscription Plans',
    'subscription_add_adjustment':'Add Adjustments',
    'subscription_add_discount':  'Add Discounts',
    'subscription_plan_delete':        'Delete Plan History Lines',
    'subscription_approve':            'Approve Subscription Changes',
    'subscription_edit_billing_date':  'Edit Next Billing Date',
    'subject_edit':               'Edit Subjects',
    'subject_category_edit':      'Edit Subject Categories',
    'grades_edit':                'Edit Grades',
    'enquiry_delete':             'Delete Enquiries',
    'course_delete':              'Delete Courses',
    'course_cancel':              'Cancel Courses',
    'settings_access':            'Access Settings',
    'reports_access':             'Access Reports',
}


# ---------------------------------------------------------------------------
# Public helper functions — import these wherever you need enforcement
# ---------------------------------------------------------------------------

def user_has_permission(user, perm_code):
    """Return True if *user* has the given tuition permission.

    Odoo system administrators (base.group_system) always return True.

    :param user:      res.users browse record (single)
    :param perm_code: key from PERMISSION_GROUP_MAP
    :rtype: bool
    """
    if not user:
        return False
    # Administrators bypass all checks
    if user.has_group('base.group_system'):
        return True
    xml_id_suffix = PERMISSION_GROUP_MAP.get(perm_code)
    if not xml_id_suffix:
        return False
    return user.has_group('tuition_management.' + xml_id_suffix)


def require_permission(user, perm_code):
    """Raise AccessError if *user* lacks the given tuition permission."""
    if not user_has_permission(user, perm_code):
        label = PERMISSION_LABELS.get(perm_code, perm_code)
        raise AccessError(
            "You do not have the required permission: «%s».\n"
            "Contact your administrator to request access." % label
        )


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class UserPermissionGroup(models.Model):
    _name = 'user.permission.group'
    _description = 'Tuition Permission Group'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # ── Identity ──────────────────────────────────────────────────────────
    name = fields.Char(string='Group Name', required=True, tracking=True)
    description = fields.Text(string='Description')

    # Backing res.groups — auto-created when wrapper is saved
    group_id = fields.Many2one(
        'res.groups', string='System Group',
        readonly=True, copy=False, ondelete='set null',
    )

    # Members: internal (non-portal) active users only
    member_ids = fields.Many2many(
        'res.users',
        'user_permission_group_users_rel',
        'perm_group_id', 'user_id',
        string='Members',
        domain=[('share', '=', False), ('active', '=', True)],
    )
    member_count = fields.Integer(
        string='Members', compute='_compute_member_count', store=True)

    # ── Tutor Management ──────────────────────────────────────────────────
    tutor_pricing_view = fields.Boolean(
        string='View Tutor Pricing', tracking=True,
        help='Can view the tutor pricing matrix.')
    tutor_pricing_edit = fields.Boolean(
        string='Edit Tutor Pricing', tracking=True,
        help='Can create and modify tutor pricing entries.')
    tutor_edit = fields.Boolean(
        string='Edit Tutor Info', tracking=True,
        help='Can edit tutor profile information.')
    tutor_delete = fields.Boolean(
        string='Delete Tutors', tracking=True,
        help='Can permanently delete tutor profiles.')
    tutor_rates_edit = fields.Boolean(
        string='Edit Tutor Rates', tracking=True,
        help='Can create and edit tutor subject rate records.')
    parent_delete = fields.Boolean(
        string='Delete Parents', tracking=True,
        help='Can permanently delete parent profiles.')
    student_delete = fields.Boolean(
        string='Delete Students', tracking=True,
        help='Can permanently delete student profiles.')

    # ── Finance ───────────────────────────────────────────────────────────
    parent_invoice_view = fields.Boolean(
        string='View Parent Invoices', tracking=True,
        help='Can view parent/student invoices.')
    parent_invoice_generate = fields.Boolean(
        string='Generate Parent Invoices', tracking=True,
        help='Can generate parent invoices and billing runs.')
    parent_invoice_approve = fields.Boolean(
        string='Approve Parent Invoicing Runs', tracking=True,
        help='Can approve parent billing runs before invoices are generated.')
    tutor_payroll_view = fields.Boolean(
        string='View Tutor Payroll', tracking=True,
        help='Can view tutor payroll runs and statements.')
    tutor_payroll_generate = fields.Boolean(
        string='Generate Tutor Payroll', tracking=True,
        help='Can create and run tutor payroll.')
    tutor_payroll_approve = fields.Boolean(
        string='Approve Tutor Payroll Runs', tracking=True,
        help='Can approve tutor payroll runs before payment.')

    # ── Subscriptions ─────────────────────────────────────────────────────
    subscription_access = fields.Boolean(
        string='Access Billing', tracking=True,
        help='Can see the Billing menu and manage subscriptions.')
    subscription_add_plan = fields.Boolean(
        string='Add Plan Products', tracking=True,
        help='Can add or change plan products in a subscription.')
    subscription_add_adjustment = fields.Boolean(
        string='Add Adjustments', tracking=True,
        help='Can add manual adjustments to a subscription.')
    subscription_add_discount = fields.Boolean(
        string='Add Discounts', tracking=True,
        help='Can add discount records to a subscription.')
    subscription_plan_delete = fields.Boolean(
        string='Delete Plan History Lines', tracking=True,
        help='Can delete rows in the subscription plan history tab.')
    subscription_approve = fields.Boolean(
        string='Approve Subscription Changes', tracking=True,
        help='Can approve or reject draft plan history lines, adjustments, and discounts.')
    subscription_edit_billing_date = fields.Boolean(
        string='Edit Next Billing Date', tracking=True,
        help='Can manually override the auto-calculated next billing date on a subscription.')

    # ── Content Management ────────────────────────────────────────────────
    subject_edit = fields.Boolean(
        string='Edit Subjects', tracking=True,
        help='Can create and edit subject records.')
    subject_category_edit = fields.Boolean(
        string='Edit Subject Categories', tracking=True,
        help='Can create and edit subject category records.')
    grades_edit = fields.Boolean(
        string='Edit Grades', tracking=True,
        help='Can create and edit grade level records.')

    # ── Actions ───────────────────────────────────────────────────────────
    enquiry_delete = fields.Boolean(
        string='Delete Enquiries', tracking=True,
        help='Can permanently delete enquiry records.')
    course_delete = fields.Boolean(
        string='Delete Courses', tracking=True,
        help='Can permanently delete course records.')
    course_cancel = fields.Boolean(
        string='Cancel Courses', tracking=True,
        help='Can cancel active course records.')

    # ── System ────────────────────────────────────────────────────────────
    settings_access = fields.Boolean(
        string='Access Settings Menu', tracking=True,
        help='Can access the Settings section of the Shiningace menu.')
    reports_access = fields.Boolean(
        string='Access Reports', tracking=True,
        help='Can open and run reports.')

    # ── Computed ──────────────────────────────────────────────────────────
    @api.depends('member_ids')
    def _compute_member_count(self):
        for rec in self:
            rec.member_count = len(rec.member_ids)

    # ── ORM overrides ─────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._ensure_res_group()
        self._sync_all_permission_groups()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._sync_all_permission_groups()
        return res

    def unlink(self):
        # Keep references to auto-created system groups before deletion
        auto_groups = self.filtered(lambda r: r.group_id).mapped('group_id')
        priv = self.env.ref(
            'tuition_management.privilege_tuition_management',
            raise_if_not_found=False,
        )
        res = super().unlink()
        # Recompute permission group memberships (now without deleted wrappers)
        self.env['user.permission.group']._sync_all_permission_groups()
        # Remove the auto-created backing res.groups records
        for g in auto_groups:
            if priv and g.privilege_id == priv:
                try:
                    g.sudo().unlink()
                except Exception:
                    pass
        return res

    # ── Internal helpers ──────────────────────────────────────────────────
    def _ensure_res_group(self):
        """Create a backing res.groups for this wrapper if it doesn't exist."""
        if self.group_id:
            # Sync the display name
            self.group_id.sudo().write({'name': 'Tuition / %s' % self.name})
            return
        priv = self.env.ref(
            'tuition_management.privilege_tuition_management',
            raise_if_not_found=False,
        )
        group = self.env['res.groups'].sudo().create({
            'name': 'Tuition / %s' % self.name,
            'privilege_id': priv.id if priv else False,
        })
        self.sudo().write({'group_id': group.id})

    @api.model
    def _sync_all_permission_groups(self):
        """
        Recompute membership of every named permission res.group from the
        current set of wrapper records.

        For each of the 21 permission flags, the corresponding res.group gets
        the union of members from all wrappers that have that flag set to True.

        Also syncs each wrapper's backing group_id.users to its member_ids
        (so the group can be used for @groups= access rights independently).
        """
        all_wrappers = self.sudo().search([])

        for flag, xml_id_suffix in PERMISSION_GROUP_MAP.items():
            perm_group = self.env.ref(
                'tuition_management.' + xml_id_suffix,
                raise_if_not_found=False,
            )
            if not perm_group:
                continue
            user_ids = set()
            for wrapper in all_wrappers:
                if getattr(wrapper, flag):
                    user_ids |= set(wrapper.member_ids.ids)
            perm_group.sudo().write({'user_ids': [(6, 0, list(user_ids))]})

        # Sync each wrapper's backing group
        for wrapper in all_wrappers:
            if wrapper.group_id:
                wrapper.group_id.sudo().write(
                    {'user_ids': [(6, 0, wrapper.member_ids.ids)]}
                )

    # ── Admin action: Bulk assign users ──────────────────────────────────
    def action_bulk_assign_users(self):
        """Open wizard to bulk-assign users to this group."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bulk Assign Users — %s' % self.name,
            'res_model': 'user.permission.group.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_group_id': self.id},
        }

    # ── Admin action: Export permission matrix ────────────────────────────
    def action_export_matrix(self):
        """Download a CSV showing all groups × all permission flags."""
        import io
        import csv
        import base64

        groups = self.search([])
        flags = list(PERMISSION_GROUP_MAP.keys())
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['Group', 'Members'] + [PERMISSION_LABELS.get(f, f) for f in flags])
        for g in groups:
            row = [g.name, len(g.member_ids)]
            for flag in flags:
                row.append('Yes' if getattr(g, flag) else 'No')
            writer.writerow(row)

        csv_data = buf.getvalue().encode('utf-8')
        attachment = self.env['ir.attachment'].create({
            'name': 'tuition_permission_matrix.csv',
            'type': 'binary',
            'datas': base64.b64encode(csv_data),
            'mimetype': 'text/csv',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'self',
        }

    # ── Post-install default setup ────────────────────────────────────────
    @api.model
    def setup_default_group(self):
        """
        Called from post_init_hook.
        Creates a 'Full Access (Default)' group with ALL permissions enabled
        and adds all current internal users to it.
        Skipped if any permission groups already exist (idempotent).
        """
        if self.search_count([]):
            return  # Already configured — respect existing setup

        all_internal = self.env['res.users'].search([
            ('share', '=', False),
            ('active', '=', True),
        ])

        all_true_flags = {flag: True for flag in PERMISSION_GROUP_MAP}
        all_true_flags.update({
            'name': 'Full Access (Default)',
            'description': (
                'Auto-created on module install. All existing internal users '
                'have full access. Adjust as needed in Settings → Permissions.'
            ),
            'member_ids': [(6, 0, all_internal.ids)],
        })
        self.sudo().create(all_true_flags)


# ---------------------------------------------------------------------------
# Wizard: bulk assign users to a group
# ---------------------------------------------------------------------------

class UserPermissionGroupAssignWizard(models.TransientModel):
    _name = 'user.permission.group.assign.wizard'
    _description = 'Bulk Assign Users to Permission Group'

    group_id = fields.Many2one('user.permission.group', string='Permission Group', required=True)
    user_ids = fields.Many2many(
        'res.users',
        'perm_assign_wizard_users_rel',
        'wizard_id', 'user_id',
        string='Users to Add',
        domain=[('share', '=', False), ('active', '=', True)],
    )
    replace = fields.Boolean(
        string='Replace existing members',
        help='If checked, the group members will be replaced by the selected users. '
             'If unchecked, the selected users are added to existing members.',
    )

    def action_confirm(self):
        self.ensure_one()
        if self.replace:
            self.group_id.write({'member_ids': [(6, 0, self.user_ids.ids)]})
        else:
            self.group_id.write({'member_ids': [(4, uid) for uid in self.user_ids.ids]})
        return {'type': 'ir.actions.act_window_close'}

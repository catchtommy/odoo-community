# -*- coding: utf-8 -*-
import base64
import calendar
import io
from datetime import timedelta

import xlsxwriter

from odoo import api, fields, models

# Enquiry statuses that are neither converted (enrolled) nor lost.
PENDING_STATUSES = ('new', 'demo_scheduled', 'demo_completed')


class TuitionEnquiryReportWizard(models.TransientModel):
    """Interactive report wizard: enquiries created in a date range, counted
    by their current status and grouped by day / week / month."""

    _name = 'tuition.enquiry.report.wizard'
    _description = 'Enquiry Report Wizard'
    _inherit = 'tuition.date.range.wizard.mixin'

    from_date = fields.Date(
        string='From Date',
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    to_date = fields.Date(
        string='To Date',
        default=lambda self: fields.Date.context_today(self).replace(
            day=calendar.monthrange(
                fields.Date.context_today(self).year,
                fields.Date.context_today(self).month,
            )[1]
        ),
    )
    group_by = fields.Selection(
        [('range', 'Date Range'), ('day', 'Day'), ('week', 'Week'), ('month', 'Month')],
        string='Group By',
        default='range',
        help='Date Range shows one row totalling the whole From–To period.',
    )
    line_ids = fields.One2many('tuition.enquiry.report.wizard.line', 'wizard_id', string='Lines')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        from_date = fields.Date.to_date(vals.get('from_date')) or today.replace(day=1)
        to_date = fields.Date.to_date(vals.get('to_date')) or today.replace(day=calendar.monthrange(today.year, today.month)[1])
        if 'line_ids' in fields_list:
            vals['line_ids'] = [(0, 0, line) for line in self._get_line_values(
                from_date, to_date, vals.get('group_by', 'range'),
                vals.get('report_tz') or self._default_report_tz(),
            )]
        return vals

    @staticmethod
    def _period_bounds(period_start, group_by, from_date, to_date):
        """First/last local date of a grouped period, clipped to the report's
        date range (a week/month bucket can start before From Date or end after To Date)."""
        if group_by == 'range':
            return from_date, to_date
        if group_by == 'week':
            last_date = period_start + timedelta(days=6)
        elif group_by == 'month':
            last_date = period_start.replace(day=calendar.monthrange(period_start.year, period_start.month)[1])
        else:
            last_date = period_start
        return max(period_start, from_date), min(last_date, to_date)

    @staticmethod
    def _period_label(first_date, last_date):
        if first_date == last_date:
            return first_date.strftime('%d %b %Y')
        return '%s – %s' % (first_date.strftime('%d %b %Y'), last_date.strftime('%d %b %Y'))

    def _date_range_domain(self):
        # Enquiries are dated by when they were created, not by a lesson start.
        self.ensure_one()
        self._check_date_range()
        start, end = self._local_dates_to_utc(self.from_date, self.to_date, self.report_tz)
        return [('create_date', '>=', start), ('create_date', '<', end)]

    def _get_line_values(self, from_date, to_date, group_by='range', tz_name='UTC'):
        if from_date > to_date:
            return []
        tz_name = self._valid_tz_name(tz_name)
        start, end = self._local_dates_to_utc(from_date, to_date, tz_name)
        # create_date is naive UTC; bucket each enquiry by its date in tz_name.
        if group_by == 'range':
            # One bucket for the whole period; from_date is a date object, so its
            # ISO form is a safe literal.
            group_expr = f"DATE '{from_date.isoformat()}'"
        elif group_by == 'week':
            group_expr = "date_trunc('week', enq.local_dt)::date"
        elif group_by == 'month':
            group_expr = "date_trunc('month', enq.local_dt)::date"
        else:
            group_expr = "enq.local_dt::date"
        self.env.cr.execute(
            f"""
            WITH enq AS (
                SELECT
                    e.status,
                    (e.create_date AT TIME ZONE 'UTC') AT TIME ZONE %s AS local_dt
                FROM enquiry e
                WHERE e.create_date >= %s
                  AND e.create_date < %s
            )
            SELECT
                {group_expr} AS report_date,
                COUNT(*)::integer AS total_enquiries,
                COUNT(*) FILTER (WHERE enq.status = 'new')::integer AS new_enquiries,
                COUNT(*) FILTER (WHERE enq.status = 'demo_scheduled')::integer AS demo_scheduled,
                COUNT(*) FILTER (WHERE enq.status = 'demo_completed')::integer AS demo_completed,
                COUNT(*) FILTER (WHERE enq.status = 'enrolled')::integer AS converted,
                COUNT(*) FILTER (WHERE enq.status = 'lost')::integer AS lost,
                COUNT(*) FILTER (WHERE enq.status IN %s)::integer AS pending
            FROM enq
            GROUP BY {group_expr}
            ORDER BY {group_expr}
            """,
            (tz_name, start, end, PENDING_STATUSES),
        )
        rows = self.env.cr.fetchall()
        if group_by == 'range' and not rows:
            # Always show the period row, even when nothing was created in it.
            rows = [(from_date, 0, 0, 0, 0, 0, 0, 0)]
        lines = []
        for row in rows:
            first_date, last_date = self._period_bounds(row[0], group_by, from_date, to_date)
            lines.append({
                'report_date': row[0],
                'period_label': self._period_label(first_date, last_date),
                'tz_abbr': self._tz_abbr_on(first_date, tz_name),
                'total_enquiries': row[1],
                'new_enquiries': row[2],
                'demo_scheduled': row[3],
                'demo_completed': row[4],
                'converted': row[5],
                'lost': row[6],
                'pending': row[7],
            })
        return lines

    def _refresh_lines(self):
        for rec in self:
            rec._check_date_range()
            rec.line_ids.unlink()
            for line in self._get_line_values(rec.from_date, rec.to_date, rec.group_by or 'range', rec.report_tz):
                line['wizard_id'] = rec.id
                self.env['tuition.enquiry.report.wizard.line'].create(line)

    def action_refresh(self):
        # Refresh in place — must NOT return a new act_window action, or the
        # client pushes a second, duplicate breadcrumb/header for the same record.
        self.ensure_one()
        self._refresh_lines()

    def action_clear_filters(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        self.write({
            'from_date': today.replace(day=1),
            'to_date': today.replace(day=calendar.monthrange(today.year, today.month)[1]),
            'group_by': 'range',
            'report_tz': self._default_report_tz(),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Enquiry Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def _open_enquiries(self, name, domain):
        """Enquiry list for a [start, end) UTC window, with creation times
        shown in the report timezone."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'enquiry',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('tuition_management.view_report_enquiry_drilldown_list').id, 'list'),
                (False, 'form'),
            ],
            'domain': domain,
            'context': {'create': False, 'tz': self._get_report_tz_name()},
            'target': 'current',
        }

    def action_export_excel(self):
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Enquiry Report')

        title_fmt = workbook.add_format({'bold': True, 'font_size': 13})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#2E86AB', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center'})
        cell_fmt = workbook.add_format({'border': 1})
        text_fmt = workbook.add_format({'border': 1, 'align': 'center'})
        num_fmt = workbook.add_format({'num_format': '#,##0', 'border': 1, 'align': 'center'})
        total_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0', 'bg_color': '#F0F0F0', 'border': 1, 'align': 'center'})
        total_lbl_fmt = workbook.add_format({'bold': True, 'bg_color': '#F0F0F0', 'border': 1})

        sheet.write(0, 0, 'Enquiry Report', title_fmt)
        sheet.write(1, 0, f"Period: {self.from_date} to {self.to_date} ({self._get_report_tz_name()})")

        headers = ['Date Range', 'TZ', 'Total Created', 'New', 'Demo Scheduled', 'Demo Completed', 'Converted', 'Lost', 'Pending']
        col_widths = [28, 8, 14, 10, 16, 16, 12, 10, 12]
        for col, (h, w) in enumerate(zip(headers, col_widths)):
            sheet.write(3, col, h, header_fmt)
            sheet.set_column(col, col, w)

        totals = [0] * 7
        for row_idx, line in enumerate(self.line_ids, start=4):
            sheet.write(row_idx, 0, line.period_label or '', cell_fmt)
            sheet.write(row_idx, 1, line.tz_abbr or '', text_fmt)
            nums = [
                line.total_enquiries, line.new_enquiries, line.demo_scheduled,
                line.demo_completed, line.converted, line.lost, line.pending,
            ]
            for col, val in enumerate(nums, start=2):
                sheet.write(row_idx, col, val, num_fmt)
                totals[col - 2] += val

        total_row = 4 + len(self.line_ids)
        sheet.write(total_row, 0, 'Total', total_lbl_fmt)
        sheet.write(total_row, 1, '', total_lbl_fmt)
        for col, val in enumerate(totals, start=2):
            sheet.write(total_row, col, val, total_fmt)

        workbook.close()
        attachment = self.env['ir.attachment'].create({
            'name': f'Enquiry_Report_{self.from_date}_{self.to_date}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.getvalue()),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


class TuitionEnquiryReportWizardLine(models.TransientModel):
    """One line per grouped creation-date period; each count drills down to its enquiries."""

    _name = 'tuition.enquiry.report.wizard.line'
    _description = 'Enquiry Report Line'
    _order = 'report_date'

    wizard_id = fields.Many2one('tuition.enquiry.report.wizard', required=True, ondelete='cascade')
    report_date = fields.Date(string='Period Start', readonly=True)
    period_label = fields.Char(string='Date Range', readonly=True)
    tz_abbr = fields.Char(string='TZ', readonly=True)
    total_enquiries = fields.Integer(string='Total Created', readonly=True)
    new_enquiries = fields.Integer(string='New', readonly=True)
    demo_scheduled = fields.Integer(string='Demo Scheduled', readonly=True)
    demo_completed = fields.Integer(string='Demo Completed', readonly=True)
    converted = fields.Integer(string='Converted', readonly=True)
    lost = fields.Integer(string='Lost', readonly=True)
    pending = fields.Integer(string='Pending', readonly=True)

    def _period_domain(self):
        """create_date bounds of this line's period in the wizard's timezone."""
        self.ensure_one()
        wizard = self.wizard_id
        first_date, last_date = wizard._period_bounds(
            self.report_date, wizard.group_by or 'range', wizard.from_date, wizard.to_date)
        start, end = wizard._local_dates_to_utc(first_date, last_date, wizard.report_tz)
        return [('create_date', '>=', start), ('create_date', '<', end)]

    def _open(self, label, status_domain):
        return self.wizard_id._open_enquiries(label, self._period_domain() + status_domain)

    def action_view_total(self):
        return self._open('Enquiries Created', [])

    def action_view_new(self):
        return self._open('New Enquiries', [('status', '=', 'new')])

    def action_view_demo_scheduled(self):
        return self._open('Demo Scheduled', [('status', '=', 'demo_scheduled')])

    def action_view_demo_completed(self):
        return self._open('Demo Completed', [('status', '=', 'demo_completed')])

    def action_view_converted(self):
        return self._open('Converted Enquiries', [('status', '=', 'enrolled')])

    def action_view_lost(self):
        return self._open('Lost Enquiries', [('status', '=', 'lost')])

    def action_view_pending(self):
        return self._open('Pending Enquiries', [('status', 'in', list(PENDING_STATUSES))])

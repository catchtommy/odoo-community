# -*- coding: utf-8 -*-
from werkzeug.urls import url_quote_plus
from urllib.parse import urlparse

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from .portal_mixin import PortalMixin


class VirtualClassroomPortal(http.Controller, PortalMixin):

    def _redirect_with_error(self, fallback_url, error):
        message = url_quote_plus(str(error))
        separator = '&' if '?' in fallback_url else '?'
        return request.redirect('%s%svc_error=%s' % (fallback_url, separator, message))

    @http.route('/bigbluebutton/api/<string:action>', type='http', auth='public',
                website=False, csrf=False)
    def bbb_local_url_redirect(self, action, **kw):
        """Forward stale Odoo-host BBB links to the configured BBB server."""
        server_url = request.env['ir.config_parameter'].sudo().get_param(
            'tuition_management.bbb_server_url'
        )
        server_url = (server_url or '').rstrip('/')
        parsed_url = urlparse(server_url)
        if parsed_url.scheme not in ('http', 'https') or not parsed_url.netloc:
            return request.not_found()
        if parsed_url.hostname in ('localhost', '127.0.0.1'):
            return request.not_found()

        query_string = request.httprequest.query_string.decode()
        redirect_url = '%s/bigbluebutton/api/%s' % (server_url, action)
        if query_string:
            redirect_url = '%s?%s' % (redirect_url, query_string)
        return request.redirect(redirect_url, code=302, local=False)

    @http.route('/my/tutor/lesson/<int:occurrence_id>/start-class', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def tutor_start_class(self, occurrence_id, provider=None, **kw):
        fallback = request.httprequest.referrer or '/my/tutor/schedule'
        tutor = self._get_tutor()
        occurrence = request.env['class.schedule.occurrence'].sudo().browse(occurrence_id)
        if not tutor or not occurrence.exists() or occurrence.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/schedule')
        try:
            service = request.env['virtual.classroom.service']
            meeting = service.start_meeting(occurrence, provider)
            url = service.get_tutor_start_url(meeting, tutor)
        except (AccessError, UserError) as exc:
            return self._redirect_with_error(fallback, exc)
        return request.redirect(url or fallback, local=not bool(url))

    @http.route('/my/student/lesson/<int:occurrence_id>/join-class', type='http',
                auth='user', website=True)
    def student_join_class(self, occurrence_id, **kw):
        fallback = request.httprequest.referrer or '/my/student/schedule'
        student = self._get_student()
        occurrence = request.env['class.schedule.occurrence'].sudo().browse(occurrence_id)
        if not student or not occurrence.exists():
            return request.redirect('/my/student/schedule')
        try:
            url = request.env['virtual.classroom.service'].get_student_join_url(occurrence, student)
        except (AccessError, UserError) as exc:
            return self._redirect_with_error(fallback, exc)
        return request.redirect(url, local=False)

from odoo import http
from odoo.http import request
from odoo.addons.web.controllers import main as web
import base64
import json
import logging

_logger = logging.getLogger(__name__)


class ShiningAceMoodleImportController(http.Controller):
    """
    Controller for Moodle XML import handling.
    Provides endpoints for programmatic import and validation.
    """

    @http.route('/shiningace/moodle/import/validate', type='http', methods=['POST'], auth='user', csrf=False)
    def validate_moodle_xml(self, **kwargs):
        """
        Validate a Moodle XML file and return metadata about its contents.
        Used by the import wizard to show preview before importing.
        """
        try:
            xml_file = request.httprequest.files.get('file')
            if not xml_file:
                return json.dumps({'error': 'No file uploaded'})

            xml_data = xml_file.read()
            from lxml import etree
            root = etree.fromstring(xml_data)

            questions = root.findall('.//question')
            if not questions:
                questions = root.findall('question')

            question_types = {}
            total = len(questions)
            for q in questions:
                qtype = q.get('type', 'unknown')
                question_types[qtype] = question_types.get(qtype, 0) + 1

            return json.dumps({
                'success': True,
                'total_questions': total,
                'question_types': question_types,
                'file_name': xml_file.filename,
            })

        except Exception as e:
            _logger.exception("Error validating Moodle XML")
            return json.dumps({'error': str(e)})

    @http.route('/shiningace/moodle/import/preview', type='http', methods=['POST'], auth='user', csrf=False)
    def preview_moodle_xml(self, **kwargs):
        """
        Preview the first few questions from a Moodle XML file.
        """
        try:
            xml_file = request.httprequest.files.get('file')
            if not xml_file:
                return json.dumps({'error': 'No file uploaded'})

            xml_data = xml_file.read()
            from lxml import etree
            root = etree.fromstring(xml_data)

            questions = root.findall('.//question')
            if not questions:
                questions = root.findall('question')

            preview = []
            for q in questions[:10]:  # Preview first 10
                name_elem = q.find('name')
                name = ''
                if name_elem is not None:
                    text_elem = name_elem.find('text')
                    if text_elem is not None and text_elem.text:
                        name = text_elem.text.strip()

                preview.append({
                    'name': name or 'Unnamed',
                    'type': q.get('type', 'unknown'),
                })

            return json.dumps({
                'success': True,
                'preview': preview,
                'total': len(questions),
            })

        except Exception as e:
            _logger.exception("Error previewing Moodle XML")
            return json.dumps({'error': str(e)})

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging
import re
from lxml import etree
from io import StringIO

_logger = logging.getLogger(__name__)


class ShiningAceImportMoodleWizard(models.TransientModel):
    """
    Wizard for importing questions from Moodle XML export files.
    """
    _name = 'shiningace.import.moodle.wizard'
    _description = 'Import Moodle XML Wizard'

    moodle_xml_file = fields.Binary(string='Moodle XML File', required=True)
    file_name = fields.Char(string='File Name')
    subject_id = fields.Many2one(
        'shiningace.subject',
        string='Target Subject',
        required=True,
        help="Subject to assign imported questions to"
    )
    default_difficulty = fields.Selection([
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
        ('very_hard', 'Very Hard'),
    ], string='Default Difficulty', default='medium',
        help="Default difficulty level for imported questions without difficulty metadata")
    skip_existing = fields.Boolean(
        string='Skip Existing Questions',
        default=True,
        help="If a question with the same Moodle ID already exists, skip it."
    )
    overwrite_existing = fields.Boolean(
        string='Overwrite Existing',
        default=False,
        help="If a question with the same Moodle ID exists, update its content."
    )
    default_tag_ids = fields.Many2many(
        'shiningace.question.tag',
        string='Default Tags',
        help="Tags to apply to all imported questions"
    )

    # Import statistics
    total_found = fields.Integer(string='Total Found', readonly=True)
    imported = fields.Integer(string='Imported', readonly=True)
    skipped = fields.Integer(string='Skipped', readonly=True)
    errors = fields.Integer(string='Errors', readonly=True)
    import_log = fields.Text(string='Import Log', readonly=True)

    # Mapping from Moodle question types to our internal types
    MOODLE_TYPE_MAP = {
        'multichoice': 'multichoice',
        'truefalse': 'truefalse',
        'shortanswer': 'shortanswer',
        'numerical': 'numerical',
        'calculated': 'calculated',
        'calculatedsimple': 'calculated_simple',
        'calculatedmulti': 'calculated_multi',
        'essay': 'essay',
        'matching': 'matching',
        'draganddrop': 'drag_drop',
        'draganddropimage': 'drag_drop_image',
        'draganddropmarker': 'drag_drop_marker',
        'cloze': 'cloze',
        'description': 'description',
        'randomsamatch': 'random_short_match',
    }

    def action_import(self):
        """Main import method - parses Moodle XML and creates questions."""
        if not self.moodle_xml_file:
            raise UserError(_('Please upload a Moodle XML file.'))

        # Decode the file
        try:
            xml_data = base64.b64decode(self.moodle_xml_file)
            xml_content = xml_data.decode('utf-8')
        except Exception as e:
            raise UserError(_('Could not read the file: %s') % str(e))

        # Parse XML
        try:
            root = etree.fromstring(xml_data)
        except etree.XMLSyntaxError as e:
            raise UserError(_('Invalid XML file: %s') % str(e))

        # Find all question elements
        question_elements = root.findall('.//question')

        if not question_elements:
            # Try alternate Moodle format
            question_elements = root.findall('question')

        if not question_elements:
            raise UserError(_(
                'No questions found in the XML file. Please ensure this is a valid Moodle XML export.'
            ))

        self.total_found = len(question_elements)
        imported_count = 0
        skipped_count = 0
        error_count = 0
        log_lines = []

        Question = self.env['shiningace.question']
        QuestionType = self.env['shiningace.question.type']
        Answer = self.env['shiningace.question.answer']

        for q_elem in question_elements:
            try:
                result = self._import_single_question(q_elem, Question, QuestionType, Answer)
                if result == 'imported':
                    imported_count += 1
                    log_lines.append(_('✓ Imported: %s') % q_elem.get('name', 'Unknown'))
                elif result == 'skipped':
                    skipped_count += 1
                    log_lines.append(_('⏭ Skipped: %s (already exists)') % q_elem.get('name', 'Unknown'))
                else:
                    error_count += 1
                    log_lines.append(_('✗ Error: %s - %s') % (
                        q_elem.get('name', 'Unknown'), result))
            except Exception as e:
                error_count += 1
                log_lines.append(_('✗ Error: %s') % str(e))
                _logger.exception("Import error for question: %s", q_elem.get('name', 'Unknown'))
                continue

        self.imported = imported_count
        self.skipped = skipped_count
        self.errors = error_count
        self.import_log = '\n'.join(log_lines)

        # Create import log record
        ImportLog = self.env['shiningace.moodle.import.log']
        log = ImportLog.create({
            'name': _('Moodle Import - %s') % (self.file_name or 'Unknown'),
            'file_name': self.file_name,
            'file_data': self.moodle_xml_file,
            'total_questions': self.total_found,
            'imported_count': imported_count,
            'skipped_count': skipped_count,
            'error_count': error_count,
            'state': 'completed' if error_count == 0 else 'partial',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'shiningace.import.moodle.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'show_import_result': True},
        }

    def _import_single_question(self, q_elem, Question, QuestionType, Answer):
        """
        Import a single question from Moodle XML element.
        Supports all standard Moodle question types.
        """
        # Get basic question info
        moodle_type = q_elem.get('type', '')
        internal_type = self.MOODLE_TYPE_MAP.get(moodle_type, 'multichoice')

        question_type = QuestionType.search([('code', '=', internal_type)], limit=1)
        if not question_type:
            return _('Unknown question type: %s') % moodle_type

        # Get question name
        name_elem = q_elem.find('name')
        name = ''
        if name_elem is not None:
            text_elem = name_elem.find('text')
            if text_elem is not None and text_elem.text:
                name = text_elem.text.strip()

        # Get question text
        qtext_elem = q_elem.find('questiontext')
        question_text = ''
        if qtext_elem is not None:
            text_elem = qtext_elem.find('text')
            if text_elem is not None and text_elem.text:
                question_text = text_elem.text.strip()
                # Handle CDATA
                if not question_text and text_elem.text is not None:
                    question_text = text_elem.text

        if not question_text and not name:
            return 'Empty question (no name or text)'

        # Get Moodle ID if present
        moodle_id = None
        id_elem = q_elem.find('id')
        if id_elem is not None and id_elem.text:
            try:
                moodle_id = int(id_elem.text)
            except ValueError:
                pass

        # Check if existing
        if moodle_id and self.skip_existing:
            existing = Question.search([('moodle_id', '=', moodle_id)], limit=1)
            if existing:
                if self.overwrite_existing:
                    # Update existing
                    vals = self._prepare_question_vals(
                        q_elem, question_type, name, question_text, moodle_id
                    )
                    existing.write(vals)
                    self._import_answers(q_elem, existing)
                    return 'imported'
                return 'skipped'

        # Create the question
        vals = self._prepare_question_vals(
            q_elem, question_type, name, question_text, moodle_id
        )
        question = Question.create(vals)

        # Import answers/choices
        self._import_answers(q_elem, question)

        # Import matching pairs
        if moodle_type == 'matching':
            self._import_matching_pairs(q_elem, question)

        # Import general feedback
        self._import_feedback(q_elem, question)

        # Store original XML for reference
        question.write({
            'moodle_xml': etree.tostring(q_elem, pretty_print=True, encoding='unicode'),
        })

        return 'imported'

    def _prepare_question_vals(self, q_elem, question_type, name, question_text, moodle_id=None):
        """Prepare question creation values from Moodle XML element."""
        vals = {
            'name': name or _('Imported Question'),
            'question_text': question_text or '',
            'question_type_id': question_type.id,
            'subject_id': self.subject_id.id,
            'difficulty_level': self.default_difficulty,
            'state': 'draft',
        }

        if moodle_id:
            vals['moodle_id'] = moodle_id

        # Default mark
        default_mark_elem = q_elem.find('defaultgrade')
        if default_mark_elem is not None and default_mark_elem.text:
            try:
                vals['default_mark'] = float(default_mark_elem.text)
            except ValueError:
                pass

        # Penalty
        penalty_elem = q_elem.find('penalty')
        if penalty_elem is not None and penalty_elem.text:
            vals['type_config'] = f'{{"penalty": {penalty_elem.text}}}'

        # Apply default tags
        if self.default_tag_ids:
            vals['tags'] = [(4, tag.id) for tag in self.default_tag_ids]

        return vals

    def _import_answers(self, q_elem, question):
        """Import answer choices from Moodle XML."""
        Answer = self.env['shiningace.question.answer']
        existing = self.env['shiningace.question.answer']

        # Clear existing answers if any (for overwrite)
        question.answer_ids.unlink()

        moodle_type = q_elem.get('type', '')

        if moodle_type in ('multichoice', 'truefalse', 'shortanswer'):
            for answer_elem in q_elem.findall('answer'):
                text_elem = answer_elem.find('text')
                answer_text = ''
                if text_elem is not None and text_elem.text:
                    answer_text = text_elem.text

                fraction = 0.0
                fraction_str = answer_elem.get('fraction', '0')
                try:
                    fraction = float(fraction_str) / 100.0  # Moodle uses 0-100
                except ValueError:
                    pass

                # Feedback
                feedback_text = ''
                feedback_elem = answer_elem.find('feedback')
                if feedback_elem is not None:
                    fb_text_elem = feedback_elem.find('text')
                    if fb_text_elem is not None and fb_text_elem.text:
                        feedback_text = fb_text_elem.text

                Answer.create({
                    'question_id': question.id,
                    'answer_text': answer_text or _('(empty)'),
                    'is_correct': fraction > 0,
                    'fraction': fraction,
                    'feedback': feedback_text,
                })

        elif moodle_type == 'numerical':
            for answer_elem in q_elem.findall('answer'):
                text_elem = answer_elem.find('text')
                answer_text = ''
                tolerance = 0
                if text_elem is not None and text_elem.text:
                    answer_text = text_elem.text

                try:
                    tolerance = float(answer_elem.get('tolerance', 0))
                except ValueError:
                    pass

                fraction = 0.0
                fraction_str = answer_elem.get('fraction', '0')
                try:
                    fraction = float(fraction_str) / 100.0
                except ValueError:
                    pass

                Answer.create({
                    'question_id': question.id,
                    'answer_text': answer_text,
                    'numerical_answer': float(answer_text) if answer_text else 0,
                    'numerical_tolerance': tolerance,
                    'is_correct': fraction > 0,
                    'fraction': fraction,
                })

    def _import_matching_pairs(self, q_elem, question):
        """Import matching pairs for matching-type questions."""
        Matching = self.env['shiningace.question.matching']
        Matching.search([('question_id', '=', question.id)]).unlink()

        for sub_q_elem in q_elem.findall('subquestion'):
            text_elem = sub_q_elem.find('text')
            question_text = ''
            if text_elem is not None and text_elem.text:
                question_text = text_elem.text

            answer_elem = sub_q_elem.find('answer')
            answer_text = ''
            if answer_elem is not None:
                ans_text_elem = answer_elem.find('text')
                if ans_text_elem is not None and ans_text_elem.text:
                    answer_text = ans_text_elem.text

            Matching.create({
                'question_id': question.id,
                'question_text': question_text or '',
                'answer_text': answer_text or '',
            })

    def _import_feedback(self, q_elem, question):
        """Import general feedback from Moodle XML."""
        Feedback = self.env['shiningace.question.feedback']

        fb_elem = q_elem.find('generalfeedback')
        if fb_elem is not None:
            text_elem = fb_elem.find('text')
            if text_elem is not None and text_elem.text:
                Feedback.create({
                    'question_id': question.id,
                    'feedback_type': 'general',
                    'feedback_text': text_elem.text,
                })

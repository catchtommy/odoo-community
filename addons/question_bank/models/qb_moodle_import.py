# -*- coding: utf-8 -*-
import base64
import re
import json
import xml.etree.ElementTree as ET
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import html


class QbMoodleImport(models.TransientModel):
    _name = 'qb.moodle.import'
    _description = 'Moodle XML Import Wizard'

    xml_file = fields.Binary(string='Moodle XML File', required=True)
    filename = fields.Char(string='Filename')
    state = fields.Selection([
        ('upload', 'Upload'),
        ('preview', 'Preview'),
        ('done', 'Done')
    ], default='upload', string='State')
    
    # Preview fields
    preview_line_ids = fields.One2many('qb.moodle.import.line', 'import_id', string='Preview Lines')
    total_questions = fields.Integer(compute='_compute_stats', string='Total Questions')
    selected_questions = fields.Integer(compute='_compute_stats', string='Selected Questions')
    
    # Import options
    subject_id = fields.Many2one('qb.subject', string='Default Subject', required=True)
    topic_id = fields.Many2one('qb.topic', string='Default Topic')
    create_categories_as_topics = fields.Boolean(string='Create Categories as Topics', default=True)
    skip_duplicates = fields.Boolean(string='Skip Duplicate Questions', default=True)

    @api.depends('preview_line_ids', 'preview_line_ids.selected')
    def _compute_stats(self):
        for rec in self:
            rec.total_questions = len(rec.preview_line_ids)
            rec.selected_questions = len(rec.preview_line_ids.filtered('selected'))

    def action_parse_xml(self):
        """Parse the uploaded XML file and show preview"""
        self.ensure_one()
        
        if not self.xml_file:
            raise UserError(_('Please upload an XML file.'))
        
        try:
            xml_content = base64.b64decode(self.xml_file)
            root = ET.fromstring(xml_content)
            
            # Clear existing preview lines
            self.preview_line_ids.unlink()
            
            # Parse questions
            preview_lines = []
            for question_elem in root.findall('question'):
                parsed_data = self._parse_question(question_elem)
                if parsed_data:
                    preview_lines.append((0, 0, parsed_data))
            
            self.preview_line_ids = preview_lines
            self.state = 'preview'
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'qb.moodle.import',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }
            
        except ET.ParseError as e:
            raise UserError(_('Invalid XML file: %s') % str(e))
        except Exception as e:
            raise UserError(_('Error parsing XML: %s') % str(e))

    def _parse_question(self, question_elem):
        """Parse a single question element"""
        qtype = question_elem.get('type')
        
        # Skip category questions
        if qtype == 'category':
            return None
        
        # Extract basic info
        name_elem = question_elem.find('name/text')
        question_text_elem = question_elem.find('questiontext/text')
        
        if name_elem is None or question_text_elem is None:
            return None
        
        name = name_elem.text or 'Untitled'
        question_text = self._clean_html(question_text_elem.text or '')
        
        # Extract category
        category = ''
        category_elem = question_elem.find('.//category/text')
        if category_elem is not None:
            category = category_elem.text or ''
        
        # Detect LaTeX
        has_latex = self._detect_latex(question_text)
        
        # Extract images from question text
        images = self._extract_images(question_text_elem)
        
        # Parse answers based on question type
        answers_data = []
        correct_answer = ''
        
        if qtype == 'multichoice':
            answers_data, correct_answer = self._parse_multichoice(question_elem)
        elif qtype == 'truefalse':
            answers_data, correct_answer = self._parse_truefalse(question_elem)
        elif qtype in ['shortanswer', 'numerical']:
            answers_data, correct_answer = self._parse_shortanswer(question_elem)
        
        # Extract general feedback
        feedback = ''
        feedback_elem = question_elem.find('generalfeedback/text')
        if feedback_elem is not None:
            feedback = self._clean_html(feedback_elem.text or '')
        
        return {
            'name': name[:200],  # Limit length
            'question_text': question_text,
            'question_type': self._map_question_type(qtype),
            'category': category,
            'has_latex': has_latex,
            'has_images': bool(images),
            'images_data': str(images) if images else '',
            'answers_preview': self._format_answers_preview(answers_data),
            # Store as real JSON (answers can contain quotes/HTML, so Python str() is unsafe)
            'answers_json': json.dumps(answers_data),
            'correct_answer': correct_answer,
            'feedback': feedback,
            'selected': True,
            'moodle_type': qtype,
        }

    def _parse_multichoice(self, question_elem):
        """Parse multiple choice answers"""
        answers = []
        correct = []
        
        for answer_elem in question_elem.findall('answer'):
            fraction = float(answer_elem.get('fraction', 0))
            text_elem = answer_elem.find('text')
            if text_elem is not None:
                answer_text = self._clean_html(text_elem.text or '')
                answers.append({
                    'text': answer_text,
                    'fraction': fraction,
                    'is_correct': fraction > 0
                })
                if fraction > 0:
                    correct.append(answer_text)
        
        return answers, ', '.join(correct)

    def _parse_truefalse(self, question_elem):
        """Parse true/false answers"""
        answers = []
        correct = ''
        
        for answer_elem in question_elem.findall('answer'):
            fraction = float(answer_elem.get('fraction', 0))
            text_elem = answer_elem.find('text')
            if text_elem is not None:
                answer_text = text_elem.text or ''
                answers.append({
                    'text': answer_text,
                    'fraction': fraction,
                    'is_correct': fraction > 0
                })
                if fraction > 0:
                    correct = answer_text
        
        return answers, correct

    def _parse_shortanswer(self, question_elem):
        """Parse short answer questions"""
        answers = []
        correct = []
        
        for answer_elem in question_elem.findall('answer'):
            fraction = float(answer_elem.get('fraction', 0))
            text_elem = answer_elem.find('text')
            if text_elem is not None:
                answer_text = text_elem.text or ''
                answers.append({
                    'text': answer_text,
                    'fraction': fraction,
                    'is_correct': fraction > 0
                })
                if fraction > 0:
                    correct.append(answer_text)
        
        return answers, ', '.join(correct)

    def _map_question_type(self, moodle_type):
        """Map Moodle question type to our question type"""
        mapping = {
            'multichoice': 'mcq',
            'truefalse': 'true_false',
            'shortanswer': 'fill_blank',
            'numerical': 'fill_blank',
            'essay': 'essay',
        }
        return mapping.get(moodle_type, 'mcq')

    def _clean_html(self, text):
        """Clean HTML and preserve formatting"""
        if not text:
            return ''
        # Decode HTML entities
        text = html.unescape(text)
        return text.strip()

    def _detect_latex(self, text):
        """Detect if text contains LaTeX"""
        if not text:
            return False
        # Common LaTeX patterns
        latex_patterns = [
            r'\$\$.*?\$\$',  # Display math
            r'\$.*?\$',      # Inline math
            r'\\begin\{.*?\}',
            r'\\end\{.*?\}',
            r'\\frac\{',
            r'\\sqrt\{',
            r'\\text\{',
        ]
        for pattern in latex_patterns:
            if re.search(pattern, text):
                return True
        return False

    def _extract_images(self, text_elem):
        """Extract embedded images from question text"""
        images = []
        
        # Look for file elements (Moodle embeds images as file elements)
        if text_elem is not None:
            for file_elem in text_elem.findall('.//file'):
                filename = file_elem.get('name', '')
                encoding = file_elem.get('encoding', 'base64')
                
                if file_elem.text and encoding == 'base64':
                    images.append({
                        'filename': filename,
                        'data': file_elem.text,
                        'encoding': encoding
                    })
        
        return images

    def _format_answers_preview(self, answers_data):
        """Format answers for preview display"""
        if not answers_data:
            return ''
        
        preview = []
        for ans in answers_data[:5]:  # Show first 5 answers
            marker = '✓' if ans.get('is_correct') else '○'
            preview.append(f"{marker} {ans.get('text', '')[:50]}")
        
        if len(answers_data) > 5:
            preview.append(f"... and {len(answers_data) - 5} more")
        
        return '\n'.join(preview)

    def action_import_questions(self):
        """Import selected questions into the question bank"""
        self.ensure_one()
        
        selected_lines = self.preview_line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_('Please select at least one question to import.'))
        
        QbQuestion = self.env['qb.question']
        QbTopic = self.env['qb.topic']
        IrAttachment = self.env['ir.attachment']
        
        imported_count = 0
        skipped_count = 0
        category_topics = {}  # Cache for created topics
        
        for line in selected_lines:
            try:
                # Check for duplicates
                if self.skip_duplicates:
                    existing = QbQuestion.search([
                        ('question_html', '=', line.question_text),
                        ('subject_id', '=', self.subject_id.id)
                    ], limit=1)
                    if existing:
                        skipped_count += 1
                        continue
                
                # Determine topic
                topic_id = self.topic_id.id
                if self.create_categories_as_topics and line.category:
                    # Create or get topic from category
                    if line.category not in category_topics:
                        topic = QbTopic.search([
                            ('name', '=', line.category),
                            ('subject_id', '=', self.subject_id.id)
                        ], limit=1)
                        if not topic:
                            topic = QbTopic.create({
                                'name': line.category,
                                'subject_id': self.subject_id.id,
                            })
                        category_topics[line.category] = topic.id
                    topic_id = category_topics[line.category]
                
                # Prepare question data
                question_vals = {
                    'name': line.name[:200],  # Question title
                    'question_html': line.question_text,
                    'question_type': line.question_type,
                    'subject_id': self.subject_id.id,
                    'topic_id': topic_id,
                    'explanation': line.feedback or '',
                    'difficulty': 'medium',
                    'state': 'draft',
                }
                
                # Handle different question types
                if line.moodle_type == 'multichoice':
                    # Create question first
                    question = QbQuestion.create(question_vals)
                    
                    # Parse and create options from stored JSON data
                    try:
                        answers = json.loads(line.answers_json or '[]')
                    except Exception:
                        answers = []
                    
                    QbQuestionOption = self.env['qb.question.option']
                    for idx, ans in enumerate(answers):  # Moodle exports can contain any option count
                        QbQuestionOption.create({
                            'question_id': question.id,
                            'option_text': ans.get('text', ''),
                            'is_correct': ans.get('is_correct', False),
                            'sequence': idx + 1,
                        })
                        
                elif line.moodle_type == 'truefalse':
                    question_vals['true_false_answer'] = 'true' if 'true' in line.correct_answer.lower() else 'false'
                    question = QbQuestion.create(question_vals)
                    
                elif line.moodle_type in ['shortanswer', 'numerical']:
                    question_vals['blank_answer'] = line.correct_answer
                    question = QbQuestion.create(question_vals)
                else:
                    # Default: create as MCQ
                    question = QbQuestion.create(question_vals)
                
                # Handle images
                if line.has_images and line.images_data:
                    try:
                        images = eval(line.images_data)  # Safe in this context
                        for img in images:
                            IrAttachment.create({
                                'name': img['filename'],
                                'datas': img['data'],
                                'res_model': 'qb.question',
                                'res_id': question.id,
                                'type': 'binary',
                            })
                    except:
                        pass  # Skip image errors
                
                imported_count += 1
                
            except Exception as e:
                # Log error but continue with other questions
                continue
        
        self.state = 'done'
        
        message = _('Successfully imported %d question(s).') % imported_count
        if skipped_count > 0:
            message += _(' Skipped %d duplicate(s).') % skipped_count
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Import Complete'),
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def _reconstruct_answers(self, line):
        """Reconstruct answer list from preview text"""
        if not line.answers_preview:
            return []
        
        answers = []
        for line_text in line.answers_preview.split('\n'):
            if line_text.startswith('✓') or line_text.startswith('○'):
                answer_text = line_text[2:].strip()
                if answer_text and not answer_text.startswith('...'):
                    answers.append(answer_text)
        
        return answers

    def _parse_stored_answers(self, line):
        """Parse answers from stored preview data with correct/incorrect info"""
        if not line.answers_preview:
            return []
        
        answers = []
        for line_text in line.answers_preview.split('\n'):
            if line_text.startswith('✓'):
                answer_text = line_text[2:].strip()
                if answer_text and not answer_text.startswith('...'):
                    answers.append({'text': answer_text, 'is_correct': True})
            elif line_text.startswith('○'):
                answer_text = line_text[2:].strip()
                if answer_text and not answer_text.startswith('...'):
                    answers.append({'text': answer_text, 'is_correct': False})
        
        return answers

    def action_back_to_upload(self):
        """Go back to upload step"""
        self.state = 'upload'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'qb.moodle.import',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class QbMoodleImportLine(models.TransientModel):
    _name = 'qb.moodle.import.line'
    _description = 'Moodle Import Preview Line'
    _order = 'id'

    import_id = fields.Many2one('qb.moodle.import', string='Import Batch', required=True, ondelete='cascade')
    selected = fields.Boolean(string='Selected', default=True)
    
    name = fields.Char(string='Question Name')
    question_text = fields.Text(string='Question Text')
    question_type = fields.Selection([
        ('mcq', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('fill_blank', 'Fill in the Blank'),
        ('essay', 'Essay'),
    ], string='Type')
    moodle_type = fields.Char(string='Moodle Type')
    
    category = fields.Char(string='Category')
    has_latex = fields.Boolean(string='Has LaTeX')
    has_images = fields.Boolean(string='Has Images')
    images_data = fields.Text(string='Images Data')
    
    answers_preview = fields.Text(string='Answers Preview')
    answers_json = fields.Text(string='Answers JSON Data')  # Store full answer data
    correct_answer = fields.Char(string='Correct Answer')
    feedback = fields.Text(string='Feedback')

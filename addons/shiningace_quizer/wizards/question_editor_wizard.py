from odoo import models, fields, api, _


class ShiningAceQuestionEditorWizard(models.TransientModel):
    """
    Wizard for advanced question editing with dual HTML/LaTeX editors.
    Provides a streamlined interface for creating questions with rich content.
    """
    _name = 'shiningace.question.editor.wizard'
    _description = 'ShiningAce Question Editor Wizard'

    question_id = fields.Many2one('shiningace.question', string='Question')

    # Tab mode
    editor_mode = fields.Selection([
        ('html', 'HTML Editor'),
        ('latex', 'LaTeX Editor'),
        ('preview', 'Preview'),
    ], string='Editor Mode', default='html')

    # HTML content
    question_text_html = fields.Html(
        string='Question (HTML)',
        help='Use $$...$$ for LaTeX equations within HTML'
    )
    answer_html = fields.Html(
        string='Answer (HTML)',
        help='Answer content with HTML formatting'
    )
    feedback_html = fields.Html(
        string='Feedback (HTML)',
        help='Feedback content with HTML formatting'
    )

    # LaTeX content
    question_text_latex = fields.Text(
        string='Question (LaTeX)',
        help='Full LaTeX document for the question'
    )
    answer_latex = fields.Text(
        string='Answer (LaTeX)',
        help='LaTeX source for the answer'
    )
    feedback_latex = fields.Text(
        string='Feedback (LaTeX)',
        help='LaTeX source for feedback'
    )

    # Preview
    preview_html = fields.Html(
        string='Preview',
        readonly=True,
        help='Rendered preview of the question'
    )

    def action_switch_to_latex(self):
        """Switch to LaTeX editor mode."""
        self.editor_mode = 'latex'
        return self._reopen()

    def action_switch_to_html(self):
        """Switch to HTML editor mode."""
        self.editor_mode = 'html'
        return self._reopen()

    def action_preview(self):
        """Generate preview from current content."""
        if self.editor_mode == 'html':
            self.preview_html = self.question_text_html
        elif self.editor_mode == 'latex':
            # In a real scenario, this would render LaTeX to HTML
            # For now, we display the raw LaTeX in a styled container
            self.preview_html = '''
                <div class="latex-preview" style="
                    background: #f8f9fa;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                    padding: 20px;
                    font-family: 'Courier New', monospace;
                    white-space: pre-wrap;
                ">{}</div>
                <div class="alert alert-info" style="margin-top: 10px;">
                    <i class="fa fa-info-circle"></i>
                    LaTeX preview requires a LaTeX renderer (MathJax/KaTeX) configured on the server.
                </div>
            '''.format(self.question_text_latex or '')
        self.editor_mode = 'preview'
        return self._reopen()

    def action_save(self):
        """Save the edited content back to the question."""
        if not self.question_id:
            return

        vals = {}
        if self.editor_mode == 'html':
            vals['question_text'] = self.question_text_html
        elif self.editor_mode == 'latex':
            vals['question_latex'] = self.question_text_latex

        if vals:
            self.question_id.write(vals)

        return {'type': 'ir.actions.act_window_close'}

    def _reopen(self):
        """Reopen the wizard in the current mode."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'shiningace.question.editor.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

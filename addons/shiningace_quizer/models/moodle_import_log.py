from odoo import models, fields, api


class ShiningAceMoodleImportLog(models.Model):
    """
    Logs Moodle XML import operations for auditing and troubleshooting.
    """
    _name = 'shiningace.moodle.import.log'
    _description = 'ShiningAce Moodle Import Log'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Import Name', required=True)
    import_date = fields.Datetime(string='Import Date', default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='Imported By', default=lambda self: self.env.user)
    file_name = fields.Char(string='File Name')
    file_data = fields.Binary(string='File Data', attachment=True)

    # Statistics
    total_questions = fields.Integer(string='Total Questions Found')
    imported_count = fields.Integer(string='Successfully Imported')
    skipped_count = fields.Integer(string='Skipped')
    error_count = fields.Integer(string='Errors')

    state = fields.Selection([
        ('completed', 'Completed'),
        ('partial', 'Partial Success'),
        ('failed', 'Failed'),
    ], string='Status', default='completed')

    import_details = fields.One2many(
        'shiningace.moodle.import.log.line',
        'import_log_id',
        string='Import Details'
    )

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)


class ShiningAceMoodleImportLogLine(models.Model):
    """
    Individual import line tracking each question's import result.
    """
    _name = 'shiningace.moodle.import.log.line'
    _description = 'ShiningAce Moodle Import Log Line'
    _order = 'id'

    import_log_id = fields.Many2one(
        'shiningace.moodle.import.log',
        string='Import Log',
        required=True,
        ondelete='cascade'
    )
    moodle_question_id = fields.Char(string='Moodle Question ID')
    moodle_question_name = fields.Char(string='Moodle Question Name')
    moodle_question_type = fields.Char(string='Moodle Question Type')
    status = fields.Selection([
        ('imported', 'Imported'),
        ('skipped', 'Skipped'),
        ('error', 'Error'),
    ], string='Status', default='imported')
    message = fields.Text(string='Message')
    created_question_id = fields.Many2one(
        'shiningace.question',
        string='Created Question',
        ondelete='set null'
    )

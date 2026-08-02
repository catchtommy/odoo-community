# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

_MAX_DEPTH = 50


class EducationPrerequisite(models.Model):
    """Explicit relation between two topics (rather than a bare Many2many)
    so prerequisite strength/notes can be recorded, and so cycles can be
    detected before they corrupt "what should a student learn first" logic.
    """
    _name = 'education.prerequisite'
    _description = 'Curriculum Prerequisite'
    _order = 'topic_id, id'

    topic_id = fields.Many2one('education.topic', required=True, index=True, ondelete='cascade')
    prerequisite_topic_id = fields.Many2one(
        'education.topic', string='Prerequisite Topic', required=True, index=True, ondelete='cascade',
    )
    is_mandatory = fields.Boolean(default=True)
    notes = fields.Text()

    _no_self_prerequisite = models.Constraint(
        'CHECK(topic_id != prerequisite_topic_id)', 'A topic cannot be a prerequisite of itself.',
    )
    _unique_pair = models.Constraint(
        'UNIQUE(topic_id, prerequisite_topic_id)', 'This prerequisite relationship already exists.',
    )

    @api.constrains('topic_id', 'prerequisite_topic_id')
    def _check_no_cycle(self):
        for rec in self:
            visited = {rec.topic_id.id}
            frontier = [rec.prerequisite_topic_id]
            depth = 0
            while frontier and depth < _MAX_DEPTH:
                depth += 1
                next_frontier = []
                for topic in frontier:
                    if topic.id in visited:
                        raise ValidationError(
                            "Adding this prerequisite would create a cycle: "
                            f"'{rec.topic_id.name}' would indirectly depend on itself."
                        )
                    visited.add(topic.id)
                    next_frontier.extend(topic.prerequisite_ids.mapped('prerequisite_topic_id'))
                frontier = next_frontier

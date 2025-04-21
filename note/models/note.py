# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools import html2plaintext
from odoo.addons.web_editor.tools import handle_history_divergence

class Stage(models.Model):
    _name = "note.stage"
    _description = "Note Stage"
    _order = 'sequence'

    name = fields.Char('Stage Name', translate=True, required=True)
    sequence = fields.Integer(default=1)
    fold = fields.Boolean('Folded by Default')


class Tag(models.Model):

    _name = "note.tag"
    _description = "Note Tag"

    name = fields.Char('Tag Name', required=True, translate=True)
    color = fields.Integer('Color Index')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Tag name already exists !"),
    ]


class Note(models.Model):

    _name = 'note.note'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Note"
    _order = 'sequence, id desc'

    def _get_default_stage_id(self):
        return self.env['note.stage'].search([], limit=1)

    name = fields.Text(
        compute='_compute_name', string='Note Summary', store=True, readonly=False)
    company_id = fields.Many2one('res.company')
    user_id = fields.Many2one('res.users', string='Owner', default=lambda self: self.env.uid)
    memo = fields.Html('Note Content')
    sequence = fields.Integer('Sequence', default=0)
    stage_id = fields.Many2one(
        comodel_name='note.stage',
        string='Stage', default=_get_default_stage_id, store=True, readonly=False)
    open = fields.Boolean(string='Active', default=True)
    date_done = fields.Date('Date done')
    color = fields.Integer(string='Color Index')
    tag_ids = fields.Many2many('note.tag', 'note_tags_rel', 'note_id', 'tag_id', string='Tags')
    # modifying property of ``mail.thread`` field
    message_partner_ids = fields.Many2many(compute_sudo=True)

    @api.depends('memo')
    def _compute_name(self):
        """ Read the first line of the memo to determine the note name """
        for note in self:
            if note.name:
                continue
            text = html2plaintext(note.memo) if note.memo else ''
            note.name = text.strip().replace('*', '').split("\n")[0]

    def _compute_stage_id(self):
        first = self.env['note.stage'].search([], limit=1)
        for note in self:
            if not note.stage_id:
                note.stage_id = note.stage_ids.sudo()[:1] or first

    def action_close(self):
        return self.write({'open': False, 'date_done': fields.date.today()})

    def action_open(self):
        return self.write({'open': True})

    def write(self, vals):
        if len(self) == 1:
            handle_history_divergence(self, 'memo', vals)
        return super(Note, self).write(vals)

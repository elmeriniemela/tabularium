# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class DocumentDirectory(models.Model):
    _name = 'document.directory'
    _description = 'Document Directory'
    _inherit = ['mail.thread.main.attachment']

    name = fields.Char(required=True)
    attachment_ids = fields.One2many('ir.attachment', 'res_id', domain=[('res_model', '=', 'document.directory')], string='Attachments')
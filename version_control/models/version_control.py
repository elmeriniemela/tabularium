# -*- coding: utf-8 -*-

import logging
import difflib
import hashlib
try:
    from markdownify import markdownify as md
except Exception:
    md = lambda x: x

from odoo import models, tools, fields, api, _

_logger = logging.getLogger(__name__)


class VersionControl(models.Model):
    _name = 'version.control'
    _description = 'Version Control'
    _order = 'id desc'
    _auto = False

    create_date = fields.Datetime(string='Created on')
    create_uid = fields.Many2one(comodel_name='res.users', string='Created by')

    model = fields.Char('Related Document Model')
    res_id = fields.Many2oneReference('Related Document ID', model_field='model')
    field_id = fields.Many2one('ir.model.fields')
    old_value_text = fields.Text('Old Value Text', readonly=True)
    new_value_text = fields.Text('New Value Text', readonly=True)

    diff = fields.Text(compute='_compute_diff')


    version_hash_before = fields.Char(compute='_compute_hash')
    version_hash_after = fields.Char(compute='_compute_hash')
    name = fields.Char(compute='_compute_hash')
    reference = fields.Char(string='Reference', compute='_compute_reference', readonly=True, store=False)

    @api.depends('model', 'res_id')
    def _compute_reference(self):
        for res in self:
            res.reference = "%s,%s" % (res.model, res.res_id)

    def _select(self):
        return f"""
            mtv.id as id,
            mtv.create_date as create_date,
            mtv.create_uid as create_uid,
            mm.model as model,
            mm.res_id as res_id,
            mtv.field_id as field_id,
            mtv.old_value_text as old_value_text,
            mtv.new_value_text as new_value_text
        """

    def _from(self):
        return f"""
            mail_tracking_value mtv
            LEFT JOIN ir_model_fields imf ON imf.id=mtv.field_id
            LEFT JOIN mail_message mm ON mm.id=mail_message_id
        """

    def _where(self):
        return f"""
            imf.version_control=True
        """


    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE or REPLACE VIEW %s as (
            SELECT %s
            FROM %s
            WHERE %s
            )""" % (self._table, self._select(), self._from(), self._where()))


    def _compute_diff(self):
        for rec in self:
            src = rec.old_value_text or ''
            dst = rec.new_value_text or ''
            if rec.field_id.ttype == 'html':
                src = md(src)
                dst = md(dst)
            lines = difflib.unified_diff(
                src.splitlines(True),
                dst.splitlines(True),
                fromfile=rec.field_id.name,
                tofile=rec.field_id.name,
            )
            rec.diff = ''.join(lines)


    def _compute_hash(self):
        for rec in self:
            rec.version_hash_before = hashlib.sha1((rec.old_value_text or '').encode('utf-8')).hexdigest()
            rec.version_hash_after = hashlib.sha1((rec.new_value_text or '').encode('utf-8')).hexdigest()
            rec.name = f'{rec.version_hash_before}...{rec.version_hash_after}'

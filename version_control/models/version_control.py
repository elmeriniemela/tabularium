# -*- coding: utf-8 -*-

import logging
from odoo import models, tools, fields, api, _

_logger = logging.getLogger(__name__)


class VersionControl(models.Model):
    _name = 'version.control'
    _description = 'Version Control'
    _order = 'id desc'
    _auto = False

    def _select(self):
        return f"""
            mtv.id
        """

    def _from(self):
        return f"""
            mail_tracking_value mtv
        """

    def _where(self):
        return f"""
            mtv.id is not null
        """


    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE or REPLACE VIEW %s as (
            SELECT %s
            FROM %s
            WHERE %s
            )""" % (self._table, self._select(), self._from(), self._where()))
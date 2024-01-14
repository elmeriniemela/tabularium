# -*- coding: utf-8 -*-

import logging

from odoo import models, _
from odoo.tools.convert import convert_xml_import, xml_import
_logger = logging.getLogger(__name__)

class Base(models.AbstractModel):
    _inherit = 'base'

    def xml_import(self, root, noupdate=True, mode='init', module='__export__'):
        obj = xml_import(self.env.cr, module=module, idref=None, mode=mode, noupdate=noupdate, xml_filename=None)
        obj.parse(root)

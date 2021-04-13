# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TogglExport(models.TransientModel):
    _name = 'toggl.export'
    _description = 'Toggl Export'
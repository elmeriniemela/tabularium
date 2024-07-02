# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, _

_logger = logging.getLogger(__name__)


class DnsZone(models.Model):
    _name = 'dns.zone'
    _description = 'DNS Zone'
    _inherit = ['mail.thread']

    name = fields.Char(
        required=True,
        tracking=True,
    )

    identifier = fields.Char(
        required=True,
        tracking=True,
    )

    record_ids = fields.One2many(
        comodel_name='dns.zone.record',
        inverse_name='zone_id',
    )

    ns_endpoint_id = fields.Many2one(
        string="Nameservers",
        comodel_name='api.endpoint',
        domain=[
            ('usage_field_id.name', '=', 'ns_endpoint_id'),
            ('usage_field_id.model_id.model', '=', 'dns.zone'),
        ],
        compute='_compute_ns_endpoint_id',
    )

    _sql_constraints = [
        ('uniq_name', 'UNIQUE(name)', 'The zone name must be unique!'),
        ('uniq_identifier', 'UNIQUE(identifier)', 'The zone identifier must be unique!'),
    ]

    def _compute_ns_endpoint_id(self):
        ns_endpoint = self.env['api.endpoint'].search([
            ('usage_field_id.name', '=', 'ns_endpoint_id'),
            ('usage_field_id.model_id.model', '=', 'dns.zone'),
        ], limit=1)
        for zone in self:
            zone.ns_endpoint_id = ns_endpoint

    @api.model
    def upsert(self, vals):
        rec = self.search([('identifier', '=', vals['identifier'])])
        if not rec:
            rec = self.create(vals)
        else:
            rec.write(vals)
        return rec


    def fetch(self):
        ZoneRecord = self.env['dns.zone.record'].with_context(fetching=True)
        for zone in self.with_context(fetching=True):
            globals_dict = zone.ns_endpoint_id.produce({'kwargs': {
                'url': f'/zones/{zone.identifier}/dns_records',
                'method': 'GET',
            }})
            res_list = globals_dict['obj']['result']
            existing = ZoneRecord.browse()
            for i, res in enumerate(res_list, start=1):
                _logger.info(res)
                existing += ZoneRecord.upsert({
                    'name': res['name'],
                    'identifier': res['id'],
                    'ttl': res['ttl'],
                    'rtype': res['type'],
                    'content': res['content'],
                    'proxied': res['proxied'],
                    'zone_id': zone.id,
                    'sequence': i,
                })
            (zone.record_ids - existing).unlink()


# -*- coding: utf-8 -*-

import logging
import secrets
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
            for res in res_list:
                _logger.info(res)
                existing += ZoneRecord.upsert({
                    'name': res['name'],
                    'identifier': res['id'],
                    'ttl': res['ttl'],
                    'rtype': res['type'],
                    'content': res['content'],
                    'proxied': res['proxied'],
                    'zone_id': zone.id,
                })
            (zone.record_ids - existing).unlink()



class DnsZoneRecord(models.Model):
    _name = 'dns.zone.record'
    _description = 'DNS Zone Record'
    _inherit = ['mail.thread']

    name = fields.Char(
        required=True,
        tracking=True,
    )

    instance_id = fields.Many2one(
        comodel_name='cloud.instance',
        tracking=True,
        ondelete='set null',
    )

    content = fields.Char(
        required=True,
        tracking=True,
    )

    identifier = fields.Char(
        tracking=True,
    )

    proxied = fields.Boolean(
        tracking=True,
    )

    ttl = fields.Integer(
        string="TTL",
        required=True,
        tracking=True,
    )

    rtype = fields.Char(
        string="Type",
        required=True,
        tracking=True,
    )

    zone_id = fields.Many2one(
        comodel_name='dns.zone',
        ondelete='restrict',
        required=True,
        tracking=True,
    )

    _sql_constraints = [
        ('uniq_identifier', 'UNIQUE(identifier)', 'The zone record identifier must be unique!'),
    ]

    @api.model
    def upsert(self, vals):
        rec = self.search([('identifier', '=', vals['identifier'])])
        if not rec:
            rec = self.create(vals)
        else:
            rec.write(vals)
        return rec


    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('fetching') and any(f in vals for f in ['content', 'name', 'proxied', 'type', 'ttl']):
            self.cloudflare_update()
        return res

    def cloudflare_update(self):
        for rec in self:
            globals_dict = rec.zone_id.ns_endpoint_id.produce({'kwargs': {
                'url': f'/zones/{rec.zone_id.identifier}/dns_records/{rec.identifier}',
                'method': 'PUT',
                'json': {
                    "content": rec.content,
                    "name": rec.name,
                    "proxied": rec.proxied,
                    "type": rec.rtype,
                    # "comment": "Domain verification record",
                    "id": rec.identifier,
                    # "tags": [
                    #     "owner:dns-team"
                    # ],
                    "ttl": rec.ttl,
                }
            }})
            assert globals_dict['obj']['success'], f"Fail: {globals_dict['obj']}"



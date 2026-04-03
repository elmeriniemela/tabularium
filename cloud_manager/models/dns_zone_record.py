# -*- coding: utf-8 -*-

import logging
import secrets
from odoo import models, api, fields, _

_logger = logging.getLogger(__name__)

class DnsZoneRecord(models.Model):
    _name = 'dns.zone.record'
    _description = 'DNS Zone Record'
    _inherit = ['mail.thread']
    _order = "sequence, id"

    sequence = fields.Integer(
        tracking=True,
        copy=False,
    )

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

    readonly = fields.Boolean(
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

    _uniq_identifier = models.Constraint('UNIQUE(identifier)', 'The zone record identifier must be unique!')

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

    @api.model_create_multi
    def create(self, vals_list):
        Zone = self.env['dns.zone']
        for vals in vals_list:
            if not vals.get('zone_id'):
                zone = '.'.join(vals.get('name', '').split('.')[-2:])
                vals['zone_id'] = Zone.search([('name', '=', zone)], limit=1).id

        records = super().create(vals_list)

        if not self.env.context.get('fetching'):
            records.cloudflare_create()
        return records

    def unlink(self):
        if not self.env.context.get('fetching'):
            self.cloudflare_delete()
        return super().unlink()

    def cloudflare_update(self):
        for rec in self:
            if rec.readonly: continue
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
            assert globals_dict['obj'].get('success'), f"Fail: {globals_dict['obj']}"


    def cloudflare_create(self):
        for rec in self:
            if rec.readonly: continue
            globals_dict = rec.zone_id.ns_endpoint_id.produce({'kwargs': {
                'url': f'/zones/{rec.zone_id.identifier}/dns_records',
                'method': 'POST',
                'json': {
                    "content": rec.content,
                    "name": rec.name,
                    "proxied": rec.proxied,
                    "type": rec.rtype,
                    "ttl": rec.ttl,
                }
            }})
            assert globals_dict['obj'].get('success'), f"Fail: {globals_dict['obj']}"
            rec.identifier = globals_dict['obj']['result']['id']

    def cloudflare_delete(self):
        for rec in self:
            if rec.readonly: continue
            globals_dict = rec.zone_id.ns_endpoint_id.produce({'kwargs': {
                'url': f'/zones/{rec.zone_id.identifier}/dns_records/{rec.identifier}',
                'method': 'DELETE',
            }})
            assert globals_dict['obj'].get('result', {}).get('id') == rec.identifier, f"Fail: {globals_dict['obj']}"
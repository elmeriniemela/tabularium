# -*- coding: utf-8 -*-

import logging
import secrets
import base64
import json
import xmlrpc.client
import ssl
import functools
from lxml import etree
import html
from odoo import models, exceptions, fields, api, _
import datetime as realdt
from odoo.tools.safe_eval import (
    wrap_module,
    datetime,
    dateutil,
    CodeType,
    check_values,
    compile_codeobj,
    assert_valid_codeobj,
    _BUILTINS,
    _SAFE_OPCODES,
    unsafe_eval,
    _BUBBLEUP_EXCEPTIONS,
)
from odoo.tools.convert import xml_import as XMLImport
from odoo.tools import config
from odoo.http import request

requests = wrap_module(__import__('requests'), {'get': None, 'post': None, 'put': None, 'delete': None, 'request': None, 'exceptions': ['ReadTimeout', 'Timeout', 'ConnectionError']})
io = wrap_module(__import__('io'), ['StringIO', 'BytesIO'])
pandas = wrap_module(__import__('pandas'), ['read_csv', 'read_excel', 'DataFrame'])
re = wrap_module(__import__('re'), ['findall', 'sub'])
json = wrap_module(__import__('json'), ['loads','dumps'])
xmltodict = wrap_module(__import__('xmltodict'), ['parse'])
dicttoxml = wrap_module(__import__('dicttoxml'), ['dicttoxml'])
yfinance = wrap_module(__import__('yfinance'), ['Ticker', 'Tickers', 'download'])

zipfile = wrap_module(__import__('zipfile'), ['ZipFile','ZIP_DEFLATED','BadZipfile'])
hashlib = wrap_module(__import__('hashlib'), ['sha256','sha512'])
hmac = wrap_module(__import__('hmac'), ['new',])
base64 = wrap_module(__import__('base64'), ['b64decode', 'b64encode'])
time = wrap_module(__import__('time'), ['time',])

import lxml
lxml_mods = ['etree']
for mod in lxml_mods:
    __import__('lxml.%s' % mod)
lxml = wrap_module(__import__('lxml'), {mod: getattr(lxml, mod).__all__ for mod in lxml_mods})


import urllib
urllib_mods = ['parse']
for mod in urllib_mods:
    __import__('urllib.%s' % mod)
urllib = wrap_module(__import__('urllib'), {mod: getattr(urllib, mod).__all__ for mod in urllib_mods})



_logger = logging.getLogger(__name__)


def safe_eval(expr, /, context, *, mode="eval", filename=None):
    """Adapted from odoo.tools.safe_eval.safe_eval to use GlobalsDict instead of regular dict in the evaluation.
    """
    if type(expr) is CodeType: # pragma: no cover
        raise TypeError("safe_eval does not allow direct evaluation of code objects.")

    check_values(context)

    globals_dict = GlobalsDict(context or {}, __builtins__=dict(_BUILTINS))

    c = compile_codeobj(expr, filename=filename, mode=mode)
    assert_valid_codeobj(_SAFE_OPCODES, c, expr)
    try:
        # empty locals dict makes the eval behave like top-level code
        return unsafe_eval(c, globals_dict, None)

    except _BUBBLEUP_EXCEPTIONS:
        raise

    except Exception as e:
        raise ValueError('%r while evaluating\n%r' % (e, expr))

    finally:
        if context is not None:
            del globals_dict['__builtins__']
            context.update(globals_dict)


def json_encoder(o):
    if isinstance(o, (datetime.date, datetime.datetime)):
        return repr(o)
    raise TypeError(f'Object of type {o.__class__.__name__} is not JSON serializable')


def json_decoder(d):
    for key, value in d.items():
        if not isinstance(value, str):
            continue

        def dtargs(v):
            args = re.findall(r'\d+', value)
            return (int(a) for a in args)

        if value.startswith('datetime.datetime'):
            d[key] = datetime.datetime(*dtargs(value))
        elif value.startswith('datetime.date'):
            d[key] = datetime.date(*dtargs(value))
    return d


def import_xml(cr, root, noupdate=True, mode='init', module='__export__'):
    obj = XMLImport(cr, module=module, idref=None, mode=mode, noupdate=noupdate, xml_filename=None)
    obj.parse(root)


class GlobalsDict(dict):

    def __init__(self, mapping=None, /, **kwargs):
        super().__init__(mapping)
        self.__protected_keys = set(mapping.keys()) | {
            'msg',
        }

    def force_set(self, key, value):
        super().__setitem__(key, value)

    def __setitem__(self, key, value):
        if key in self.__protected_keys:
            raise exceptions.UserError(f"Cannot redefine a protected variable {key}={value}. Protected vars: {self.__protected_keys}")
        super().__setitem__(key, value)


class ApiEndpoint(models.Model):
    _name = 'api.endpoint'
    _description = 'API Endpoint'
    _inherit = ['mail.thread']
    _order = "sequence, id"

    def _get_globals(self):
        return GlobalsDict({
            'self': self.with_user(self.user_id).sudo(flag=False),
            'json': json,
            'xmltodict': xmltodict,
            'dicttoxml': dicttoxml,
            'zipfile': zipfile,
            'pandas': pandas,
            'requests': requests,
            'request': request,
            'datetime': datetime,
            'dateutil': dateutil,
            'urllib': urllib,
            'hashlib': hashlib,
            'hmac': hmac,
            'base64': base64,
            'time': time,
            'io': io,
            'yfinance': yfinance,
            're': re,
            'lxml': lxml,
            '_logger': _logger,
            'ValidationError': exceptions.ValidationError,
            'UserError': exceptions.UserError,
            'AccessError': exceptions.AccessError,
            'import_xml': functools.partial(import_xml, self.env.cr),
            'locals': locals,
        })


    sequence = fields.Integer(
        string="Endpoint Sequence",
        tracking=True,
        default=10000,
        copy=False,
    )

    name = fields.Char(
        required=True,
        tracking=True,
    )

    state = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('error', 'Error'),
            ('archived', 'Archived'),
        ],
        required=True,
        tracking=True,
        default='active',
    )

    active = fields.Boolean(compute='_compute_active', store=True)

    company_id = fields.Many2one(
        comodel_name='res.company',
        tracking=True,
        index=True,
    )

    usage_field_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Used in',
        ondelete='set null',
        tracking=True,
        domain=[('relation', '=', 'api.endpoint')],
        help="Use this field to limit selection of a spefic field to a specific subset of API endpoints."
    )

    usage_count = fields.Integer(compute='_compute_usage_count')

    direction = fields.Selection(
        selection=[
            ('outbound', 'Outbound'),
            ('inbound', 'Inbound'),
        ],
        required=True,
        tracking=True,
        default='outbound',
        help="Is the data flow inbound or outbound from the endpoint's perspective?"
    )

    role = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('passive', 'Passive'),
        ],
        required=True,
        tracking=True,
        default='active',
        help="Is the endpoint an active participant on the integration, or does it passivly respond to events calls from an external system?"
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
        ondelete='restrict',
        domain=[('active', 'in', [True, False])],
    )


    comm_method = fields.Selection(
        string="Communication",
        selection=[
            ('http', 'HTTP'),
            ('xmlrpc', 'XML-RPC'),
            ('jsonrpc', 'JSON-RPC'),
            ('sftp', 'SFTP'),
        ],
        required=True,
        tracking=True,
        default='http',
    )

    http_method = fields.Selection(
        string="HTTP-Method",
        selection=[
            ('get', 'GET'),
            ('post', 'POST'),
            ('delete', 'DELETE'),
            ('put', 'PUT'),
        ],
        tracking=True,
    )

    file_format = fields.Selection(
        selection=[
            ('json', 'JSON'),
            ('xml', 'XML'),
            ('csv', 'CSV'),
            ('zip', 'ZIP'),
            ('bytes', 'Bytes'),
        ],
        required=True,
        tracking=True,
        default='json',
    )

    response_format = fields.Selection(
        selection=[
            ('json', 'JSON'),
            ('xml', 'XML'),
            ('csv', 'CSV'),
            ('zip', 'ZIP'),
            ('redirect', 'HTTP Redirect'),
        ],
        tracking=True,
    )

    sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        required=True,
        tracking=True,
        copy=False,
        ondelete='restrict',
    )

    authorization = fields.Char(
        tracking=True,
        default=lambda self: secrets.token_urlsafe(),
    )

    location = fields.Char(
        required=True,
        tracking=True,
        default='',
    )

    url = fields.Char(compute='_compute_url')

    ttl = fields.Integer(
        string="TTL",
        default=7,
        tracking=True,
    )

    cron_id = fields.Many2one(
        comodel_name='ir.cron',
        tracking=True,
        ondelete='restrict',
        domain=[
            ('model_id.model', '=', 'api.endpoint'),
            ('code', '=', 'model.cron_run()'),
        ]
    )

    allow_backoff = fields.Boolean(tracking=True)
    backoff = fields.Integer(tracking=True)
    to_skip = fields.Integer(tracking=True)

    cron_interval_number = fields.Integer(related='cron_id.interval_number', readonly=True)
    cron_interval_type = fields.Selection(related='cron_id.interval_type', readonly=True)

    multi_record = fields.Boolean(
        default=False,
        tracking=True,
        help="The integration has multiple records per one file."
    )

    auto_consume = fields.Boolean(
        default=True,
        tracking=True,
    )

    auto_commit = fields.Boolean(
        default=True,
        tracking=True,
    )

    auto_code = fields.Boolean(
        default=True,
        tracking=True,
    )

    hardcoded_producer = fields.Text(
        compute='_compute_hardcoded'
    )

    hardcoded_consumer = fields.Text(
        compute='_compute_hardcoded'
    )

    xslt = fields.Text(
        string="XSLT",
        tracking=True,
        version_control=True,
        help="XSLT transformation.",
    )

    documentation = fields.Html()

    test_example = fields.Text(
        string="Test Example",
        help="Example code to test the integration.",
    )

    initiator = fields.Text(
        string="Initiator",
        tracking=True,
        version_control=True,
        help="Default initiator for the integration, used by the cron actions and the 'Execute' button. The 'variables' variable will be empty by default.",
        default='self.produce(variables={})',
    )

    producer = fields.Text(
        string="Producer (READ)",
        tracking=True,
        version_control=True,
        help="Produces a list of new message. The output will be passed to consumer.",
    )

    consumer = fields.Text(
        string="Consumer (CREATE, WRITE, DELETE)",
        tracking=True,
        version_control=True,
        help="consumees a list of messages generated by the producer. The result will be imported to Odoo or send to an external system.",
    )

    msg_ids = fields.One2many(
        comodel_name='api.message',
        inverse_name='endpoint_id',
        readonly=True
    )

    msg_count = fields.Integer(
        string="Files",
        compute='_compute_msg_count',
    )


    @api.depends('usage_field_id')
    def _compute_usage_count(self):
        for record in self:
            record.usage_count = len(record._get_usage_records())


    def _get_usage_records(self):
        self.ensure_one()
        if not self.usage_field_id:
            return self.browse()

        return self.env[self.usage_field_id.model_id.model].search([(self.usage_field_id.name, '=', self.id)])


    def action_view_usage(self):
        records = self._get_usage_records()
        return {
            'type': 'ir.actions.act_window',
            'name': records._description,
            'res_model': records._name,
            'view_mode': 'list',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', records.ids)],
        }

    @api.depends('state')
    def _compute_active(self):
        for record in self:
            record.active = record.state != 'archived'


    @api.autovacuum
    def _gc_messages(self):
        for endpoint in self.search([('ttl', '>', 0)]):
            limit_dt = fields.Datetime.subtract(fields.Datetime.now(), days=endpoint.ttl)
            to_unlink = self.env['api.message'].search([
                ('endpoint_id', '=', endpoint.id),
                ('create_date', '<=', limit_dt),
            ])
            to_unlink.unlink()
            if not config.options['test_enable']: # pragma: no cover
                to_unlink.env.cr.commit()


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('sequence_id'):
                name = vals['name']
                code = re.sub(r'[^a-z\d]+', '_', name.lower()).strip('_')
                vals['sequence_id'] = self.env['ir.sequence'].create({
                    'name': 'API: %s' % name,
                    'prefix': '%s_' % code,
                    'company_id': False,
                    'padding': 8,
                }).id
        return super().create(vals_list)


    @api.depends('msg_ids')
    def _compute_msg_count(self):
        for rec in self:
            rec.msg_count = len(rec.msg_ids)


    @api.depends('comm_method', 'role', 'direction', 'file_format')
    def _compute_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url').rstrip('/')
        for rec in self:
            url = False
            if rec.comm_method == 'http' and rec.role == 'passive' and rec.location:
                url = f'{base_url}/api-v1/{rec.location}'
                if rec.authorization:
                    url += f'?Authorization={rec.authorization}'
            rec.url = url


    @api.depends('comm_method', 'role', 'direction', 'file_format')
    def _compute_hardcoded(self):
        for rec in self:
            hardcoded_producer = ''
            hardcoded_consumer = ''
            if rec.auto_code:
                if rec.comm_method == 'http':
                    if rec.direction == 'inbound':
                        if rec.role == 'active':
                            hardcoded_producer += "resp = requests.request(self.http_method, self.location, headers={'Authorization': self.authorization}, timeout=10)\n"
                            hardcoded_producer += "data = resp.content\n"

                        if rec.file_format == 'json':
                            hardcoded_producer += "obj = json.loads(data)\n"
                        elif rec.file_format == 'xml':
                            hardcoded_producer += "obj = lxml.etree.fromstring(data)\n"
                            if (rec.xslt or '').strip():
                                hardcoded_consumer += 'xslt = lxml.etree.XSLT(lxml.etree.XML(self.xslt))\n'
                                hardcoded_consumer += 'obj = xslt(obj, test=lxml.etree.XSLT.strparam("test")).getroot()\n'
                            hardcoded_consumer += 'import_xml(obj)\n'
                        elif rec.file_format == 'csv':
                            hardcoded_producer += "obj = pandas.read_csv(io.BytesIO(data))\n"
                        elif rec.file_format == 'zip':
                            hardcoded_producer += "obj = zipfile.ZipFile(io.BytesIO(data))\n"
                    else:
                        hardcoded_producer += "records = self.env['res.partner'].search([('name', '=', ticker)])\n"
                        if rec.file_format == 'xml':
                            hardcoded_producer += "obj = records.xml_export(['name', 'vat'])\n"

                elif rec.comm_method == 'xmlrpc' and rec.direction == 'outbound' and rec.role == 'active':
                    hardcoded_producer += (
                        "url = 'https://%s@%s' % (self.authorization, self.location)\n"
                        "response = self.xmlrpc(url, method, args)\n"
                    )


            rec.hardcoded_producer = hardcoded_producer
            rec.hardcoded_consumer = hardcoded_consumer


    def action_execute(self):
        self.ensure_one()
        if self.to_skip > 0:
            self.to_skip -= 1
            _logger.info("Skipped action_execute due to error backoff")
            return
        commit = self.env.context.get('force_commit') or self.auto_commit
        raise_exc = self.env.context.get('raise_exc', True)
        assert raise_exc or commit, "If you want to bypass the error, you need to set force_commit=True."

        try:
            if not (self.initiator and self.role == 'active'):
                raise exceptions.UserError(_("Unable to initiate, check integration parameters."))
            globals_dict = self._get_globals()
            safe_eval(self.initiator, globals_dict, mode="exec")
        except Exception as error:
            if not config.options['test_enable']: # pragma: no cover
                self.env.cr.rollback()
            if commit and self.state == 'active': # if still active, it means that error was not handled by .produce() call, we need our own handling here.
                self._mark_error()
                self.message_post(body=(str(error)), subtype_xmlid='api_endpoint.mt_integration_error', message_type='comment')
                if not config.options['test_enable']: # pragma: no cover
                    self.env.cr.commit()
            if raise_exc or not commit: # Commit required, silent bypass is not allowed
                raise error

    def action_test(self):
        globals_dict = self._get_globals()
        safe_eval(self.test_example or '', globals_dict, mode="exec")


    def produce(self, variables):
        self.ensure_one()
        globals_dict = self._get_globals()
        if self.to_skip > 0:
            self.to_skip -= 1
            _logger.info("Skipped produce due to error backoff")
            return globals_dict
        self = self.sudo() # All the internals of this function should be run as root, but the _get_globals will demote the user.
        commit = self.env.context.get('force_commit') or self.auto_commit
        raise_exc = self.env.context.get('raise_exc', True)
        assert raise_exc or commit, "If you want to bypass the error, you need to set force_commit=True."
        try:
            if self.state not in ['active', 'error']:
                raise exceptions.UserError(_("Unable to produce, invalid state: %s.") % self.state)
            serialized_vars = self._serialize_dict(globals_dict, variables)
            serialized_ctx = self._serialize_dict(globals_dict, self.env.context)
            globals_dict.update(variables)
            copied_globals_dict = globals_dict.copy() # To prevent sharing new vars between Producer and Consumer. These vars are not stored in message queue.
            safe_eval((self.hardcoded_producer or '') + (self.producer or ''), copied_globals_dict, mode="exec")
            if 'obj' in copied_globals_dict:
                globals_dict['obj'] = copied_globals_dict['obj']
            else:
                raise RuntimeError("No obj to store! The producer code should assign a variable called 'obj'!")
            self._store(globals_dict, serialized_vars, serialized_ctx)
        except Exception as error:
            if not config.options['test_enable']: # pragma: no cover
                self.env.cr.rollback()
            if commit:
                self._mark_error()
                self.message_post(body=(str(error)), subtype_xmlid='api_endpoint.mt_integration_error', message_type='comment')
                if not config.options['test_enable']: # pragma: no cover
                    self.env.cr.commit()
            if raise_exc or not commit: # Commit required, silent bypass is not allowed
                error._producer_handled = True
                raise error
        else:
            self._mark_active()

        if commit and not config.options['test_enable']: # pragma: no cover:
            self.env.cr.commit()
        if self.auto_consume:
            self._consume(globals_dict)
        return globals_dict


    def _mark_error(self):
        if self.state == 'active':
            self.state = 'error'

        if self.allow_backoff:
            if not self.backoff:
                self.backoff = 1
            else:
                self.backoff *= 2
            self.to_skip = self.backoff


    def _mark_active(self):
        if self.state == 'error':
            self.state = 'active'
            self.to_skip = 0
            self.backoff = 0


    def _serialize_dict(self, globals_dict, original_dict):
        d = original_dict.copy()
        class EvalModel:
            def __init__(self, recs):
                self.recs = recs

            def __repr__(self) -> str:
                return f"self.env['{self.recs._name}'].browse({self.recs.ids})"

        for key, val in d.items():
            if isinstance(val, models.AbstractModel):
                d[key] = EvalModel(val)

        serialized_dict = str(d)
        assert isinstance(safe_eval(serialized_dict, globals_dict), dict), "Ensure that the dict can be evaluated from message queue."
        return serialized_dict


    def _store(self, globals_dict, variables, context):
        self.ensure_one()
        obj = globals_dict['obj']
        bytesdata = self.obj_to_bytes(obj, self.file_format)
        globals_dict.force_set('msg', self.sudo().env['api.message'].create({
            'endpoint_id': self.id,
            'content': base64.b64encode(bytesdata),
            'variables': variables,
            'context': context,
        }))


    def _consume(self, globals_dict):
        commit = self.env.context.get('force_commit') or self.auto_commit
        raise_exc = self.env.context.get('raise_exc', True)
        assert raise_exc or commit, "If you want to bypass the error, you need to set force_commit=True."
        try:
            safe_eval((self.hardcoded_consumer or '') + (self.consumer or ''), globals_dict, mode="exec")
        except Exception as error:
            if not config.options['test_enable']: # pragma: no cover
                self.env.cr.rollback()
            if commit:
                if globals_dict.get('msg'):
                    globals_dict['msg'].write({'state': 'error'})
                    globals_dict['msg'].message_post(body=(str(error)), subtype_xmlid='api_endpoint.mt_integration_error', message_type='comment')
                if not config.options['test_enable']: # pragma: no cover
                    self.env.cr.commit()
            if raise_exc or not commit: # Commit required, silent bypass is not allowed
                raise error
        else:
            if globals_dict.get('msg'):
                globals_dict['msg'].write({'state': 'consumed'})
            if commit and not config.options['test_enable']: # pragma: no cover:
                self.env.cr.commit()

            if self.response_format:
                self.ensure_response(globals_dict)
                bytesdata = self.obj_to_bytes(globals_dict['response'], self.response_format)
                if globals_dict.get('msg'):
                    globals_dict['msg'].write({
                        'response': base64.b64encode(bytesdata)
                    })
                if commit and not config.options['test_enable']: # pragma: no cover:
                    self.env.cr.commit()


    def ensure_response(self, globals_dict):
        if 'response' not in globals_dict:
            raise RuntimeError("The consumer code did not assign variable 'response'.")


    def assert_obj_type(self, obj, fmt):
        if fmt in ['json', 'redirect']:
            assert isinstance(obj, (list, dict)), str(type(obj))
        elif fmt == 'xml':
            assert isinstance(obj, (etree._Element)), str(type(obj)) # the wrapped module does not have attr ._Element
        elif fmt == 'csv':
            assert isinstance(obj, (pandas.DataFrame)), str(type(obj))
        elif fmt == 'zip':
            assert isinstance(obj, (zipfile.ZipFile)), str(type(obj))
        else:
            raise NotImplementedError(f"Invalid file format: {fmt}")


    def bytes_to_obj(self, bytesdata, fmt):
        self.ensure_one()
        if fmt in ['json', 'redirect']:
            obj = json.loads(bytesdata, object_hook=json_decoder)
        elif fmt == 'xml':
            obj = lxml.etree.fromstring(bytesdata)
        elif fmt == 'csv':
            obj = pandas.read_csv(io.BytesIO(bytesdata))
        elif fmt == 'zip':
            obj = zipfile.ZipFile(io.BytesIO(bytesdata))
        elif fmt == 'bytes':
            obj = bytesdata
        else:
            raise NotImplementedError(f"Invalid file format: {fmt}")
        self.assert_obj_type(obj, fmt)
        return obj


    def obj_to_bytes(self, obj, fmt):
        self.ensure_one()
        if fmt in ['json', 'redirect']:
            bytesdata = json.dumps(obj, sort_keys=True, indent=4, default=json_encoder).encode('utf-8')
        elif fmt == 'xml':
            bytesdata = lxml.etree.tostring(obj, pretty_print=True, xml_declaration=True, encoding='utf-8')
        elif fmt == 'csv':
            bytesdata = obj.to_csv().encode('utf-8')
        elif fmt == 'zip':
            fp = obj.fp
            fp.seek(0)
            bytesdata = fp.read()
        elif fmt == 'bytes':
            bytesdata = obj
        else:
            raise NotImplementedError(f"Invalid file format: {fmt}")
        assert isinstance(bytesdata, bytes)
        return bytesdata


    @api.model
    def cron_run(self):
        progress = self.env['ir.cron.progress'].browse(self.env.context.get('ir_cron_progress_id') or 0).exists()
        if not (progress and progress.cron_id):
            raise exceptions.ValidationError(_("Unable to run, cron progress is missing: %s") % progress)

        for rec in self.search([('cron_id', '=', progress.cron_id.id),('role', '=', 'active')]).sudo():
            _logger.info("Execute %s", rec.name)
            rec.with_context(force_commit=True, raise_exc=False).action_execute()
            if not config.options['test_enable']: # pragma: no cover
                rec.env.cr.commit()
            while msg := rec.next_from_queue():
                _logger.info("Process %s", msg.name)
                try:
                    globals_dict = msg._get_msg_globals() # READ-ONLY, should be OK not to ROLLBACK
                except Exception as error:
                    # NO ROLLBACK NEEDED.
                    msg.write({'state': 'error'})
                    msg.message_post(body=(str(error)), subtype_xmlid='api_endpoint.mt_integration_error', message_type='comment')
                else:
                    msg.endpoint_id.with_context(force_commit=True, raise_exc=False)._consume(globals_dict) # method _consume already has error handling.
                finally:
                    if not config.options['test_enable']: # pragma: no cover
                        msg.env.cr.commit() # Save all and release msg lock.

                assert msg.state != 'produced', "Programming error, break infinite while loop."


    def next_from_queue(self):
        """
        Get next record to consume and lock it to support multiple cronthreads.
        """
        self.ensure_one()
        Msg = self.env['api.message']
        Msg.flush_model(['endpoint_id', 'state']) # ensure state changes are flushed
        self.env.cr.execute(f"SELECT id FROM {Msg._table} WHERE endpoint_id=%s AND state='produced' ORDER BY id ASC LIMIT 1 FOR UPDATE SKIP LOCKED", (self.id,))
        ids = self.env.cr.fetchall()
        if ids:
            return Msg.browse(ids[0])
        return Msg.browse()


    def xmlrpc(self, url, method, args, verify_ssl=True):
        if not verify_ssl:
            kwargs = dict(context=ssl._create_unverified_context())
        else:
            kwargs = dict()

        proxy = xmlrpc.client.ServerProxy(url, **kwargs)
        call_proxy = getattr(proxy, method)
        try:
            return call_proxy(*args)
        except xmlrpc.client.Fault as err:
            raise exceptions.UserError(err.faultString)
        except xmlrpc.client.ProtocolError as err:
            raise exceptions.UserError(f'Error connecting to {err.url}: {err.errmsg}')

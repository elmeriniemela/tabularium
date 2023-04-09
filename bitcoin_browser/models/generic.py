
from odoo import fields, models

from tinyrpc.protocols.jsonrpc import JSONRPCProtocol
from tinyrpc.transports.http import HttpPostClientTransport
from tinyrpc import RPCClient


class BitcoinJSONRPCProtocol(JSONRPCProtocol):

    def _parse_subreply(self, rep):
        """
        The base class JSONRPCProtocol raises unnecessary errors for missing/extra keys in the response that makes it incompatible with bitcoin RPC.
        """
        rep['jsonrpc'] = self.JSON_RPC_VERSION
        for mutex in ['error', 'result']:
            if rep[mutex] == None:
                del rep[mutex]
        return super()._parse_subreply(rep)


class BigInteger(fields.Integer):
    column_type = ('int8', 'int8')

class ConfigParam(models.Model):
    _inherit = 'ir.config_parameter'

    def bitcoind_proxy(self):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        rpc_client = RPCClient(
            BitcoinJSONRPCProtocol(),
            HttpPostClientTransport(get_param('bitcoind.url'), auth=(get_param('bitcoind.user'), get_param('bitcoind.pw')))
        )
        return rpc_client.get_proxy()

fields.BigInteger = BigInteger

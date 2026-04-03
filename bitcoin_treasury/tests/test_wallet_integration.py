# -*- coding: utf-8 -*-

import datetime
import json
import socket
import socketserver
import ssl
import tempfile
import threading

from btclib.bip32 import rootxprv_from_seed

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.bitcoin_treasury.electrum.bitcoin import address_to_scripthash
from odoo.addons.bitcoin_treasury.models.key import script_type_default
from odoo.addons.bitcoin_treasury.models.wallet import electumx_jsonrpc

_TLS_CERT = """-----BEGIN CERTIFICATE-----
MIIDCTCCAfGgAwIBAgIUQL8HqP+R9ZZgHNAz5tjC5Nod74wwDQYJKoZIhvcNAQEL
BQAwFDESMBAGA1UEAwwJbG9jYWxob3N0MB4XDTI2MDQwMzA4NDQxN1oXDTI3MDQw
MzA4NDQxN1owFDESMBAGA1UEAwwJbG9jYWxob3N0MIIBIjANBgkqhkiG9w0BAQEF
AAOCAQ8AMIIBCgKCAQEAmkFYynrFzh+JN3WYb6l8wFAB/u0K1EsclgC8+7zmDx5G
WW+ByR1hUQJQyrf+K+H+i3j908K1GJmzfsrCLBc4Ecx0CfJncTnAGDHoA3ObrQAl
qgQIK8Ozw9GjLlo9e0g8txlSaH4yvbtUtkE+rWoHnTjhRHi0z40BG0r5jX4oANCr
8KEIjHNnUul2ZnMihw4F0aPtsxQf3tLCTnCNHy9WVipgggAvbrKWn/4QAAwDlEX7
22QV21MOPA6Gp5ymidgV3uruKKCcniGTFupwHHqP+ACCOM5Q+czCAfhRWONeH14G
azD8G4uQiSpYkIn90pyWCKBSDjp7JepfPbvp7ytSfwIDAQABo1MwUTAdBgNVHQ4E
FgQUg9YyLz1QfUGYiVfc0m0pBiK8tMcwHwYDVR0jBBgwFoAUg9YyLz1QfUGYiVfc
0m0pBiK8tMcwDwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAQEAImUQ
yk5rV7gXBDROpStJCEv3yCLpFSSPmFz8VPWQ2fJVeebKUtvRPZoivUwgzzoah1J/
dA3LOdUDU9qqQZt/aFN9l8Eu0KHDSAOiKo9fIIIbJItM+Fcqvv03M/5J0lC9QdRv
DObrksltiKSrZg0JL8qPc60Bx7yMGDubWFxIKaIqIu3363RrKpqhwVU2ic/sG1U6
BV8h90R+7ZeA+8BoBIj2Y3mJjlz6eaJKb7+VSd6LW5IhnxjUZa3GASc9Vk9hnD4+
r1EVNsKFazx4jF1X4dxGdPLgqbRS+E7LpajFkosm58U5KOBWh6pFBcnVdQwIxax0
aMjrS8Sh7ZKp08LceQ==
-----END CERTIFICATE-----
"""

_TLS_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCaQVjKesXOH4k3
dZhvqXzAUAH+7QrUSxyWALz7vOYPHkZZb4HJHWFRAlDKt/4r4f6LeP3TwrUYmbN+
ysIsFzgRzHQJ8mdxOcAYMegDc5utACWqBAgrw7PD0aMuWj17SDy3GVJofjK9u1S2
QT6tagedOOFEeLTPjQEbSvmNfigA0KvwoQiMc2dS6XZmcyKHDgXRo+2zFB/e0sJO
cI0fL1ZWKmCCAC9uspaf/hAADAOURfvbZBXbUw48DoannKaJ2BXe6u4ooJyeIZMW
6nAceo/4AII4zlD5zMIB+FFY414fXgZrMPwbi5CJKliQif3SnJYIoFIOOnsl6l89
u+nvK1J/AgMBAAECggEAD1lKomJWaPZ5wVmp3UAbzsj6dQ+VVCvUwHCtw7P3a/BJ
WlNxmLDoz4lvv5Qdeue/jvvVieryxevGHZ4p28t3Q7IfDVeGh0PFto9n58jRNNG+
1BMXOwxiLuBrujK2SzX6lwXls/1zdnr7tWNHMmf9mCo71zcJisNovxRi23tLmk6b
M/6l1MkyVZoxuPL5i16xZSrvtsWDYBeQP6dT86llm25H9CuuDjujxsI0L06bFAQn
I+etQv7xoGf+H1DM0XolymE5VtofDMmS7vfdvS6E6o9hcTij+/AsPT6f7b/AmvO2
eZy9ezQS8sUtMglsA2ECKpZ4+2XtmUbFt1wRHx4NcQKBgQDQfVkvrzfdrNDWUU2O
sBPJNZIU5pbZw+MjvlVqeNV61bCR1NplHBhDSrrvOb0DkQyALmJUSv47HxJ8D77d
ct0h8x5Sk7FWMww6Cw6MugiQe2+dwsw3OQNjqq9UFo5raaC8MMrE2yk0+KCeEaib
h0zEwsBSNPdHakk0VkzvS5UvbwKBgQC9aCEuhKLIhOw5d3Bj4aVoQ+KT+QiNdHbj
4vGIyB072YP2uXkZ02fkNjTmRu9jx6mOZDAjyEvRdGDMOJmeNcViPJMCRImaUoPr
Nf9jYXYqzMK7tkHWncRXLwY8yD0i7+v5OU+utZqeeQmlO8D9q47Jw2Dw2IIkq3Xu
FeckYLuF8QKBgCsraUYoX8b0u6FE4GxFJTOqdf8B6AZbOzLxfDo5nup6SL9JdZcu
BBAa7y4NpIeShyYbdJzDknSncGpj0D+GQyd+ca7jifqxQzzZgT++XXudM3VVGnfs
xDjk5LzilsbC7ldJOxMb1iJzwL46JdFeaJTtRmk/MlyFM3c0z2VVHyTdAoGBAJcq
UTlAMG8a7zGaKr/8qjfB3ka8/d9vsSeFy8Gf/Pz0SAcU1hsPh54yyRt0R8D57FAx
k94rEJ/VYx/6mFgVkDgsIiQwMSZSbui9itt1QIs+KrkH6Bnyhm4SoMbIBUsp8spQ
vFCyrfmGnnUacJfEYUyUO31dPtknYxKmtnhpH6DxAoGBAMcu6X0zfRhL86hvyFai
wUF3zw/rJYWq/iUyVCsJRy5TZWBc5bj/flDdjw91IVbOSAraFfqaud0xI5Q2ekhl
Q60eUwvdB7Y908ETJ+Au0gWkSMKmMeJVb1d6OKnbipPDHuWHHYl2rC1pA+cthgGp
KcP67gyit4y6ctKGVW5jkb33
-----END PRIVATE KEY-----
"""


class _ElectrumRPCHandler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            line = self.rfile.readline()
            if not line:
                break
            request = json.loads(line.decode("utf-8"))
            self.server.requests.append(request)
            response = self.server.dispatch(request)
            self.wfile.write(json.dumps(response).encode("utf-8") + b"\n")
            self.wfile.flush()


class _ElectrumRPCServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, host_port, dispatch):
        self.dispatch = dispatch
        self.requests = []
        super().__init__(host_port, _ElectrumRPCHandler)


@tagged("post_install", "-at_install")
class TestBitcoinWalletIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Key = cls.env["bitcoin.key"]
        cls.Wallet = cls.env["bitcoin.wallet"]
        cls.WalletKey = cls.env["bitcoin.wallet.key"]
        cls.WalletHistory = cls.env["bitcoin.wallet.history"]
        cls.Tx = cls.env["bitcoin.tx"]
        cls.Block = cls.env["bitcoin.block"]
        cls.Config = cls.env["ir.config_parameter"].sudo()
        cls._seed = 1

    @classmethod
    def _next_seed(cls):
        cls._seed += 1
        return cls._seed

    def _new_key(self, **overrides):
        seed = bytes([self._next_seed()]) * 32
        values = {
            "name": "Key %s" % self._seed,
            "wif": rootxprv_from_seed(seed),
            "witness_type": "segwit",
            "multisig": False,
        }
        values.update(overrides)
        return self.Key.create(values)

    def _new_wallet(self, keys, **overrides):
        values = {
            "name": "Wallet %s" % self._testMethodName,
            "address_amount": 1,
            "gap_limit": 1,
        }
        values.update(overrides)
        wallet = self.Wallet.create(values)
        for sequence, key in enumerate(keys):
            self.WalletKey.create(
                {
                    "wallet_id": wallet.id,
                    "key_id": key.id,
                    "sequence": sequence,
                }
            )
        return wallet

    def _address(self, wallet, atype, index):
        return wallet.address_ids.filtered(lambda rec: rec.atype == str(atype) and rec.index == index)

    def _set_electrumx(self, port):
        self.Config.set_param("electrumx.host", "127.0.0.1")
        self.Config.set_param("electrumx.port", str(port))
        self.Config.set_param("electrumx.use_ssl", "0")

    def _start_electrum_server(self, dispatch):
        server = _ElectrumRPCServer(("127.0.0.1", 0), dispatch)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 1)
        return server, server.server_address[1]

    def _start_electrum_tls_server(self, dispatch):
        tempdir = tempfile.TemporaryDirectory()
        cert_path = tempdir.name + "/cert.pem"
        key_path = tempdir.name + "/key.pem"
        with open(cert_path, "w", encoding="utf-8") as cert_file:
            cert_file.write(_TLS_CERT)
        with open(key_path, "w", encoding="utf-8") as key_file:
            key_file.write(_TLS_KEY)

        server = _ElectrumRPCServer(("127.0.0.1", 0), dispatch)
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.load_cert_chain(cert_path, key_path)
        server.socket = tls_context.wrap_socket(server.socket, server_side=True)

        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 1)
        self.addCleanup(tempdir.cleanup)
        return server, server.server_address[1]

    def _start_disconnect_server(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)

        def _worker():
            connection, _ = listener.accept()
            try:
                connection.recv(1024)
            finally:
                connection.close()
                listener.close()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 1)
        return listener.getsockname()[1]

    def test_script_type_default_matrix_and_invalid(self):
        self.assertEqual(script_type_default("legacy", False, True), "p2pkh")
        self.assertEqual(script_type_default("legacy", False, False), "sig_pubkey")
        self.assertEqual(script_type_default("legacy", True, True), "p2sh")
        self.assertEqual(script_type_default("legacy", True, False), "p2sh_multisig")
        self.assertEqual(script_type_default("segwit", False, True), "p2wpkh")
        self.assertEqual(script_type_default("segwit", False, False), "sig_pubkey")
        self.assertEqual(script_type_default("segwit", True, True), "p2wsh")
        self.assertEqual(script_type_default("segwit", True, False), "p2sh_multisig")
        self.assertEqual(script_type_default("p2sh-segwit", False, True), "p2sh")
        self.assertEqual(script_type_default("p2sh-segwit", False, False), "p2sh_p2wpkh")
        self.assertEqual(script_type_default("p2sh-segwit", True, True), "p2sh")
        self.assertEqual(script_type_default("p2sh-segwit", True, False), "p2sh_p2wsh")
        self.assertEqual(script_type_default("taproot", False, True), "p2tr")
        with self.assertRaises(ValidationError):
            script_type_default("invalid", False, True)

    def test_key_computed_fields(self):
        key = self._new_key()
        self.assertEqual(key.encoding, "bech32")
        self.assertEqual(key.script_type, "p2wpkh")
        self.assertEqual(len(key.fingerprint), 8)

        key.write({"witness_type": "legacy"})
        self.assertEqual(key.encoding, "base58")
        self.assertEqual(key.script_type, "p2pkh")

        key.write({"multisig": True})
        self.assertEqual(key.script_type, "p2sh")

        key_virtual = self.Key.new({"name": "Virtual", "wif": False, "witness_type": "segwit"})
        key_virtual._compute_fingerprint()
        self.assertFalse(key_virtual.fingerprint)

    def test_electrumx_jsonrpc_success_and_connection_failure(self):
        def dispatch(request):
            return {"id": request["id"], "result": {"method": request["method"]}}

        _, port = self._start_electrum_server(dispatch)
        with electumx_jsonrpc("127.0.0.1", port, False) as send:
            response = send({"method": "server.ping", "params": [], "id": 7})
        self.assertEqual(response["result"]["method"], "server.ping")

        _, tls_port = self._start_electrum_tls_server(dispatch)
        with electumx_jsonrpc("127.0.0.1", tls_port, True) as send:
            response_tls = send({"method": "server.version", "params": ["", "1.4"], "id": 8})
        self.assertEqual(response_tls["result"]["method"], "server.version")

        disconnect_port = self._start_disconnect_server()
        with electumx_jsonrpc("127.0.0.1", disconnect_port, False) as send:
            with self.assertRaises(AssertionError):
                send({"method": "server.ping", "params": [], "id": 9})

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
        probe.close()
        with self.assertRaises(UserError):
            with electumx_jsonrpc("127.0.0.1", closed_port, False):
                pass # pragma: no cover

    def test_refresh_addresses_single_key_paths(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=2)
        self.assertEqual(wallet.first_key_id, key)
        self.assertFalse(wallet.multisig)

        wallet.refresh_addresses()
        self.assertEqual(len(wallet.address_ids), 4)

        receiving_0 = self._address(wallet, 0, 0)
        old_address = receiving_0.address

        key.write({"witness_type": "legacy"})
        wallet.refresh_addresses()
        receiving_0.invalidate_recordset(["address"])
        self.assertNotEqual(receiving_0.address, old_address)
        self.assertEqual(len(wallet.address_ids), 4)

        key.write({"witness_type": "segwit", "multisig": True})
        with self.assertRaises(ValidationError):
            wallet.refresh_addresses()

        empty_wallet = self._new_wallet([])
        with self.assertRaises(UserError):
            empty_wallet.refresh_addresses()

    def test_refresh_addresses_multisig_paths(self):
        key_a = self._new_key(multisig=True, witness_type="legacy")
        key_b = self._new_key(multisig=True, witness_type="legacy")
        wallet = self._new_wallet([key_a, key_b], sigs_required=2)
        self.assertTrue(wallet.multisig)

        wallet.refresh_addresses()
        self.assertEqual(len(wallet.address_ids), 2)

        key_a.write({"witness_type": "segwit", "multisig": False})
        with self.assertRaises(ValidationError):
            wallet.refresh_addresses()

    def test_refresh_calls_refresh_addresses_transactions_and_history(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=1, gap_limit=1)

        def dispatch(request):
            return {"id": request["id"], "result": []}

        _, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)
        wallet.refresh()

        self.assertEqual(len(wallet.address_ids), 2)
        self.assertEqual(wallet.balance, 0.0)
        self.assertEqual(wallet.transactions, 0)

    def test_refresh_transactions_links_cleanup_and_gap_limit(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=3, gap_limit=1)
        wallet.refresh_addresses()
        receiving_0 = self._address(wallet, 0, 0)
        receiving_1 = self._address(wallet, 0, 1)

        tx_old = self.Tx.create({"txid": "1" * 64})
        tx_new = self.Tx.create({"txid": "2" * 64})
        receiving_0.transaction_ids = [Command.set(tx_old.ids)]

        history_map = {
            address_to_scripthash(receiving_0.address): [{"tx_hash": tx_new.txid}],
            address_to_scripthash(receiving_1.address): [],
        }

        def dispatch(request):
            sh = request["params"][0]
            return {"id": request["id"], "result": history_map.get(sh, [])}

        server, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)
        wallet.with_context(disable_auto_populate=True).refresh_transactions()

        self.assertEqual(receiving_0.transaction_ids.ids, tx_new.ids)
        self.assertNotIn(tx_old, receiving_0.transaction_ids)
        self.assertGreaterEqual(
            len([req for req in server.requests if req["method"] == "blockchain.scripthash.get_history"]),
            3,
        )

    def test_refresh_transactions_missing_tx_raises(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=1, gap_limit=1)
        wallet.refresh_addresses()
        receiving_0 = self._address(wallet, 0, 0)
        missing_txid = "a" * 64

        def dispatch(request):
            sh = request["params"][0]
            if sh == address_to_scripthash(receiving_0.address):
                return {"id": request["id"], "result": [{"tx_hash": missing_txid}]}
            return {"id": request["id"], "result": []} # pragma: no cover

        _, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)
        with self.assertRaises(UserError):
            wallet.with_context(disable_auto_populate=True).refresh_transactions()

    def test_refresh_transactions_none_result_raises(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=1, gap_limit=1)
        wallet.refresh_addresses()
        receiving_0 = self._address(wallet, 0, 0)

        def dispatch(request):
            if request["method"] == "blockchain.scripthash.get_history":
                sh = request["params"][0]
                if sh == address_to_scripthash(receiving_0.address):
                    return {"id": request["id"], "result": None}
                return {"id": request["id"], "result": []} # pragma: no cover
            if request["method"] == "server.version":
                return {"id": request["id"], "result": "test/1.4"}
            raise AssertionError("Unexpected method %s" % request["method"]) # pragma: no cover

        server, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)
        with self.assertRaises(UserError):
            wallet.with_context(disable_auto_populate=True).refresh_transactions()
        self.assertIn("server.version", [req["method"] for req in server.requests])

    def test_refresh_transactions_ran_out_of_addresses_raises(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=1, gap_limit=5)
        wallet.refresh_addresses()
        receiving_0 = self._address(wallet, 0, 0)
        tx = self.Tx.create({"txid": "3" * 64})

        def dispatch(request):
            if request["method"] == "blockchain.scripthash.get_history":
                sh = request["params"][0]
                if sh == address_to_scripthash(receiving_0.address):
                    return {"id": request["id"], "result": [{"tx_hash": tx.txid}]}
                return {"id": request["id"], "result": []} # pragma: no cover
            raise AssertionError("Unexpected method %s" % request["method"]) # pragma: no cover

        _, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)
        with self.assertRaises(UserError):
            wallet.with_context(disable_auto_populate=True).refresh_transactions()

    def test_refresh_history_computes_balances_and_other_wallets(self):
        wallet_a = self._new_wallet([self._new_key()], address_amount=1)
        wallet_b = self._new_wallet([self._new_key()], address_amount=1)
        wallet_a.refresh_addresses()
        wallet_b.refresh_addresses()

        a_recv = self._address(wallet_a, 0, 0)
        a_change = self._address(wallet_a, 1, 0)
        b_recv = self._address(wallet_b, 0, 0)

        prev = self.Tx.create(
            {
                "txid": "4" * 64,
                "vin_ids": [
                    Command.create(
                        {
                            "sequence": 1,
                            "coinbase": "1111",
                            "vout_tx_id": False,
                            "vout": False,
                        }
                    )
                ],
                "vout_ids": [
                    Command.create(
                        {
                            "n": 0,
                            "type": "pubkeyhash",
                            "address": b_recv.address,
                            "asm": "asm",
                            "value": 1.2,
                        }
                    )
                ],
            }
        )
        tx_in = self.Tx.create(
            {
                "txid": "5" * 64,
                "blocktime": datetime.datetime(2024, 1, 1, 12, 0, 0),
                "vin_ids": [Command.create({"sequence": 2, "vout_tx_id": prev.id, "vout": 0})],
                "vout_ids": [
                    Command.create(
                        {
                            "n": 0,
                            "type": "pubkeyhash",
                            "address": a_recv.address,
                            "asm": "asm",
                            "value": 1.0,
                        }
                    )
                ],
            }
        )
        block = self.Block.create({"hash": "6" * 64, "time": datetime.datetime(2024, 1, 2, 12, 0, 0)})
        tx_out = self.Tx.create(
            {
                "txid": "7" * 64,
                "block_id": block.id,
                "vin_ids": [Command.create({"sequence": 3, "vout_tx_id": tx_in.id, "vout": 0})],
                "vout_ids": [
                    Command.create(
                        {
                            "n": 0,
                            "type": "pubkeyhash",
                            "address": b_recv.address,
                            "asm": "asm",
                            "value": 0.4,
                        }
                    ),
                    Command.create(
                        {
                            "n": 1,
                            "type": "pubkeyhash",
                            "address": a_change.address,
                            "asm": "asm",
                            "value": 0.5,
                        }
                    ),
                ],
            }
        )

        a_recv.transaction_ids = [Command.set([tx_in.id, tx_out.id])]
        a_change.transaction_ids = [Command.set([tx_out.id])]

        wallet_a.refresh_history()
        self.assertEqual(wallet_a.transactions, 2)
        self.assertAlmostEqual(wallet_a.balance, 0.5)

        history_in = self.WalletHistory.search(
            [("wallet_id", "=", wallet_a.id), ("transaction_id", "=", tx_in.id)], limit=1
        )
        history_out = self.WalletHistory.search(
            [("wallet_id", "=", wallet_a.id), ("transaction_id", "=", tx_out.id)], limit=1
        )
        (history_in + history_out)._compute_other_wallet_ids()
        self.assertAlmostEqual(history_in.amount, 1.0)
        self.assertAlmostEqual(history_out.amount, -0.5)
        self.assertEqual(history_in.date, tx_in.blocktime)
        self.assertEqual(history_out.date, block.time)
        self.assertNotIn(wallet_a, history_in.other_wallet_ids)
        self.assertNotIn(wallet_a, history_out.other_wallet_ids)

        self.assertIn(wallet_b, tx_out.vout_ids.filtered(lambda out: out.address == b_recv.address).wallet_ids)
        self.assertIn(wallet_a, tx_out.vin_ids.wallet_ids)

        self.assertAlmostEqual(a_recv.balance, 0.0)
        self.assertAlmostEqual(a_change.balance, 0.5)

        tx_out.vout_ids.filtered(lambda out: out.address == a_change.address).write({"value": 0.2})
        wallet_a.refresh_history()
        self.assertEqual(wallet_a.transactions, 2)
        self.assertAlmostEqual(wallet_a.balance, 0.2)

        history_out.invalidate_recordset(["amount"])
        self.assertAlmostEqual(history_out.amount, -0.8)

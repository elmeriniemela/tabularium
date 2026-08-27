# -*- coding: utf-8 -*-

import calendar
import datetime
import json
import socketserver
import threading

from bitwalkit import (
    ExtendedKey,
    base58check_decode,
    base58check_encode,
    descriptor_checksum,
)

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged



class _ElectrumRPCHandler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            line = self.rfile.readline()
            if not line:
                break
            request = json.loads(line.decode("utf-8"))
            self.server.raw_requests.append(request)
            if isinstance(request, list):
                self.server.requests.extend(request)
                response = [self.server.dispatch(item) for item in request]
            else:
                self.server.requests.append(request)
                response = self.server.dispatch(request)
            self.wfile.write(json.dumps(response).encode("utf-8") + b"\n")
            self.wfile.flush()


class _ElectrumRPCServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, host_port, dispatch):
        self.dispatch = dispatch
        self.requests = []
        self.raw_requests = []
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
        cls._root_xpub = (
            "xpub661MyMwAqRbcGFeMhhkrJL6Yj3YKQFNZQSM2BAvoMmhdjNKBh43n5v3c4YT5dFtjkirfhqQH"
            "Md22br7cHAQXAV8cZdicedZJkNweja4WWBK"
        )
        cls._seed = 1

    @classmethod
    def _next_seed(cls):
        cls._seed += 1
        return cls._seed

    def _new_key(self, **overrides):
        index = self._next_seed()
        values = {
            "name": "Key %s" % self._seed,
            "wif": ExtendedKey.parse(self._root_xpub).child(index).serialize(),
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

    def test_script_type_default_matrix_and_invalid(self):
        self.assertEqual(self.Key._script_type_default("legacy", False), "p2pkh")
        self.assertEqual(self.Key._script_type_default("legacy", True), "p2sh")
        self.assertEqual(self.Key._script_type_default("segwit", False), "p2wpkh")
        self.assertEqual(self.Key._script_type_default("segwit", True), "p2wsh")
        self.assertEqual(self.Key._script_type_default("p2sh-segwit", False), "p2sh_p2wpkh")
        self.assertEqual(self.Key._script_type_default("p2sh-segwit", True), "p2sh_p2wsh")
        self.assertEqual(self.Key._script_type_default("taproot", False), "p2tr")
        with self.assertRaises(ValidationError):
            self.Key._script_type_default("invalid", False)

    def test_single_signature_descriptor(self):
        key = self._new_key(
            real_parent_fingerprint="DEADBEEF",
            real_derivation_path="m/84'/0'/0'",
        )
        wallet = self._new_wallet([key])
        payload = "wpkh([deadbeef/84h/0h/0h]%s/<0;1>/*)" % key.wif
        self.assertEqual(
            wallet.descriptor,
            "%s#%s" % (payload, descriptor_checksum(payload)),
        )

        key.write({"real_derivation_path": "m"})
        payload = "wpkh([deadbeef]%s/<0;1>/*)" % key.wif
        self.assertEqual(
            wallet.descriptor,
            "%s#%s" % (payload, descriptor_checksum(payload)),
        )

        key.write({"real_parent_fingerprint": False, "real_derivation_path": False})
        payload = "wpkh(%s/<0;1>/*)" % key.wif
        self.assertEqual(
            wallet.descriptor,
            "%s#%s" % (payload, descriptor_checksum(payload)),
        )

    def test_multisig_descriptor(self):
        key_a = self._new_key(multisig=True)
        key_b = self._new_key(multisig=True)
        wallet = self._new_wallet([key_a, key_b], sigs_required=2)
        payload = "wsh(sortedmulti(2,%s/<0;1>/*,%s/<0;1>/*))" % (key_a.wif, key_b.wif)
        self.assertEqual(
            wallet.descriptor,
            "%s#%s" % (payload, descriptor_checksum(payload)),
        )

    def test_descriptor_timestamp(self):
        wallet = self._new_wallet([self._new_key()])
        self.assertEqual(
            wallet.birth_timestamp,
            str(calendar.timegm(wallet.create_date.utctimetuple())),
        )

        earliest = datetime.datetime(2024, 1, 1, 12, 0, 0)
        for index, date in enumerate((datetime.datetime(2024, 2, 1, 12, 0, 0), earliest)):
            self.WalletHistory.create({
                "wallet_id": wallet.id,
                "date": date,
                "amount": 1,
                "transaction_id": self.Tx.create({"txid": str(index) * 64}).id,
            })

        self.assertEqual(wallet.birth_timestamp, str(calendar.timegm(earliest.utctimetuple())))

    def test_descriptor_unsupported_wallets(self):
        invalid_wallets = [
            self._new_wallet([]),
            self._new_wallet([self._new_key(witness_type="legacy")]),
            self._new_wallet([self._new_key(multisig=True)]),
            self._new_wallet([self._new_key(multisig=True), self._new_key()]),
        ]

        keys = [self._new_key(multisig=True), self._new_key(multisig=True)]
        invalid_wallets.append(self._new_wallet(keys, sigs_required=3))
        keys = [self._new_key(multisig=True) for _index in range(16)]
        invalid_wallets.append(self._new_wallet(keys))

        for wallet in invalid_wallets:
            self.assertTrue(wallet.descriptor)
            self.assertNotIn('#', wallet.descriptor)

    def test_descriptor_reports_invalid_existing_key_origin(self):
        key = self._new_key()
        wallet = self._new_wallet([key])
        self.env.cr.execute(
            "UPDATE bitcoin_key SET real_parent_fingerprint = %s WHERE id = %s",
            ("deadbee", key.id),
        )
        key.invalidate_recordset(["real_parent_fingerprint"])

        wallet._compute_descriptor()

        self.assertTrue(wallet.descriptor)
        self.assertNotIn('#', wallet.descriptor)

    def test_key_origin_validation(self):
        invalid_origins = [
            {"real_parent_fingerprint": "deadbee"},
            {"real_derivation_path": "m/84'/0'/0'"},
            {"real_parent_fingerprint": "deadbeef", "real_derivation_path": "m/84'/0'/*"},
        ]
        for origin in invalid_origins:
            with self.assertRaises(ValidationError):
                self._new_key(**origin)

        invalid_key = self.Key.new({
            "wif": self._new_key().wif,
            "real_parent_fingerprint": "deadbee",
        })
        self.assertTrue(invalid_key._key_origin_error())

    def test_key_computed_fields(self):
        key = self._new_key()
        self.assertEqual(key.encoding, "bech32")
        self.assertEqual(key.script_type, "p2wpkh")

        key.write({"witness_type": "legacy"})
        self.assertEqual(key.encoding, "base58")
        self.assertEqual(key.script_type, "p2pkh")

        key.write({"multisig": True})
        self.assertEqual(key.script_type, "p2sh")

    def test_key_accepts_mainnet_extended_public_key_versions(self):
        versions = (0x0488B21E, 0x049D7CB2, 0x04B24746, 0x0295B43F, 0x02AA7ED3)
        for index, version in enumerate(versions):
            derived = ExtendedKey.parse(self._root_xpub).child(index).serialize()
            raw = base58check_decode(derived)
            key = self._new_key(
                wif=base58check_encode(version.to_bytes(4, "big") + raw[4:])
            )
            self.assertTrue(key._descriptor_key().startswith("xpub"))

    def test_key_rejects_non_mainnet_public_material(self):
        private_key = (
            "xprv9s21ZrQH143K3mZtbgDqwC9pB1hpznei3DRRNnXBoSAerZz39WjXY7j8DGtLtww1M8dm"
            "JsNngHtKFCdYG4oE5Lt1S1VtMCQ8XoYPEsbkuuT"
        )
        raw = base58check_decode(ExtendedKey.parse(self._root_xpub).child(0).serialize())
        testnet_public_key = base58check_encode(bytes.fromhex("043587cf") + raw[4:])
        unknown_version_key = base58check_encode(bytes.fromhex("01020304") + raw[4:])
        initial_keys = self.Key.search_count([])
        initial_messages = self.env["mail.message"].search_count([("model", "=", "bitcoin.key")])

        for value in (private_key, testnet_public_key, unknown_version_key, "not-an-extended-key"):
            with self.assertRaises(ValidationError):
                self._new_key(wif=value)

        self.assertEqual(self.Key.search_count([]), initial_keys)
        self.assertEqual(
            self.env["mail.message"].search_count([("model", "=", "bitcoin.key")]),
            initial_messages,
        )

        key = self._new_key()
        original_public_key = key.wif
        with self.assertRaises(ValidationError):
            key.write({"wif": private_key})
        self.assertEqual(key.wif, original_public_key)

    def test_address_to_scripthash(self):
        scripthash = self.env["bitcoin.wallet.address"]._address_to_scripthash(
            "bc1qdy2tx6quz0auwkm0k339r2ywy7wr7wrzq4m8mk"
        )
        self.assertEqual(scripthash, "9d8a38623329e4cc3a3ab29cfa7fef02bad30f3b2efa61c2c102898dff2c4f7e")

    def test_refresh_addresses_single_key_paths(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=2)
        self.assertEqual(wallet.first_key_id, key)
        self.assertFalse(wallet.multisig)

        wallet.refresh_addresses()
        self.assertEqual(len(wallet.address_ids), 4)

        receiving_0 = self._address(wallet, 0, 0)
        old_address = receiving_0.address
        stale_tx = self.Tx.create({"txid": "3" * 64})
        receiving_0.write({
            "transaction_ids": [Command.set(stale_tx.ids)],
            "scripthash_status": "stale-status",
        })

        key.write({"witness_type": "legacy"})
        wallet.refresh_addresses()
        receiving_0.invalidate_recordset(["address", "transaction_ids", "scripthash_status"])
        self.assertNotEqual(receiving_0.address, old_address)
        self.assertFalse(receiving_0.transaction_ids)
        self.assertFalse(receiving_0.scripthash_status)
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

    def test_refresh_addresses_multisig_uses_bip67_sorting(self):
        key_a = self._new_key(multisig=True)
        key_b = self._new_key(multisig=True)
        wallet_ab = self._new_wallet([key_a, key_b], sigs_required=2)
        wallet_ba = self._new_wallet([key_b, key_a], sigs_required=2)

        (wallet_ab | wallet_ba).refresh_addresses()

        self.assertEqual(
            wallet_ab.address_ids.sorted(lambda address: (address.atype, address.index)).mapped("address"),
            wallet_ba.address_ids.sorted(lambda address: (address.atype, address.index)).mapped("address"),
        )

    def test_refresh_addresses_wrapped_segwit(self):
        account_a = ExtendedKey.parse(self._root_xpub).child(1).serialize()
        account_b = ExtendedKey.parse(self._root_xpub).child(2).serialize()

        single_key = self._new_key(wif=account_a, witness_type="p2sh-segwit")
        single_wallet = self._new_wallet([single_key])
        single_wallet.refresh_addresses()
        self.assertEqual(
            self._address(single_wallet, 0, 0).address,
            "33YCu16ApjG8Hp7exycEwgVzfVQxjLAe7m",
        )

        keys = [
            self._new_key(wif=account_a, witness_type="p2sh-segwit", multisig=True),
            self._new_key(wif=account_b, witness_type="p2sh-segwit", multisig=True),
        ]
        multisig_wallet = self._new_wallet(keys, sigs_required=2)
        multisig_wallet.refresh_addresses()
        self.assertEqual(
            self._address(multisig_wallet, 0, 0).address,
            "3Bke1vqUtyAcZb6yJkMTKrU6AckyJYd8m2",
        )

    def test_refresh_calls_refresh_addresses_transactions_and_history(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=1, gap_limit=1)

        def dispatch(request):
            if request["method"] == "blockchain.scripthash.subscribe":
                return {"id": request["id"], "result": None}
            raise AssertionError("Unexpected method %s" % request["method"]) # pragma: no cover

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

        receiving_0_scripthash = receiving_0.scripthash
        history_map = {
            receiving_0_scripthash: [{"tx_hash": tx_new.txid, "height": 1}],
        }
        status_map = {
            receiving_0_scripthash: "status-new",
            receiving_1.scripthash: None,
        }

        def dispatch(request):
            sh = request["params"][0]
            if request["method"] == "blockchain.scripthash.subscribe":
                if sh in status_map:
                    return {"id": request["id"], "result": status_map[sh]}
                return {"id": request["id"], "result": None}
            if request["method"] == "blockchain.scripthash.get_history":
                return {"id": request["id"], "result": history_map[sh]}
            raise AssertionError("Unexpected method %s" % request["method"]) # pragma: no cover

        server, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)
        wallet.with_context(disable_auto_populate=True).refresh_transactions()

        self.assertEqual(receiving_0.transaction_ids.ids, tx_new.ids)
        self.assertEqual(receiving_0.scripthash_status, "status-new")
        self.assertNotIn(tx_old, receiving_0.transaction_ids)
        subscribe_requests = [
            req for req in server.requests if req["method"] == "blockchain.scripthash.subscribe"
        ]
        history_requests = [
            req for req in server.requests if req["method"] == "blockchain.scripthash.get_history"
        ]
        self.assertEqual(len(subscribe_requests), 6)
        self.assertEqual(len(history_requests), 1)
        self.assertTrue(all(req["method"] == "blockchain.scripthash.subscribe" for req in server.raw_requests[0]))
        self.assertTrue(all(req["method"] == "blockchain.scripthash.get_history" for req in server.raw_requests[1]))

    def test_refresh_transactions_batches_multiple_wallets(self):
        wallets = self.Wallet
        status_map = {}
        history_map = {}
        transactions = self.Tx
        for index in range(2):
            wallet = self._new_wallet([self._new_key()], address_amount=2, gap_limit=1)
            wallet.refresh_addresses()
            address = self._address(wallet, 0, 0)
            transaction = self.Tx.create({"txid": str(index + 3) * 64})
            wallets |= wallet
            transactions |= transaction
            status_map.update(dict.fromkeys(wallet.address_ids.mapped("scripthash")))
            status_map[address.scripthash] = "status-%s" % index
            history_map[address.scripthash] = [{"tx_hash": transaction.txid, "height": 1}]

        def dispatch(request):
            scripthash = request["params"][0]
            if request["method"] == "blockchain.scripthash.subscribe":
                return {"id": request["id"], "result": status_map[scripthash]}
            if request["method"] == "blockchain.scripthash.get_history":
                return {"id": request["id"], "result": history_map[scripthash]}
            raise AssertionError("Unexpected method %s" % request["method"]) # pragma: no cover

        server, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)
        wallets.with_context(disable_auto_populate=True).refresh_transactions()

        self.assertEqual(wallets.address_ids.transaction_ids, transactions)
        self.assertEqual(len(server.raw_requests), 2)
        self.assertEqual(len(server.raw_requests[0]), 8)
        self.assertEqual(len(server.raw_requests[1]), 2)
        self.assertTrue(all(req["method"] == "blockchain.scripthash.subscribe" for req in server.raw_requests[0]))
        self.assertTrue(all(req["method"] == "blockchain.scripthash.get_history" for req in server.raw_requests[1]))

    def test_refresh_transactions_unchanged_status_skips_history(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=2, gap_limit=1)
        wallet.refresh_addresses()
        receiving_0 = self._address(wallet, 0, 0)
        tx = self.Tx.create({"txid": "8" * 64})
        receiving_0.write({
            "transaction_ids": [Command.set(tx.ids)],
            "scripthash_status": "same-status",
        })

        status_map = {
            receiving_0.scripthash: "same-status",
        }

        def dispatch(request):
            if request["method"] == "blockchain.scripthash.subscribe":
                sh = request["params"][0]
                if sh in status_map:
                    return {"id": request["id"], "result": status_map[sh]}
                return {"id": request["id"], "result": None}
            raise AssertionError("Unexpected method %s" % request["method"]) # pragma: no cover

        server, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)
        wallet.with_context(disable_auto_populate=True).refresh_transactions()

        self.assertEqual(receiving_0.transaction_ids.ids, tx.ids)
        self.assertEqual(receiving_0.scripthash_status, "same-status")
        self.assertFalse(
            [req for req in server.requests if req["method"] == "blockchain.scripthash.get_history"]
        )

    def test_refresh_transactions_empty_status_clears_address_state(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=1, gap_limit=1)
        wallet.refresh_addresses()
        receiving_0 = self._address(wallet, 0, 0)
        stale_tx = self.Tx.create({"txid": "9" * 64})
        receiving_0.write({
            "transaction_ids": [Command.set(stale_tx.ids)],
            "scripthash_status": "stale-status",
        })

        def dispatch(request):
            if request["method"] == "blockchain.scripthash.subscribe":
                return {"id": request["id"], "result": None}
            raise AssertionError("Unexpected method %s" % request["method"]) # pragma: no cover

        server, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)
        wallet.with_context(disable_auto_populate=True).refresh_transactions()

        self.assertFalse(receiving_0.transaction_ids)
        self.assertFalse(receiving_0.scripthash_status)
        self.assertFalse(
            [req for req in server.requests if req["method"] == "blockchain.scripthash.get_history"]
        )

    def test_refresh_transactions_missing_tx_raises(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=2, gap_limit=1)
        wallet.refresh_addresses()
        receiving_0 = self._address(wallet, 0, 0)
        missing_txid = "a" * 64

        def dispatch(request):
            if request["method"] == "blockchain.scripthash.subscribe":
                sh = request["params"][0]
                if sh == receiving_0.scripthash:
                    return {"id": request["id"], "result": "missing-status"}
                return {"id": request["id"], "result": None}
            if request["method"] == "blockchain.scripthash.get_history":
                return {"id": request["id"], "result": [{"tx_hash": missing_txid, "height": 1}]}
            raise AssertionError("Unexpected method %s" % request["method"]) # pragma: no cover

        _, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)
        with self.assertRaises(UserError):
            wallet.with_context(disable_auto_populate=True).refresh_transactions()

    def test_refresh_transactions_none_result_raises(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=2, gap_limit=1)
        wallet.refresh_addresses()
        receiving_0 = self._address(wallet, 0, 0)

        def dispatch(request):
            if request["method"] == "blockchain.scripthash.subscribe":
                sh = request["params"][0]
                if sh == receiving_0.scripthash:
                    return {"id": request["id"], "result": "bad-history-status"}
                return {"id": request["id"], "result": None}
            if request["method"] == "blockchain.scripthash.get_history":
                return {"id": request["id"], "result": None}
            raise AssertionError("Unexpected method %s" % request["method"]) # pragma: no cover

        server, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)
        with self.assertRaises(UserError):
            wallet.with_context(disable_auto_populate=True).refresh_transactions()

    def test_refresh_transactions_ran_out_of_addresses_raises(self):
        key = self._new_key()
        wallet = self._new_wallet([key], address_amount=1, gap_limit=5)
        wallet.refresh_addresses()
        receiving_0 = self._address(wallet, 0, 0)

        def dispatch(request):
            if request["method"] == "blockchain.scripthash.subscribe":
                sh = request["params"][0]
                if sh == receiving_0.scripthash:
                    return {"id": request["id"], "result": "full-window-status"}
                return {"id": request["id"], "result": None} # pragma: no cover
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
                            "n": 0,
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
                            "script_pub_key_hex": "00",
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
                "vin_ids": [Command.create({"n": 0, "sequence": 2, "vout_tx_id": prev.id, "vout": 0})],
                "vout_ids": [
                    Command.create(
                        {
                            "n": 0,
                            "type": "pubkeyhash",
                            "address": a_recv.address,
                            "asm": "asm",
                            "script_pub_key_hex": "00",
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
                "vin_ids": [Command.create({"n": 0, "sequence": 3, "vout_tx_id": tx_in.id, "vout": 0})],
                "vout_ids": [
                    Command.create(
                        {
                            "n": 0,
                            "type": "pubkeyhash",
                            "address": b_recv.address,
                            "asm": "asm",
                            "script_pub_key_hex": "00",
                            "value": 0.4,
                        }
                    ),
                    Command.create(
                        {
                            "n": 1,
                            "type": "pubkeyhash",
                            "address": a_change.address,
                            "asm": "asm",
                            "script_pub_key_hex": "00",
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

# Bitcoin Browser

Bitcoin Browser is an Odoo addon for browsing Bitcoin blockchain data inside
Odoo. It stores blocks, transactions, inputs, and outputs, fetches missing data
from a Bitcoin Core JSON-RPC node, and renders Bitcoin Script verification
traces for transactions.

## Features

- Adds an `Explorer` application menu for blocks, transactions, inputs, and
  outputs.
- Fetches block metadata and full transaction data from Bitcoin Core RPC.
- Auto-populates exact block-hash and transaction-id searches when records are
  not already stored.
- Tracks transaction inputs, outputs, spent-output relationships, coinbase data,
  fees, weights, sizes, locktime, and block membership.
- Provides a transaction script visualization in the backend transaction form.
- Exposes a public script visualization route at `/bitcoin/tx/<txid>`.

## Configuration

After installing the module, configure these Odoo system parameters:

| Parameter | Purpose | Example |
| --- | --- | --- |
| `bitcoind.url` | Bitcoin Core RPC endpoint URL | `http://127.0.0.1:8332` |
| `bitcoind.user` | Bitcoin Core RPC username | `odoo` |
| `bitcoind.pw` | Bitcoin Core RPC password | `secret` |

## Usage

1. Install the `bitcoin_browser` module.
2. Give users the `Bitcoin / User` or `Bitcoin / Administrator` access group.
3. Open the `Explorer` app menu.
4. Search blocks by exact block hash or transactions by exact transaction ID.
5. Use the `Refresh` button on block and transaction forms to fetch or update
   data from the configured Bitcoin Core node.

Searching by exact block hash or transaction ID can create and refresh the
record automatically unless the caller disables auto-population through context.

## Public Route

The route `/bitcoin/tx/<txid>` renders the script visualization for a stored
transaction. If the stored transaction is not visualized yet, the controller
forces a transaction refresh before rendering.

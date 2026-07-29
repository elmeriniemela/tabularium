# Bitcoin Explorer

Bitcoin Explorer is an Odoo addon for browsing Bitcoin blockchain data inside
Odoo. It stores only the blocks, transactions, inputs, and outputs that users
look up or refresh, fetching missing data lazily from a Bitcoin Core JSON-RPC
node. It also renders Bitcoin Script verification traces for transactions.

## Features

- Adds an `Explorer` application menu for blocks, transactions, inputs, and
  outputs.
- Lazily fetches block metadata and full transaction data from Bitcoin Core RPC.
- Auto-populates exact block-hash and transaction-id searches only when records
  are not already stored.
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

1. Install the `bitcoin_explorer` module.
2. Give users the `Bitcoin / User` or `Bitcoin / Administrator` access group.
3. Open the `Explorer` app menu.
4. Search blocks by exact block hash or transactions by exact transaction ID.
5. Use the `Refresh` button on block and transaction forms to fetch or update
   data from the configured Bitcoin Core node.

## Lazy Storage

Bitcoin Explorer does not import or mirror the full blockchain. Records are
stored on demand:

- An exact block-hash search creates a `bitcoin.block` record when it is missing
  and fetches the block from Bitcoin Core.
- An exact transaction-id search creates a `bitcoin.tx` record when it is
  missing and fetches the transaction from Bitcoin Core.
- Fetching a block with transactions stores the transactions included in that
  block.
- Fetching a transaction stores its inputs and outputs. Referenced previous
  transactions are represented as lightweight records first, then populated when
  they are looked up or refreshed.
- The `Refresh` button updates an existing stored record from Bitcoin Core.

This behavior keeps the Odoo database focused on the subset of Bitcoin data that
has actually been browsed. Auto-population can be disabled by passing
`disable_auto_populate` in context.

## Public Route

The route `/bitcoin/tx/<txid>` renders the script visualization for a stored
transaction. If the stored transaction is not visualized yet, the controller
forces a transaction refresh before rendering.

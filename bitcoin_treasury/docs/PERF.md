# electrs Wallet History Performance Notes

## Summary

There is no electrs endpoint that accepts a batch of addresses or scripthashes
for `blockchain.scripthash.get_history`.

The efficient wallet workflow is to use JSON-RPC batching at the transport
level, and to subscribe to scripthashes before asking for their histories.
Subscription is not just a notification mechanism in electrs: it builds and
stores per-client `ScriptHashStatus`, which later `get_history`, `get_balance`,
and `listunspent` calls can reuse.

## Supported RPC Shape

The RPC parser exposes these single-scripthash methods:

- `blockchain.scripthash.get_balance`
- `blockchain.scripthash.get_history`
- `blockchain.scripthash.listunspent`
- `blockchain.scripthash.subscribe`
- `blockchain.scripthash.unsubscribe`

Each takes one `ScriptHash`. There is no method like
`blockchain.scripthashes.get_history`, and `get_history` does not accept an
array of scripthashes as one method call.

electrs does support JSON-RPC batch arrays, so clients can send many individual
RPC calls in one TCP message:

```json
[
  {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "blockchain.scripthash.get_history",
    "params": ["scripthash1"]
  },
  {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "blockchain.scripthash.get_history",
    "params": ["scripthash2"]
  }
]
```

That reduces round trips, but it is still handled as many logical
single-scripthash calls.

## Important Optimization

electrs has a special multi-call path for JSON-RPC batches containing only
`blockchain.scripthash.subscribe` calls.

When a batch is entirely scripthash subscriptions, electrs collects all
scripthashes and computes the new statuses in parallel with Rayon. This is the
only special batch optimization in the Electrum RPC handler.

This means the best initial wallet scan is:

```json
[
  {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "blockchain.scripthash.subscribe",
    "params": ["scripthash1"]
  },
  {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "blockchain.scripthash.subscribe",
    "params": ["scripthash2"]
  }
]
```

Do not mix `subscribe` and `get_history` in the same batch if the goal is to
use this optimized path. Mixed batches fall back to ordinary per-call handling.

## Why Subscription First Is Faster

For an unsubscribed scripthash, `blockchain.scripthash.get_history` calls
`new_status()`. That creates a fresh `ScriptHashStatus` and calls
`tracker.update_scripthash_status()`, which syncs that status from the index and
mempool before returning the history.

For a subscribed scripthash, the client already has an entry in
`client.scripthashes`. In that case, `get_history` simply serializes
`status.get_history()` from the cached status.

The same pattern applies to `get_balance` and `listunspent`: they are cheaper
after subscription because they reuse the status stored in the client state.

## Most Efficient Wallet Workflow

Use one long-lived TCP connection per wallet refresh or wallet session.

1. Derive addresses client-side.
2. Convert each address to Electrum scripthash client-side.
3. Batch `blockchain.scripthash.subscribe` calls for a derivation window.
4. Use returned status hashes:
   - `null` means no history for that scripthash.
   - non-null means there is history.
   - unchanged status hash means the client can keep its cached local history.
   - changed status hash means fetch that scripthash's history again.
5. Batch `blockchain.scripthash.get_history` only for non-empty changed hashes.
6. Deduplicate txids across all histories.
7. Batch `blockchain.transaction.get` for only the missing txids.
8. For confirmed transactions, batch block/header or merkle-proof lookups only
   for unique heights or unique txids as needed.

For HD wallets, scan in branch windows:

- receiving branch: change/index path `0/i`
- change branch: change/index path `1/i`
- stop each branch after the wallet gap limit is reached
- extend the derivation window only when used addresses appear near the end

## Connection Lifetime

The subscription cache is per client connection. Reconnecting loses the
`client.scripthashes` map, so the client must resubscribe and rebuild status on
the next connection.

For best performance:

- keep the connection open during the full refresh;
- avoid opening one connection per address;
- avoid reconnecting between subscribe and history calls;
- preserve local status hashes between refreshes so unchanged addresses do not
  need history calls.

## PR #1252

PR romanz/electrs#1252, merged on 2026-06-13, switches electrs to `bindex`.
That improves the backend cost of status/history construction, especially for
large histories.

It does not change the Electrum RPC workflow:

- no new batch history endpoint;
- no wallet-level history endpoint;
- no multi-scripthash `get_history` params;
- subscription-first remains the efficient client pattern.

The PR makes the expensive parts cheaper, but it does not remove the need to
batch subscriptions, track status hashes, and fetch histories only when needed.

## Practical Rule

Do not repeatedly call `blockchain.scripthash.get_history` for every address on
every refresh.

Prefer:

1. batch subscribe all candidate scripthashes;
2. compare status hashes;
3. fetch history only for changed non-empty scripthashes;
4. deduplicate follow-up transaction/header/proof requests.

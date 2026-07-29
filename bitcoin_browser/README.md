# Bitcoin Browser Compatibility

This is a compatibility shim for databases that already have the old
`bitcoin_browser` module installed.

The real addon has been renamed to `bitcoin_explorer`. This module intentionally
contains no models, views, security rules, or data of its own; it only depends
on `bitcoin_explorer` so upgrading an existing `bitcoin_browser` installation
pulls in the renamed module.

New databases should install `bitcoin_explorer` directly.

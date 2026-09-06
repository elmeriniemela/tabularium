# Bitcoin Treasury

## Generate a PSBT

Open **Treasury → PSBTs** to review persistent drafts, or use
**Generate PSBT** on a wallet or wallet-address form to open a new full-screen
draft. The action is available even when its balance is zero.

Drafts are stored as regular Treasury records and remain available in the list
until deleted. They are private to the user who created them. The generated
binary and Base64 exports are cleared from the visible form whenever the
transaction details no longer match the last generated fingerprint; generate
the PSBT again after editing.

1. Add inputs with a wallet, receiving/change branch, address index, previous
   transaction ID, previous output index, and declared amount in BTC. Addresses
   are derived directly; refreshing the wallet or having transaction history
   is unnecessary. Unknown and spent outpoints are accepted.
2. Add destination outputs and BTC amounts:
   - **Address**: sends to a pasted mainnet address.
   - **Wallet**: derives an address from your wallet (e.g. for change).
   - **OP_RETURN**: creates an unspendable data carrier output with text (ASCII)
     or hexadecimal payload, defaulting to 0 sat.
3. Check the totals and fee. The fee is the difference between the declared
   input amounts and the output amounts. Outputs cannot exceed inputs.
4. Click **Generate PSBT**, then download `transaction.psbt` or copy Base64 for
   your external signer. Editing the transaction hides the previous export.

Amounts accept plain decimal BTC text with up to eight decimal places, with
exact satoshi conversion. Zero amounts and zero fees are allowed. The generator
does not apply dust policy, estimate fees, select coins, sign, or broadcast.

The wizard shows advisory warnings for:

- Declared fees of at least **0.001 BTC (100,000 sat)** or **1% of declared
  inputs**. These are review thresholds, not recommended fees or estimates of
  current network conditions.
- Zero fees and missing explicit change to an input wallet's change branch.
- Outputs below Bitcoin Core's dust threshold at a **3000 sat/kvB** policy
  baseline. Node policies vary; dust warnings do not block export.
- Duplicate destination scripts, including addresses pasted in different
  letter cases, and wallet outputs outside the configured address window.
- Non-zero amounts on **OP_RETURN** outputs, warning that funds are provably
  unspendable and permanently burned.
- **OP_RETURN** scripts exceeding the standard **83-byte** relay limit (80 bytes
  of data), or transactions declaring multiple **OP_RETURN** outputs.

Warnings update as rows change. They never require a balance or block
intentional PSBT experiments. Structural errors such as duplicate input
outpoints, invalid addresses, and outputs exceeding declared inputs still
prevent generation.

Use **Double-check before signing** to review the input txids (not wtxids),
zero-based output indexes, actual amounts, and source addresses. Verify every
destination, change amount, and fee on your signing device. The displayed fee
depends on manually declared input amounts; it has not been verified against
previous transactions. Extended public keys in the export can reveal other
wallet addresses, so share the file only with intended signers.

Inputs and wallet-derived outputs support native SegWit P2WPKH and P2WSH
multisig (up to 15 keys). Account keys need their **Master Key Fingerprint** and
complete **Derivation Path**, with a depth matching the exported extended key.
Master extended keys derive their own origin. All Treasury addresses use
mainnet; recipient addresses can use any supported mainnet address type.

The export contains PSBT v0, witness UTXOs, key derivations, account extended
keys, and multisig witness scripts. Transaction defaults are version 2,
locktime 0, opt-in RBF sequence 0xFFFFFFFD under BIP 125 (or final sequence
0xFFFFFFFF when RBF is unchecked), and SIGHASH_ALL. Some external signers additionally
require full previous transactions. Supplied input details must match actual
outputs for the signed transaction to be spendable.


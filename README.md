# btc-composition

Bitcoin <-> Ergo contract composition.
Composes the BTC relay/tx-check reference (sigmastate-interpreter #1182)
with the amount-binding tx parser (#1180) toward an rsBTC vault.

Stage ladder:
1. rsBTC vault core predicate
2. full OTC flow (deal-message + dual spend paths)
3. token-sale via OP_RETURN

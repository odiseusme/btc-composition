# BTC Relay/TxCheck Composition — Fixture Inventory (SCRATCH)

Status: WORKING DRAFT. Reshape to Shannon's harness format later.
Source: ross-weir/ergohack-sidechain (CC0).
Owner: odiseus (fixture side). Opened 2026-07-06.

---

## Fixture M1 — Merkle inclusion (from BitcoinMerkleProofSpec.scala)

End-to-end Merkle-inclusion fixture. Reference for how BtcTxCheck proves a tx
is included under a relay-verified header.

### Header (block containing the tx)
- Height: 93500
- Header ID (display order): 000000000003b8e6533b3f238ee00ff8dd68c3a2377a213f7a72c3ef0fe0c54b
- Relay stores header+height together: header_bytes ++ Longs.toByteArray(93500)
- Header hex (80B): 01000000076379e2c0ec4a614ad1bf0ec716e6873f2c7abac604a08cc78e070000000000579a6bbcd07e9c3d622672ad20495d4485b5233395ab4081db7cab0fd2b577d2396cec4c2a8b091b031a7313
- txHex: 0100000001eba8353ac2e5503f15548975108013246457ed83d331db760f0595b8bd7c54cb000000008c4930460221008c64f29882d9a59cbb070d75b4cdca56c04b523b0af37a0ffecee24e31cb2814022100b183ab317ad217f4a6f4e610c6138e5c2d7681d40f46201f268a5a90c1c07afa0141040b362c040204c13f6e1ec78b60978bdd76d851d4a1612cd9e82ead5177694f8f37fa4e8c78579876bbaf8a561772f320d3125f36cd1f1c5e9eb3f8bc08b626d2ffffffff0280e9fd97000000001976a914f0630fd41ff0722cf29de4db609f06a4c17fad2d88ac002a7515000000001976a9141dea9e37227b8d7a6296849fc76e00e8f5a6674e88ac00000000
- Shape: 1 input, 2 outputs, both P2PKH (76a914...88ac)
- txId = double-SHA256(txBytes), NATURAL (internal) byte order (== #1180 R4)
- Output value bytes (LE): out1 80e9fd9700000000 / out2 002a751500000000

### Merkle proof (subtle, valuable part)
Block has 3 sibling txids; tx of interest is #3:
- tx1   a7c2b4a2cc940f9f541905048fe8352bd158dab18d15221fab7ee2187bd3cb5e
- tx2   1d74396699ae0effcd67fd5d031b780ff56c336bfc5d2d015d21db687d732764
- tx3Id d8c9d6a13a7fb8236833b1e93d298f4626deeb78b2f1814aa9a779961c08ce39
Proof (2 levels), each element = [direction_flag_byte] +: sibling_hash:
- level 0: 1.toByte +: tx3Id.reverse
- level 1: 0.toByte +: hash(tx1.reverse ++ tx2.reverse)
Direction flag: 0 -> hash(elem ++ prev) (sibling left); 1 -> hash(prev ++ elem) (sibling right)
Root fold: merkleProof.fold(txId)(computeLevel)
NOTE: txids reversed when hashing (Bitcoin internal vs display order). Flag loudly for harness.

### Confirmation assumption
- Relay box R6 = height + 6 (min 6 confirmations)

### Context-variable ABI (how data reaches BtcTxCheck)
- var 1 = tx bytes
- var 2 = header id
- var 3 = AVL lookup proof (headerLookUpProof.bytes) — proves header in relay tree
- var 4 = Merkle proof array

### Two-box composition shape (KEY ARCHITECTURE FINDING)
- relayDataInput: box w/ btcRelayErgoTree, AVL header tree in R4, min-confs R6. Passed as DATA INPUT (read-only).
- txCheckInput: box w/ btcTxCheckErgoTree, the box being SPENT; reads relay via data input, validates inclusion.
- IMPLICATION: #1180 parser slots in as a THIRD validation on the spending box, alongside relay data-input + tx-check.
- BtcTxCheck consumes BtcRelay as a DATA INPUT, not by embedding.

### Harness-translation notes (why not mechanically portable)
- PlasmaMap (Lithos plasma-toolkit) for the AVL tree — NOT a sigmastate dep. Translate to native AvlTree helpers.
- ErgoProvingInterpreter / ErgoStateContext / UnsignedErgoTransaction (ergo-core) — circular dep, cannot import. Rewrite onto ErgoLikeContextTesting / testBox (#1180 stack).
- Reads src/test/resources/application.conf for chain settings — replace with sigmastate test context.

---

## Fixture M2+ — from BitcoinRelaySpec.scala (366 lines)
TODO: not yet read. Header-chain fixtures (mainnet 566092/566093 in relay.scala scratch). Next step.

## Negative cases to carry from #1180
TODO: wrong header, wrong Merkle proof, wrong tx bytes, wrong script hash, insufficient amount. Cross-ref #1180 adversarial tests.

---

## CORRECTIONS after reading #1182 (Shannon spec, 838 lines)
#1182 already embeds relay/tx-check fixtures in sigmastate-native form.
It IS the fixture reference now. Two M1 notes above are superseded:
- Relay register layout (from #1182 relayBox): R4=bestChain AVL, R5=allHeaders AVL, R6=tipHeight(Int), R7=tipId, R8=tipWork(BigInt).
  Confirmations are DERIVED: tipHeight(R6) - header height >= min-confs. Fixture default tipHeight = headerHeight + 6 encodes 6 confs.
- AVL: #1182 uses MutableAvl(..., AvlTreeFlags.InsertOnly) with lookupProof/insertProof — NOT PlasmaMap. The plasma->native translation is DONE.
- tx-check context ABI confirmed identical to M1: var1 txBytes, var2 headerId, var3 headerProof, var4 merkleProof.
- New in #1182 (not in M1): retarget fixture (anchorHeight 562464), best/fork append fixtures w/ cumulative work, 2 pinned golden calcs, 9-var relay ABI.

## PIVOT: remaining additive work is NOT more fixtures
#1182 covers relay/tx-check fixtures. Our additive value = (3) composition hand-off to #1180, and (4) rsBTC vault shape. Next.

---

## (3) Composition hand-off: #1182 BtcTxCheck -> #1180 parser (THE SEAM)
Shannon left explicit hooks in BtcTxCheck comments: amount/recipient parsing
is composed by the amount-binding parser; spending policy supplied by composer.
- BtcTxCheck proves 3 things: properRelay (dataInputs(0).tokens(0) == relay NFT),
  enoughConfs (relay R6 tipHeight - header height >= 6), properProof (Merkle
  fold from txId == header merkleRoot bytes slice(36,68)).
- SHARED ABI: both contracts read tx bytes from CONTEXT VAR 1 and compute
  txId = doubleSha256(txBytes). Same var, same bytes. One tx, two validations.
- KEY INSIGHT: composed vault DROPS #1180 R4 (pre-committed txid). Vault does
  not know txid in advance - knows recipient script + min sats. Authenticity
  comes from Merkle inclusion under relay-verified header instead.
- Composed predicate: properRelay && enoughConfs && properProof && anyOutputMatches
  (same-output script+amount binding + supply-bound check from #1180, unchanged).
- Composed registers: expected scriptPubKey hash + minSats(Long). Relay NFT id constant.
- Header layout: headerAndHeight = 80B header ++ 8B height; merkleRoot = slice(36,68);
  height = byteArrayToLong(slice(80,88)).
- Context vars for composed spend: 1 txBytes, 2 headerId, 3 headerProof (AVL
  lookup vs relay R4 bestChain), 4 merkleProof. Parser adds NO new vars.

## (4) rsBTC vault - smallest shape (sketch only, per Shannon point 4)
- Vault box guards rsBTC tokens. R4 = expected BTC scriptPubKey hash, R5 = minSats.
- Data input: relay box (identified by NFT). Spend supplies vars 1-4.
- Predicate = the composed predicate above. Nothing else in v1.
- Follow-up stages (already agreed in dev chat): full OTC = Schnorr deal-message
  + dual spend paths; then token-sale w/ OP_RETURN Ergo pubkey.

## M1 SCHEMA COMPLETION (derived + verified by computation, 2026-07-06)
- txid internal/hash order: 39ce081c9679a7a94a81f1b278ebde26468f293de9b1336823b87f3aa1d6c9d8
- txid display order:       d8c9d6a13a7fb8236833b1e93d298f4626deeb78b2f1814aa9a779961c08ce39
- Byte-order convention: contract/AVL/R4 use INTERNAL order; explorers show display (reversed).
- FINDING: display txid == fixture tx3Id. Block has 3 txs TOTAL; tx of interest IS tx3.
  Proof level 0 pairs the tx WITH ITSELF = Bitcoin odd-count duplication rule.
  M1 framing "3 siblings, interest #3" corrected. Fixture exercises the dup edge case (cf CVE-2012-2459).
- Expected Merkle root (internal, header 36..68): 579a6bbcd07e9c3d622672ad20495d4485b5233395ab4081db7cab0fd2b577d2
- Expected Merkle root (display): d277b5d20fab7cdb8140ab953323b585445d4920ad7226623d9c7ed0bc6b9a57
- Fold verified independently in python: computed root == header bytes. TRUE.
- out1: 2550000000 sats (25.5 BTC), P2PKH 76a914f0630fd41ff0722cf29de4db609f06a4c17fad2d88ac
  sha256(script) = 80fd876129a11dfd62f9e7c979a8f8775ec24d1d46d2b7b200bce57b9234e16f  (<- #1180 R5 form)
- out2: 360000000 sats (3.6 BTC), P2PKH 76a9141dea9e37227b8d7a6296849fc76e00e8f5a6674e88ac
  sha256(script) = 3cff11ce96d297d2af49a7650eac1a00791f392dabf928bb645da697e09217ea
- Negative cases this fixture supports: wrong header id, wrong Merkle proof, wrong tx bytes,
  insufficient confs, wrong script hash, minSats above out value (e.g. > 2550000000).

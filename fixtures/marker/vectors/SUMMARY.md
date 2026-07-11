# Marker fixture vectors — SUMMARY

**STATUS: PRE-FREEZE — DRAFT grammar, freeze gated on the lifecycle checkpoint. Do not treat as final.**

| case_id | family | grammar_verdict | reason_code | txid_display | label |
|---------|--------|-----------------|-------------|--------------|-------|
| N1 | N1 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | 03b8d863a912c77b5442238d54dcf8f490ab23e8bae2d0875a9dac39ceb1d652 | zero claimants (payment, no marker) |
| N10 | N10 | MALFORMED | VOUT_OUT_OF_RANGE | 7acd1712563caf1707f56281834dfef14a4f288c7520be03c509281be9a92683 | vout intended 1 encoded big-endian |
| N11a | N11 | MALFORMED | VOUT_OUT_OF_RANGE | 546deccac537c3230fd8c721433880f41c0bd527d7badcabeac479a3ca3676a2 | vout == outputCount |
| N11b | N11 | MALFORMED | VOUT_IS_MARKER | 712ef5d319f49f801e63ccd241126a1ec1c6798206b378d11ec64fecce05a175 | vout == markerOutputIndex |
| N11c | N11 | MALFORMED | VOUT_OUT_OF_RANGE | 34d9035bec558d2ca9ab89c7e1eb3c2931085be7363460c898de0e4d7c44ac9c | vout == 0xffffffff |
| N12 | N12 | MALFORMED | NONZERO_MARKER_VALUE | f496a07c58393f0e5d0c89923016d96e6337a192b5604d4c3b7d8bc6e45ff0ae | nonzero value on canonical marker |
| N13 | N13 | MALFORMED | PAYMENT_SCRIPT_MISMATCH | 8a9e3fb9493ca3345b62faa18da771fa55697f4457a3d25bc3131870db18f72b | named output fails; another output qualifies |
| N14a | N14 | MALFORMED | PAYMENT_AMOUNT_TOO_LOW | 5cb434d029bed45efc04f41e3e3e8abf54b3664e02a3da5121f8179ac1e7c008 | named output right script, amount too low |
| N14b | N14 | MALFORMED | PAYMENT_SCRIPT_MISMATCH | 4cd50fff60b2da760bee52d11cdccbec817d523e5f5918f7718f58992698136c | named output sufficient amount, wrong script |
| N15a | N15 | MALFORMED | MULTIPLE_CLAIMANTS | 967a9b6d97004d8a666d136b1f224ad3046d6b4a2cfac2b9ba3b15a2929b9f30 | second claimant at last of 300 outputs |
| N15b | N15 | VALID |  | 8cce80f202d9946345b53cfc4fc4a131176bba6577246b95d12680d91bcfc8c2 | one claimant, 300 outputs (at capacity) |
| N15c | N15 | VALID |  | 6d5241e98d1335fcddeeb0fd2e442edafa353d8ef75843d5fb781955fb95357a | one claimant, 301 outputs (over capacity) |
| N2a | N2 | MALFORMED | MULTIPLE_CLAIMANTS | 2d5fe7aa905f52f31262accc3386f9ea89c56adbb4cd7be94391859aa3a9ff65 | two canonical claimants, same vault_id |
| N2b | N2 | MALFORMED | MULTIPLE_CLAIMANTS | 654dddd8592bfe75708b16bd0bd9d16fc7b23e98d8a9390b16f756d392b58dfb | two canonical claimants, different vault_ids |
| N3a | N3 | MALFORMED | NONCANONICAL_MARKER | dc493de94184063234c86f20bc97a7b571583b2fda5fa47647887f30501a21f1 | wrong payload length 42 |
| N3b | N3 | MALFORMED | NONCANONICAL_MARKER | c4e85c95afdadc1f884ddc8e802067a2a4298e9943a538a5b56f2c75003e378d | wrong payload length 44 |
| N3c | N3 | MALFORMED | NONCANONICAL_MARKER | c60500d585f5a23f81d806b7d40e18c0527c97c88556aefeeb6f1b4ebe47bc25 | declared 43 but physically truncated |
| N3d | N3 | MALFORMED | NONCANONICAL_MARKER | 6cc19c86d3f79e4861b5f8d300bf56279a69c9305f1a79e3a52157d39c640b3d | declared 43 with a trailing byte |
| N3e | N3 | MALFORMED | NONCANONICAL_MARKER | 7f3e58098424bb01688e90c12ea77d6a57b530029e2d1d5523952115d90116e0 | declared 43 with a trailing second push |
| N4a | N4 | MALFORMED | NONCANONICAL_MARKER | c83c0efdad259a784511179cf01916cdb4740de25184c40d3cf509973f71e3ba | PUSHDATA1 encoding alone |
| N4b | N4 | MALFORMED | NONCANONICAL_MARKER | c4278e9bd92b353332a27544dcbaf83cf229479517ee3c8672747e3f9f74299f | PUSHDATA2 encoding alone |
| N4c | N4 | MALFORMED | NONCANONICAL_MARKER | 854ee5e251145c6e94d51306f7be70609675a49d8327014157b7449aa66dcc39 | PUSHDATA4 encoding alone |
| N4d | N4 | MALFORMED | MULTIPLE_CLAIMANTS | 468cb2e37500f843ba7984ef0eb031473504ba12d3a7da5ce9091b5f81bc9769 | canonical + PUSHDATA1 -> two claimants |
| N4e | N4 | MALFORMED | MULTIPLE_CLAIMANTS | f2322d5454679d4c5c16b681069593aa607e9312e0e7db8f3534289a107b4b88 | canonical + PUSHDATA2 -> two claimants |
| N4f | N4 | MALFORMED | MULTIPLE_CLAIMANTS | 9fa387a5a3f04efb0dea76d0ebe471b03e17aba9b0deef62609311c153291e36 | canonical + PUSHDATA4 -> two claimants |
| N5a | N5 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | e4302c2b5b03057470b6cfe464ed7fd110c85bfb375260be9b1fc9146652a479 | PUSHDATA1 declared 0 then magic (ignored) |
| N5b | N5 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | 99622df9b4c11024f958e8463d36d9d170328ca821758c4610d3acc6ad814cf2 | PUSHDATA1 declared 1 then magic (ignored) |
| N5c | N5 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | 68af64b7f58c05bfee181ede6ccc0c13a6064c464a03e6a3d2da58392bde2390 | PUSHDATA1 declared 2 then magic (ignored) |
| N5d | N5 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | dae3183fc657ba11a48f8c20ccacdb7a8b6d9eceafaa508a34cb499b938f2443 | PUSHDATA1 declared 3 then magic (ignored) |
| N5e | N5 | MALFORMED | NONCANONICAL_MARKER | 2ae4085933361c6e17782db1c63275656bab4ba67f1052b294dc1c7570f2adf4 | declared >=4 magic present, push beyond slice |
| N5f | N5 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | 2bd7ce223b431c8478e0438d113f8bbb1908c303ee9eb676a3e17e8d2be9319b | slice ends before four magic bytes (ignored) |
| N5g | N5 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | a83165af868b50f68861ecb1eeb9b1e7ad0a583ffcada0417fa7750cceff7d0c | incomplete PUSHDATA1 length prefix (ignored) |
| N5h | N5 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | edd04cef58c83bc045fcbfe51743703397a6ba5a93d80fed78c109999da502d3 | incomplete PUSHDATA2 length prefix (ignored) |
| N5i | N5 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | 5cee149635242781c1e405aa1992338be13edb814fce26ff5c6e8947731f0302 | incomplete PUSHDATA4 length prefix (ignored) |
| N5j | N5 | MALFORMED | NONCANONICAL_MARKER | 4add4e1e652582504981217c903ce1e7f7f52e9e1b9fd90238b2211640fb6bc3 | PUSHDATA4 length 0x80000004 with magic (claims) |
| N6a | N6 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | 127f650ad1d51bc200a140112bad6cd4b4776445b91a0aff224315846ceca16c | empty first push then magic second push |
| N6b | N6 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | fb2baa514bc4dda03ab1f9c13cc3fa8c0e3efd331af78184d056b82b94cf0c37 | unrelated first push then magic second push |
| N6c | N6 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | d6da9f7b2377a5e30e1dee83da15da37d4486ab11883a8abe2b1a73f2fa67c8a | magic embedded in P2WSH program |
| N6d | N6 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | b608eac06d8b2a3dd034832ac0e91edd603505185de7b112e120c13daf574dc8 | magic embedded in P2TR program |
| N6e | N6 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | 6d42fb561fc4b4d0bb14a7018affcafbca7acd6d7822698dbfd9609bc4c3b484 | script not starting 0x6a |
| N6f | N6 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | fe2b5ada3cade15a2d12d840f74139a2be5979e888687de328c594b6dbc099b9 | near-miss magic ERGW |
| N6g | N6 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | 860c86aed45115a26ad2510d05027bbe075c2d617ac6d192aac58082213766e9 | near-miss magic ERGU |
| N6h | N6 | NOT-A-SETTLEMENT | ZERO_CLAIMANTS | c0430c504026b6681b0f2c45783cd31d6c26c59932c23e28f81a197a664afab1 | near-miss magic ergv (lowercase) |
| N7 | N7 | MALFORMED | VERSION_MISMATCH | 02878505aab8ef53fac4913443c06f6210124edcdf3fef7f5bfdbfc1b77f391b | unknown version 0x02 |
| N8a | N8 | MALFORMED | ERGO_NETWORK_MISMATCH | f969edd47d5373114fbac4829faf391f7b3c3770b22416779ea9960e197c272f | ergo_net wrong (0x02 testnet) |
| N8b | N8 | MALFORMED | BITCOIN_NETWORK_MISMATCH | 9da9057c8f689df3191741addb0d44eec69587b6dd793af99c149592935da811 | btc_net wrong (0x02 Testnet4) |
| N8c | N8 | MALFORMED | ERGO_NETWORK_MISMATCH | 7d6743ac4891919575c94bb7ff38aadc40507ae12c63f2e661917d045d931a57 | ergo_net unlisted enum 0xff |
| N8d | N8 | MALFORMED | BITCOIN_NETWORK_MISMATCH | b694a2d3ce0c357ff8a66fa4d0365243fc3157f32081ca4ecd7cf7b3ebcde4be | btc_net unlisted enum 0xff |
| N9a | N9 | MALFORMED | VAULT_ID_MISMATCH | 64e3614fbb6e692906ec90c1d8d16618cf41024e1e0b0b8dccc5b54b97f5dc46 | vault_id = sha256(EXPECTED_VAULT_ID) |
| N9b | N9 | MALFORMED | VAULT_ID_MISMATCH | eb36a719d9fa6c2c14354fe34094954644af9a6bd8939024adbfd20de98e96fd | vault_id one-byte mismatch |
| N9c | N9 | MALFORMED | VAULT_ID_MISMATCH | 91728f456fa1a8f4f9a3437ce933f55bef77bdd49b9737d6896985a0b8b52302 | vault_id full byte reversal |
| P1a | P1 | VALID |  | 4284e39405aa9291c414a4d7f2530cc4c83fde96c447198957c1ce2df35843fd | canonical marker first, payment after |
| P1b | P1 | VALID |  | 518a634c1472ce9d7e654c315ad3ce6a950b69aa5c6a05aaa26b3d700c0ac2b9 | canonical marker middle, payment before |
| P1c | P1 | VALID |  | d4db1f0e27688bc9e50dbb2f833372baf97f7b1e9683743d1fc3f8a9b5e236fd | canonical marker last, payment before |
| P1d | P1 | VALID |  | 6bdfbbeb97abad5c47d4780d0b68a5c63b0f6f7446618585bd45fd2715753090 | canonical marker middle, payment after |
| P2a | P2 | VALID |  | bac90c127d4fece77a1ba47ca85224047b42ec47f8f682c4449835a615bf65f2 | unrelated OP_RETURN before canonical marker |
| P2b | P2 | VALID |  | 7e64250600e986ed1dd07f8bbfb6ecb44f657c7f81cd2740079ae0c9b94d90db | unrelated OP_RETURN after canonical marker |
| P3 | P3 | VALID |  | dd4bdc0bff00d20f2e0e9a64e2a436557bcf6a45f32d680c9ddca88be8a9306a | two qualifying payments, named vout is one |
| P4 | P4 | VALID |  | dc837f33fd180f1353d48daa3aa88db44550fc5d07a75981de0367aa4ff1e254 | vout == outputCount-1 (upper boundary) |
| P5 | P5 | VALID |  | 84d743257d7410529cc732a835689f6bbad507849cf0faa9c37a327ebfd99f0a | vout=1 encoded 01 00 00 00 (LE control) |
| P6 | P6 | VALID |  | ec6f2025b4e9ba1b883914c155a24339847dae15e4cc4085d17c4d9a4c752a1f | vout=256 (00 01 00 00), 257 outputs |

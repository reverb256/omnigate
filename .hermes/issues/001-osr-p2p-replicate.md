#1 OSR: Peer-to-Peer Omarchy Replication (Like Bitcoin Feature)

## Goal
Build the "Like Bitcoin" long tail: let one tuned Omarchy user share their setup
and another pull it over the LAN — no cloud, no login. QR handshake + local
peer-to-peer with b3sum verification.

## Scope
- New `replicate.py` module (Python stdlib + qrencode/inline QR)
- `omnigate share`  → generates QR (manifest hash + LAN IP:port + fingerprint),
                      starts HTTP server serving blobs + signed manifest
- `omnigate receive` → scan QR → mDNS discover peer → pull manifest →
                       b3sum verify every blob → txn.apply() (atomic)
- Reuse LocalSend discovery: UDP multicast 224.0.0.167:53317 + HTTP `/register`
- Reuse existing `txn.py` for atomic apply

## Constraints
- Never write to source machine except manifest server output dir
- Fingerprint self-discovery prevention (don't replicate to yourself)
- Protocol versioning in manifest (forward-compatible)

## Tests (8-10)
- manifest signing/verification
- QR encode/decode round-trip
- peer discovery via multicast
- receive + b3sum verify + txn apply path
- conflict: target already has the file
- interruption: resume token
- noop: identical manifest

## Acceptance
- `python3 replicate.py share` prints QR to stdout + serves on :5317
- `python3 replicate.py receive <qr-or-host:port>` pulls + verifies + applies
- 8/10 tests pass on zephyr

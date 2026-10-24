# Standing mandate example

`mandate.fx_primary.example.json` contains an unsigned example, never live authority. The `owner_signature_ref` is a placeholder and is refused by the actual loader.

The owner signing client must use `vati.risk.mandate.mandate_subject(mapping)` to produce the `mandate-v2:<SHA-256>` subject for act `mandate-admit`. The helper covers the complete effective policy, including optional defaults, normalized decimal values, account, venue, mode, instruments, strategies, every limit, profiles and lifetime. It does not sign anything. Only the owner's enrolled private key can issue the token; the public registry remains empty until genuinely provisioned.

The token validity must cover the standing policy lifetime. Changes require a newly signed content subject, even if ID and version are unchanged. Optional temperament still requires its separate `trading-temperament-admit` grant in addition to the standing grant. Identity-only historical tokens remain historical evidence and cannot authorize new orders. No server or migration manufactures a replacement signature.

Keep notes outside the JSON payload: unknown fields are refused. Loading and canonical hashing do not qualify a strategy, provider, account, native host or release.

# High-resolution master candidates

This directory is intentionally empty until a real candidate is staged.

A generated or commissioned high-resolution VAN image is **not** canonical merely because it is placed here.

Use:

```bash
van-character-forge-v3 master stage \
  --candidate visual-authority/character-forge/01-master-candidates/van_master_highres_v1.png \
  --receipt visual-authority/character-forge/01-master-candidates/van_master_highres_v1.receipt.yaml
```

Then review it against `HIGHRES_MASTER_SPEC.yaml` and record owner approval with an exact candidate SHA before promotion.

The approved output is copied to:

`visual-authority/character-forge/01-master-approved/van_master_highres.png`

No decomposition, vectorisation or rigging milestone may treat an unapproved candidate as visual authority.

## Exact derived reference

`van_canonical_reference_2x.png` is a 3072×2048 deterministic 2× Lanczos derivative of the canonical owner board.

It adds **no new identity detail** and is therefore safe as a pixel-faithful comparison/reference surface. Its exact provenance is in `van_canonical_reference_2x.receipt.json`.

It is not the final rigging master. A recreated high-detail master must still pass the owner-approval gate above.

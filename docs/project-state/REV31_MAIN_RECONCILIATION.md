# Rev 3.1 main reconciliation

The Rev 3.1 implementation branch was created from the unsquashed secure-ingress lineage rooted at `db0e988`, while `main` later squash-promoted certified source head `f357a0c` as `1d7b921b`.

Git tree identity was verified before reconciliation:

- certified source head `f357a0c` tree: `03cd85d8910db119314db4157d483ffaf92ff54d`
- promoted `main` commit `1d7b921b` tree: `03cd85d8910db119314db4157d483ffaf92ff54d`

They are byte-identical trees. The Rev 3.1 branch already contains the certified closure state plus its intentional owner-runtime changes. The reconciliation merge therefore preserves the Rev 3.1 tree and records current `main` as an additional parent; it does not resolve conflicts by dropping certified or Rev 3.1 content.

This file records the proof used for that history reconciliation. CI remains the next evidence gate after the merge ancestry is established.

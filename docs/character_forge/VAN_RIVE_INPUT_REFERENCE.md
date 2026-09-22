# VAN Rive Input Reference

Public inputs are fixed by `visual-authority/rive_contract.json` and mirrored by
`RiveBindingContract`. The nine inputs are `state`, `speaking`, `listening`,
`attention_x`, `attention_y`, `mouth_open`, `urgency`, `viseme`, and
`action_code`. The eight triggers are `point`, `ack`, `celebrate`, `warning`,
`wave`, `shrug`, `present`, and `panel`.

The validator requires exact names and exact Rive input types and rejects extras. A desired
new public input is a contract-revision request, not an authoring decision.

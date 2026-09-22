# VAN Layer Map — M1 Execution View

Required top-level semantic groups:

`hair, visor_frame, visor_lens, face, eye_l, eye_r, brow_l, brow_r, mouth_upper,
mouth_lower, mouth_inner, neck, jacket, underlayer, arm_l_upper, arm_l_fore, hand_l,
arm_r_upper, arm_r_fore, hand_r, orb_shell, orb_core`

Any additional top-level semantic group is prefixed `extra_`. No raster images, text/fonts,
external references or flattened whole-character path are admitted. Palette, geometry,
path budget and bounds are enforced by `tools/character_forge/svg_lint.py`.

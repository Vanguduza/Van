# VAN Visual Production System

Status: CANONICAL

## Pipeline

1. Identity lock (`VAN_CHARACTER_VISUAL_IDENTITY.md`)
2. Rive contract (`RIVE_CHARACTER_CONTRACT.md` / `rive_contract.json`)
3. Platform asset pack under `visual-authority/assets/`
4. Android binding contract tests vs authority JSON
5. Canvas fallback when `.riv` unavailable or fails to load
6. Device golden captures vs acceptance matrix

## Required assets

| Asset | Path |
|---|---|
| Canonical turnaround | `visual-authority/assets/turnaround.png` |
| Expression authority | `visual-authority/assets/expressions.png` |
| Gesture/action authority | `visual-authority/assets/gestures.png` |
| Android/Hermes presentation | `visual-authority/assets/presentation.png` |
| App icon | `visual-authority/assets/app_icon.png` |
| Adaptive icon foreground | `visual-authority/assets/adaptive_fg.png` |
| Monochrome icon | `visual-authority/assets/monochrome_icon.png` |
| Notification icon | `visual-authority/assets/notification_icon.png` |
| Compact avatar | `visual-authority/assets/compact_avatar.png` |
| Hermes profile avatar | `visual-authority/assets/hermes_avatar.png` |
| Onboarding hero | `visual-authority/assets/onboarding_hero.png` |
| Command Centre | `visual-authority/assets/command_centre.png` |
| Offline/degraded | `visual-authority/assets/offline_degraded.png` |
| Urgent/decision | `visual-authority/assets/urgent_decision.png` |
| Production Rive (when authored) | `visual-authority/rive/van_runtime.riv` |

Until artist `.riv` exists: enforce contract in runtime, ship Canvas fallback that remains recognizably canonical Van, document exact Rive authoring handoff.

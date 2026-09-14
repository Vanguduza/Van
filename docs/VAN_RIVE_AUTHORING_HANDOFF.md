# VAN Rive Authoring Handoff

Status: EXTERNAL AUTHORING GATE

## Deliverable

Single `.riv` file: `visual-authority/rive/van_runtime.riv`

- Artboard name: `Van`
- State machine: `VanRuntime`
- Inputs/triggers/state codes: exactly as `visual-authority/rive_contract.json`
- Identity: silver/white hair, cyan visor, medium-brown skin, blue eyes, technical jacket, cyan orb

## Acceptance

- All durable states render without frantic motion
- Compact avatar remains readable at overlay size
- Unknown action codes are unused (runtime rejects them)
- Dark hair / generic robot = automatic rejection

## Runtime until delivery

Android uses Canvas fallback driven by the same state/action enums. Tests bind Kotlin enums to `rive_contract.json`.

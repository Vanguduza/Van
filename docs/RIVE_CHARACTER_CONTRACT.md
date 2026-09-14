# Rive Character Contract

Status: CANONICAL WIRE PROTOCOL

Artboard: `Van`
State machine: `VanRuntime`

## Inputs (exact names — do not rename)

| Name | Type | Range / notes |
|---|---|---|
| `state` | number | Durable state code (see below) |
| `speaking` | boolean | TTS actively producing audio |
| `listening` | boolean | Microphone capture active |
| `attention_x` | number | -1.0 .. 1.0 |
| `attention_y` | number | -1.0 .. 1.0 |
| `mouth_open` | number | 0.0 .. 1.0 |
| `urgency` | number | 0.0 .. 1.0 |
| `viseme` | number | Viseme id; 0 = neutral |
| `action_code` | number | Finite action code; 0 = none |

## Triggers

`point`, `ack`, `celebrate`, `warning`, `wave`, `shrug`, `present`, `panel`

## Durable states

| Code | Name |
|---:|---|
| 0 | OFFLINE |
| 1 | CONNECTING |
| 2 | IDLE |
| 3 | ATTENTIVE |
| 4 | LISTENING |
| 5 | THINKING |
| 6 | SEARCHING |
| 7 | WORKING |
| 8 | DELEGATING |
| 9 | SPEAKING |
| 10 | WAITING |
| 11 | WAITING_FOR_OWNER |
| 12 | DEGRADED |
| 13 | WARNING |
| 14 | ERROR |
| 15 | SUCCESS |
| 16 | URGENT |
| 17 | SLEEPING |

## Finite actions

| Code | Name |
|---:|---|
| 1 | HELLO_WAVE |
| 2 | ACK_NOD |
| 3 | POINT_LEFT |
| 4 | POINT_RIGHT |
| 5 | POINT_UP |
| 6 | POINT_DOWN |
| 7 | POINT_TARGET |
| 8 | CELEBRATE |
| 9 | CAUTION |
| 10 | CONFIRM |
| 11 | SHRUG |
| 12 | PRESENT_CARD |
| 13 | OPEN_PANEL |
| 14 | CLOSE_PANEL |

Unknown `action_code` values **must be rejected** by the wire validator. Do not silently remap.

Machine-readable: `visual-authority/rive_contract.json`

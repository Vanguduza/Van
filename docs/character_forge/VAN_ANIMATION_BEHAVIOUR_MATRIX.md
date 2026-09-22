# VAN Animation Behaviour Matrix

The canonical state/action numeric mapping is `visual-authority/rive_contract.json`.
For all 18 durable states: entry <=300 ms, steady loop without an obvious period shorter than
6 s, exit, readable intent at 96 dp. For all 14 finite actions: 600–1800 ms with
anticipation, main pose and return.

Mandatory composition checks include WORKING+speaking, THINKING+speaking,
WAITING_FOR_OWNER+speaking, URGENT+speaking, LISTENING+attention sweep,
WORKING+POINT_TARGET, WAITING_FOR_OWNER+PRESENT_CARD, SUCCESS+CELEBRATE,
WARNING+CAUTION and DEGRADED+LISTENING. Speech uses mouth_open amplitude plus visemes 0–4.

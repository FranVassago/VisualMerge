First Commit

---

Simulation Documentation

Decision Priorities (evaluated in strict order)
1) Rule 1 — Exit box stackability A: if a line waiting at the exit has an A on top, it can pass.
2) Rule 2 — Saturation >= 85%: if a waiting line is saturated, it can pass.
3) Rule 3 — Any A in the evaluation segment: if a waiting line contains any A, it can pass.
4) Rule 4 — Weighted score: compute the weighted score per active line and allow only
   waiting lines that match the global maximum score. If none match, hold.
5) Tie-breaker — Fixed priority: Line 1 > Line 2 > Line 3.

System-wide gates (applied before Rule 1)
- waitingAtExit: lines with a stopped box at the exit scanner.
- activeLines: lines with at least one box in the evaluation segment.
- If any active line has an A, only waiting lines that also contain an A are eligible to pass.
  If no waiting line contains an A, the system holds for that cycle.

Factors used in calculations
- Stackability values: A=3, B=2, C=1.
- Saturation: boxes_in_evaluation / capacity (clamped to 100%).
- Weighted score: sum of stackability_value * position_weight, where boxes closer to the exit
  have higher weights (5,4,3,2,1...).

Recurring events and evaluation calls
- Tick loop (every 100ms):
  1) Induction: inject boxes based on cadence and capacity.
  2) Movement: advance boxes, apply blocking, update saturation.
  3) Decision: evaluate waiting lines against system-wide rules and release/stop.
  4) Render: update UI, metrics, logs, and scanner states.
  5) Completion check: stop the simulation when all sequences are processed.

# 0006 - Question N Of ~Total

## Status

Accepted

## Context

Branching means the remaining path may change based on future answers. The step label cannot promise an exact remaining count without simulating every branch.

## Decision

Display progress as `Question N of ~Total`, where `Total` is the count of questions in the survey (not the path the respondent will actually take).

The progress bar percent (`SurveyRunner.progress_percent`) is a separate, approximate heuristic:

- Baseline: `step / total * 100`, capped below 100 until no higher-order questions exist.
- When branching skips question orders (gap between current `step` and saved answer count), bias upward using answered count and a minimum floor (75% once at least one answer is saved) so the bar does not stall near 50% on long jumps.
- Detect cycles when rebuilding session paths; the bar uses the same navigation helpers as the wizard.

## Consequences

The UI stays honest about uncertainty in the label while the bar still moves forward on branch-skipping routes. The heuristic is documented here rather than implied to be linear order only.

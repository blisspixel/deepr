# Calibration

Extraction model: `gpt-5-mini`  
Methodology: v1.0  
Measured: 2026-06-13

Does the absorb extraction confidence mean what it says? This report is
measured from graded (confidence, grounded) pairs, not asserted.

## Summary

- Samples: 59
- Grounded rate: 98.3%
- Expected calibration error (ECE): 0.002 (lower is better; 0 = perfect)
- ECE after Platt scaling: 0.000
- Derived absorb threshold (>= 80% grounded): n/a
- Extraction precision / recall / F1 @ 0.6: 0.98 / 1.00 / 0.99

## Reliability curve

| Confidence bin | n | Mean predicted | Observed grounded |
|---|---|---|---|
| 0.90-1.00 | 59 | 0.98 | 0.98 |

## Notes

- no derived threshold: confidence does not positively track grounding in this sample
- Why it saturates (adversarial probe, 2026-06-14): an over-reach probe corpus
  (`tests/data/calibration-hard/`) was built with planted traps - retracted
  figures, refuted assumptions, unproven results, speculation. The extractor
  defused every one by attributing/qualifying rather than asserting (78/78 claims
  grounded; one hypothetical correctly down-weighted to 0.30). So the saturation
  reflects **extraction faithfulness, not a measurement gap** - the absorb
  extractor does not over-reach even on adversarial input. Conclusion: do not
  chase a calibration curve here; the trust story is carried by the continuity
  metrics (`deepr eval continuity`) and the absorb verdict transparency.

_Derived view: regenerate with `deepr eval calibrate`. If gold labels were
seeded by a strong-model pre-grade and spot-corrected, that bias is noted above._

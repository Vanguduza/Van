# Active document verification — Rev1.17

`verify_rev117.py` includes the experience-learning and model-hardening integration checks; it also validates the retained schema/graph/reference invariants. `verify_review_contracts.py`, `verify_experience_learning.py` and `verify_model_hardening.py` run their independent mutations and schema/cost checks. The generated plan is checked by `plan/render_plan.py --check`.

Current receipts: `evidence/rev117/final_checks/`. Historical checkers/results retain their revision-specific scope. The source probes are separately recorded and are not application acceptance. All 1,610 application contracts remain NOT_RUN, six economic experiment templates remain NOT_RUN and no model/provider inference was performed. Schema success never proves real authority, costs, model identity or profit.

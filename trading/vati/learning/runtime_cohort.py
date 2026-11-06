"""Execution provenance is independent of a policy's permission ceiling."""
from dataclasses import dataclass

from vati.learning.episodes import Environment

RESEARCH_COHORTS = frozenset({Environment.BACKTEST, Environment.REPLAY, Environment.COUNTERFACTUAL})


@dataclass(frozen=True)
class ExecutionCohort:
    kind: str
    environment: Environment

    def as_dict(self):
        return {'schema': 'vati.execution-cohort/1', 'kind': self.kind,
                'environment': self.environment.value}


def execution_cohort_for(adapter, mode, *, research_environment=None):
    from vati.execution.paper import PaperAdapter
    from vati.learning.scope import ENVIRONMENT_FOR_MODE
    ordinary = ENVIRONMENT_FOR_MODE[mode]
    simulated = isinstance(adapter, PaperAdapter)
    if research_environment is not None:
        research = Environment(research_environment)
        if not simulated or research not in RESEARCH_COHORTS:
            raise ValueError('research cohort requires a simulated execution adapter')
        return ExecutionCohort('SIMULATED_PAPER', research)
    if simulated:
        return ExecutionCohort('SIMULATED_PAPER', Environment.SHADOW if ordinary is Environment.SHADOW else Environment.DEMO)
    return ExecutionCohort('NATIVE_ADAPTER', ordinary)


def recorded_cohort(value, mode):
    """Validate a sealed native risk producer's recorded execution binding."""
    from vati.learning.scope import ENVIRONMENT_FOR_MODE
    if (not isinstance(value, dict) or set(value) != {'schema', 'kind', 'environment'}
        or value.get('schema') != 'vati.execution-cohort/1'):
        raise ValueError('malformed native execution cohort')
    environment = Environment(value['environment'])
    if value['kind'] == 'SIMULATED_PAPER':
        if environment not in RESEARCH_COHORTS | {Environment.DEMO, Environment.SHADOW}:
            raise ValueError('simulated execution cannot establish a live cohort')
    elif value['kind'] != 'NATIVE_ADAPTER' or environment is not ENVIRONMENT_FOR_MODE[mode]:
        raise ValueError('native execution cohort conflicts with its policy')
    return environment

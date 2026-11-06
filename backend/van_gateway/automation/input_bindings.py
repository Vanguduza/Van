"""Server artifact metadata remains in the grant digest, outside workflow data."""
ARTIFACT_PIN = "_automation_artifact_id"


def workflow_inputs(inputs: dict) -> dict:
    return {key: value for key, value in inputs.items() if key != ARTIFACT_PIN}

from van_gateway.command.resolver import ResolutionMode, TypedCommandResolver
from van_gateway.models import ActionClass


def test_notebook_note_resolves_to_registered_a3_action():
    resolved = TypedCommandResolver().resolve("Create a new note in NotebookLM named Dial Health")
    assert resolved.mode == ResolutionMode.EXACT_ACTION
    assert resolved.action_id == "google.notebook.note.create"
    assert resolved.canonical_action_class == ActionClass.A3
    # P4-CMD-001 — this used to assert {"title": "dial health"}. The resolver matched
    # against casefolded text, so the title the owner typed was extracted lowercased and
    # then *sealed* that way: the corruption was cryptographically bound to their command
    # and nothing downstream could recover it. The test encoded the defect.
    assert resolved.parameters == {"title": "Dial Health"}


def test_notebook_creation_is_not_confused_with_note_creation():
    resolved = TypedCommandResolver().resolve("Create a notebook in NotebookLM called Dial Health")
    assert resolved.mode == ResolutionMode.HERMES_INTERPRETATION_REQUIRED
    assert resolved.action_id is None


def test_trading_halt_inherits_a4_no_stale_replay_policy():
    resolved = TypedCommandResolver().resolve("Halt autonomous trading")
    assert resolved.action_id == "trading.halt"
    assert resolved.canonical_action_class == ActionClass.A4
    assert resolved.no_stale_replay is True
    assert resolved.max_age_seconds == 5


def test_research_only_request_resolves_but_composite_mutation_does_not():
    resolver = TypedCommandResolver()
    research = resolver.resolve("Research Android 17 background audio changes")
    assert research.action_id == "research.web.search"
    assert research.canonical_action_class == ActionClass.A2

    composite = resolver.resolve("Research Android 17 changes and update VAN")
    assert composite.mode == ResolutionMode.HERMES_INTERPRETATION_REQUIRED
    assert composite.action_id is None


def test_context_read_is_a1():
    resolved = TypedCommandResolver().resolve("What do you know about VAN?")
    assert resolved.action_id == "owner.context.read"
    assert resolved.canonical_action_class == ActionClass.A1
    assert resolved.parameters == {"topic": "VAN"}  # P4-CMD-001


def test_unknown_owner_language_is_not_guessed():
    resolved = TypedCommandResolver().resolve("Resume that thing from yesterday")
    assert resolved.mode == ResolutionMode.HERMES_INTERPRETATION_REQUIRED
    assert resolved.canonical_action_class is None


def test_gateway_only_raises_client_action_class():
    stronger = TypedCommandResolver.stronger_class
    assert stronger(ActionClass.A1, ActionClass.A4) == ActionClass.A4
    assert stronger(ActionClass.A4, ActionClass.A1) == ActionClass.A4
    assert stronger(ActionClass.A2, None) == ActionClass.A2


def test_notebook_enterprise_delete_resolves_to_a4_with_target_preserved():
    resolved = TypedCommandResolver().resolve(
        "Delete Gemini Notebook Enterprise notebook id Nb-CaseSensitive_123"
    )
    assert resolved.mode == ResolutionMode.EXACT_ACTION
    assert resolved.action_id == "google.notebook.enterprise.delete"
    assert resolved.canonical_action_class == ActionClass.A4
    assert resolved.no_stale_replay is True
    assert resolved.parameters == {"notebook_id": "Nb-CaseSensitive_123"}


def test_notebook_enterprise_source_delete_resolves_to_a4_with_all_targets():
    resolved = TypedCommandResolver().resolve(
        "Remove sources Src-A, projects/P/locations/L/notebooks/N/sources/Src-B "
        "from Gemini Notebook Enterprise notebook id Nb-1"
    )
    assert resolved.mode == ResolutionMode.EXACT_ACTION
    assert resolved.action_id == "google.notebook.enterprise.sources.delete"
    assert resolved.canonical_action_class == ActionClass.A4
    assert resolved.parameters == {
        "notebook_id": "Nb-1",
        "source_names": ["Src-A", "projects/P/locations/L/notebooks/N/sources/Src-B"],
    }
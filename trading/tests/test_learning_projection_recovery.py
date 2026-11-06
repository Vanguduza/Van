"""Cold-start parity, native source seals and duplicate evidence boundaries."""
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace
import subprocess
import sys
from pathlib import Path

import pytest

from vati.app.trade_lifecycle import AccountTradeLifecycle
from vati.cognition.attribution import DecisionQualityInputs, DecisionQualityLedger
from vati.core.events import EventKind, make_event
from vati.core.ledger import Ledger
from vati.execution.paper import PaperAdapter
from vati.execution.protection import ProtectionManager
from vati.learning.episodes import Environment, LessonStore, lesson_from_verdict


def lifecycle(ledger, eurusd):
    return AccountTradeLifecycle(ledger=ledger, adapter=PaperAdapter(), router=SimpleNamespace(),
        protection=ProtectionManager(), contracts={"EURUSD": eurusd}, engines_by_symbol={}, modelled_costs={})


def record_quality(quality, trade="one", now=1):
    return quality.record(DecisionQualityInputs(trade_intent_id=trade, strategy_id="test"),
        symbol="EURUSD", r_multiple=D("1"), now_ms=now)


def test_actual_account_constructor_restores_quality_reduction_without_double_count(tmp_path, eurusd):
    path = tmp_path/"account.sqlite3"
    live = lifecycle(Ledger(path), eurusd)
    for number in range(3):
        record_quality(live.decision_quality, str(number), number+1)
    before = live.decision_quality.health_multiplier("test")
    assert before < 1
    cold = lifecycle(Ledger(path), eurusd)
    assert cold.decision_quality.health_multiplier("test") == before
    assert len(cold.decision_quality.verdicts_for("test")) == 3
    count = cold.ledger.count()
    assert cold.decision_quality.restore_from_ledger(cold.ledger) == 0
    assert cold.ledger.count() == count


def test_quality_duplicate_is_not_another_independent_trade():
    ledger = Ledger()
    quality = DecisionQualityLedger(ledger=ledger)
    first = record_quality(quality)
    assert record_quality(quality).digest == first.digest
    assert ledger.count(EventKind.DECISION_QUADRANT) == 1
    with pytest.raises(ValueError, match="conflicting"):
        record_quality(quality, now=2)
    assert ledger.count(EventKind.DECISION_QUADRANT) == 1


def test_modified_or_non_native_quality_evidence_cannot_restore():
    original = Ledger()
    record_quality(DecisionQualityLedger(ledger=original))
    event = next(original.iter(EventKind.DECISION_QUADRANT))
    for producer, patch in [("model-output", {}), (event.producer, {"r_multiple": "900"})]:
        bad = Ledger()
        bad.append(make_event(event.kind, producer, {**event.payload, **patch}, event_time_ms=1,
            received_time_ms=1, correlation_id=event.correlation_id))
        replay = DecisionQualityLedger()
        assert replay.restore_from_ledger(bad) == 0
        assert replay.replay_rejections


def test_native_legacy_quality_record_retains_its_original_seal():
    quality = DecisionQualityLedger()
    new = record_quality(quality)
    old = replace(new, inputs={k:v for k,v in new.inputs.items() if k != "max_cost_ratio"}, version="decision-quadrant/5.1.0")
    ledger = Ledger()
    ledger.append(make_event(EventKind.DECISION_QUADRANT, "vati-decision-quality",
        old.body()|{"verdict_hash":old.digest}, event_time_ms=1, received_time_ms=1, correlation_id=old.trade_intent_id))
    restored = DecisionQualityLedger()
    assert restored.restore_from_ledger(ledger) == 1
    assert restored.get(old.trade_intent_id).body() == old.body()


def test_explicit_infinite_unmodelled_cost_keeps_its_conservative_quality_state():
    ledger = Ledger()
    source = DecisionQualityLedger(ledger=ledger)
    for index in range(3):
        source.record(DecisionQualityInputs(trade_intent_id=str(index), strategy_id="test",
            thesis_sealed=True, thesis_falsifiable=True, cost_ratio=D("Infinity")),
            symbol="EURUSD", r_multiple=D("1"), now_ms=index)
    restored = DecisionQualityLedger()
    assert restored.restore_from_ledger(ledger) == 3
    assert restored.health_multiplier("test") == source.health_multiplier("test") < 1


def lesson(quality=None):
    quality = quality or DecisionQualityLedger()
    verdict = record_quality(quality)
    return lesson_from_verdict(verdict, symbol="EURUSD", regime="NORMAL", session="LONDON",
        environment=Environment.BACKTEST, now_ms=1)


def test_lesson_replay_preserves_version_hash_and_explicit_environment():
    ledger = Ledger()
    current = LessonStore(ledger=ledger)
    old = replace(lesson(), lesson_version="trade-lesson/5.1.0", artifact_hash="").sealed()
    current.record(old)
    replay = LessonStore()
    assert replay.restore_from_ledger(ledger) == 1
    restored = replay.lessons_for("test")[0]
    assert restored.as_dict() == old.as_dict() and restored.artifact_hash == old.artifact_hash
    assert "BACKTEST" in replay.evidence_for("test")[0]
    assert "not causal proof" in replay.evidence_for("test")[0]
    assert replay.restore_from_ledger(ledger) == 0


def test_bad_lesson_hash_is_refused_before_persisting_or_indexing():
    ledger = Ledger()
    store = LessonStore(ledger=ledger)
    with pytest.raises(ValueError, match="seal"):
        store.record(replace(lesson(), artifact_hash="0"*64))
    assert ledger.count() == 0 and not store.lessons_for("test")


def test_edited_or_untyped_lesson_is_not_guessed_during_replay():
    original = LessonStore(ledger=Ledger())
    actual = original.record(lesson())
    for patch in ({"keep":["This proves profitable alpha"]}, {"environment":None}, {"lesson_version":"future/99"}):
        ledger = Ledger()
        ledger.append(make_event(EventKind.TRADE_LESSON, "vati-lessons", actual.as_dict()|{"artifact_hash":actual.artifact_hash}|patch,
            event_time_ms=1, received_time_ms=1, correlation_id=actual.strategy_id))
        replay = LessonStore()
        assert replay.restore_from_ledger(ledger) == 0
        assert replay.replay_rejections


@pytest.mark.parametrize("stage,expected", [("before_append", 0), ("after_append", 1)])
def test_actual_process_death_does_not_invent_or_lose_a_committed_lesson(tmp_path, stage, expected):
    database = tmp_path/"kill-window.sqlite3"
    script = '''
import os,sys
from decimal import Decimal
from vati.core.ledger import Ledger
from vati.cognition.attribution import DecisionQualityInputs,DecisionQualityLedger
from vati.learning.episodes import LessonStore,lesson_from_verdict,Environment
ledger=Ledger(sys.argv[1])
verdict=DecisionQualityLedger().record(DecisionQualityInputs(trade_intent_id='crash',strategy_id='test'),symbol='EURUSD',r_multiple=Decimal('1'),now_ms=1)
item=lesson_from_verdict(verdict,symbol='EURUSD',regime='NORMAL',session='LONDON',environment=Environment.BACKTEST,now_ms=1)
store=LessonStore(ledger=ledger)
if sys.argv[2]=='before_append':
    ledger.append=lambda event: os._exit(23)
else:
    store._remember=lambda item: os._exit(23)
store.record(item)
raise AssertionError('crash injection was not reached')
'''
    result = subprocess.run([sys.executable, "-c", script, str(database), stage],
        cwd=Path(__file__).resolve().parents[2], text=True, capture_output=True)
    assert result.returncode == 23, result.stdout+result.stderr
    ledger = Ledger(database)
    restored = LessonStore()
    assert restored.restore_from_ledger(ledger) == expected
    assert len(restored.lessons_for("test")) == expected
    assert ledger.count(EventKind.TRADE_LESSON) == expected

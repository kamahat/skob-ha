"""Tests de la machine d'états courrier — sans Home Assistant."""
import importlib.util
import pathlib
from datetime import datetime, timedelta, timezone

_spec = importlib.util.spec_from_file_location(
    "mail_logic",
    pathlib.Path(__file__).parent.parent / "custom_components/boks/mail_logic.py",
)
ml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ml)

T0 = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)


def t(s):
    return T0 + timedelta(seconds=s)


def kinds(evts):
    return [k for k, _ in evts]


def test_flap_open_close_deposits_once():
    m = ml.MailLogic()
    m.on_flap(False, t(0))
    assert m.on_flap(True, t(1)) == []
    assert kinds(m.on_flap(False, t(3))) == [ml.EVENT_DEPOSITED]
    assert m.on_flap(False, t(4)) == []  # pas de doublon


def test_unknown_states_emit_nothing():
    m = ml.MailLogic()
    assert m.on_flap(None, t(0)) == []
    assert m.on_flap(True, t(1)) == []   # None -> True : pas un front
    assert m.on_flap(False, t(2)) == []  # aucun front d'ouverture vu
    m.on_flap(True, t(3))
    m.on_flap(None, t(4))                # perte du capteur en plein cycle
    assert m.on_flap(False, t(5)) == []  # ne doit pas compter comme dépôt


def test_door_open_collects_without_check_by_default():
    m = ml.MailLogic()
    m.on_door(False, t(0))
    assert kinds(m.on_door(True, t(1))) == [ml.EVENT_COLLECTED]
    assert m.on_tick(t(999)) == []
    assert m.on_journal([], t(999)) == []


def test_ha_command_mode_legit_when_ha_opened_first():
    m = ml.MailLogic(ml.MODE_HA_COMMAND, 30)
    m.on_door(False, t(0))
    m.on_ha_open(t(5))
    m.on_door(True, t(8))
    assert m.on_tick(t(50)) == []


def test_ha_command_mode_ack_arrives_after_door():
    m = ml.MailLogic(ml.MODE_HA_COMMAND, 30)
    m.on_door(False, t(0))
    m.on_door(True, t(8))
    m.on_ha_open(t(12))  # l'accusé de la Boks arrive après la porte
    assert m.on_tick(t(50)) == []


def test_ha_command_mode_flags_unmatched_opening_once():
    m = ml.MailLogic(ml.MODE_HA_COMMAND, 30)
    m.on_door(False, t(0))
    m.on_door(True, t(10))
    assert m.on_tick(t(20)) == []  # fenêtre non écoulée
    assert kinds(m.on_tick(t(41))) == [ml.EVENT_UNAUTHORIZED]
    assert m.on_tick(t(80)) == []  # une seule fois


def test_journal_mode_matches_code_within_window():
    m = ml.MailLogic(ml.MODE_JOURNAL, 30)
    m.on_door(False, t(0))
    m.on_door(True, t(100))
    assert m.on_tick(t(500)) == []  # pas de verdict avant le drain
    assert m.on_journal([t(110)], t(600)) == []


def test_journal_mode_flags_opening_without_entry():
    m = ml.MailLogic(ml.MODE_JOURNAL, 30)
    m.on_door(False, t(0))
    m.on_door(True, t(100))
    out = m.on_journal([t(300)], t(600))  # une ouverture, mais loin de la porte
    assert out == [(ml.EVENT_UNAUTHORIZED, t(100))]
    assert m.on_journal([], t(700)) == []  # soldé


def test_journal_mode_counts_ha_open_as_legit():
    m = ml.MailLogic(ml.MODE_JOURNAL, 30)
    m.on_door(False, t(0))
    m.on_ha_open(t(95))
    m.on_door(True, t(100))
    assert m.on_journal([], t(600)) == []


def test_bad_mode_falls_back_to_off():
    assert ml.MailLogic("nimportequoi").mode == ml.MODE_OFF


def test_pending_is_capped():
    m = ml.MailLogic(ml.MODE_JOURNAL, 30)
    m.on_door(False, t(0))
    for i in range(1, 200):
        m.on_door(i % 2 == 1, t(i))
    assert len(m._pending) <= ml.MAX_PENDING

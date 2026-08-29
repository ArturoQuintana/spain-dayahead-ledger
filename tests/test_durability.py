"""Durability of the append-only audit trail: atomic/fsync'd writes, tolerance
+ quarantine of a torn trailing line (a crash mid-append), and a writer lock
that makes 'never run two writers' a mechanism, not a convention. Each test
simulates the crash/contention a real incident would produce."""
import json

import pytest

import talea.__main__ as cli
from talea import loop


# ---- append: fsync + self-repair of a torn tail ------------------------------

def test_append_writes_a_whole_line(tmp_path):
    f = tmp_path / "ledger.jsonl"
    loop._append(f, {"a": 1})
    loop._append(f, {"b": 2})
    assert [json.loads(x) for x in f.read_text().splitlines()] == [{"a": 1}, {"b": 2}]


def test_append_repairs_and_quarantines_a_torn_trailing_write(tmp_path):
    f = tmp_path / "ledger.jsonl"
    f.write_bytes(b'{"a": 1}\n{"b": 2')          # last write interrupted (no newline)
    loop._append(f, {"c": 3})
    # the torn record is gone from the ledger; the new one appended cleanly
    assert [json.loads(x) for x in f.read_text().splitlines()] == [{"a": 1}, {"c": 3}]
    # and the partial bytes are preserved for inspection, not dropped silently
    assert (tmp_path / "ledger.jsonl.corrupt").read_text().strip() == '{"b": 2'


def test_append_leaves_a_clean_file_untouched(tmp_path):
    f = tmp_path / "ledger.jsonl"
    f.write_bytes(b'{"a": 1}\n')                  # already newline-terminated
    loop._append(f, {"b": 2})
    assert not (tmp_path / "ledger.jsonl.corrupt").exists()
    assert [json.loads(x) for x in f.read_text().splitlines()] == [{"a": 1}, {"b": 2}]


# ---- load: tolerate torn tail, but never silent mid-file corruption ----------

def test_load_jsonl_tolerates_a_torn_trailing_line(tmp_path):
    f = tmp_path / "r.jsonl"
    f.write_bytes(b'{"a": 1}\n{"b": 2}\n{"torn"')   # crash before fsync of last line
    assert loop._load_jsonl(f) == [{"a": 1}, {"b": 2}]   # valid prefix, no raise


def test_load_jsonl_raises_on_midfile_corruption(tmp_path):
    f = tmp_path / "r.jsonl"
    f.write_bytes(b'{"a": 1}\nNOT JSON\n{"b": 2}\n')      # broken line in the middle
    with pytest.raises(json.JSONDecodeError):
        loop._load_jsonl(f)


# ---- prices: atomic rewrite --------------------------------------------------

def test_save_prices_is_atomic_and_roundtrips(tmp_path):
    f = tmp_path / "prices.json"
    prices = {"2026-08-13T00": 50.0, "2026-08-13T01": 55.0}
    loop.save_prices(prices, f)
    assert not (tmp_path / "prices.json.tmp").exists()    # temp replaced, not left
    assert loop.load_prices(f) == prices


# ---- writer lock -------------------------------------------------------------

def test_writer_lock_blocks_a_second_writer(tmp_path):
    lock = tmp_path / ".tick.lock"
    with loop.writer_lock(lock):
        with pytest.raises(loop.WriterLockError):
            with loop.writer_lock(lock):
                pass


def test_writer_lock_releases_for_the_next_writer(tmp_path):
    lock = tmp_path / ".tick.lock"
    with loop.writer_lock(lock):
        pass
    with loop.writer_lock(lock):     # re-acquire cleanly after release
        pass


def test_cmd_tick_refuses_when_the_lock_is_held(monkeypatch):
    def locked(_path):
        raise loop.WriterLockError("another writer holds .tick.lock")
    monkeypatch.setattr(cli, "writer_lock", locked)
    assert cli.cmd_tick() == 3            # ES path
    assert cli.cmd_tick("de") == 3        # a silent-market path

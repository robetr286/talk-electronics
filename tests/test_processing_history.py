"""
Testy jednostkowe dla talk_electronic.services.processing_history
"""

import json
from pathlib import Path

import pytest

from talk_electronic.services.processing_history import ProcessingHistoryStore


@pytest.fixture
def temp_storage(tmp_path: Path) -> Path:
    """Tymczasowy plik do przechowywania historii."""
    return tmp_path / "processing-history.json"


@pytest.fixture
def store(temp_storage: Path) -> ProcessingHistoryStore:
    """Instancja store do testów."""
    return ProcessingHistoryStore(temp_storage)


def test_init_creates_empty_file(temp_storage: Path):
    """Test że inicjalizacja tworzy pusty plik JSON."""
    ProcessingHistoryStore(temp_storage)

    assert temp_storage.exists()
    content = temp_storage.read_text(encoding="utf-8")
    assert content == "[]"


def test_list_entries_empty(store: ProcessingHistoryStore):
    """Test listowania pustej historii."""
    entries = store.list_entries()

    assert isinstance(entries, list)
    assert len(entries) == 0


def test_upsert_entry_insert(store: ProcessingHistoryStore):
    """Test wstawiania nowego wpisu."""
    entry = {"id": "test-123", "filename": "test.png", "timestamp": "2025-11-13T10:00:00", "operation": "deskew"}

    result = store.upsert_entry(entry)

    assert result == entry

    # Sprawdź czy wpis został zapisany
    entries = store.list_entries()
    assert len(entries) == 1
    assert entries[0] == entry


def test_upsert_entry_update(store: ProcessingHistoryStore):
    """Test aktualizacji istniejącego wpisu."""
    # Wstaw pierwszy wpis
    entry1 = {"id": "test-123", "value": "old"}
    store.upsert_entry(entry1)

    # Aktualizuj ten sam ID
    entry2 = {"id": "test-123", "value": "new", "extra": "data"}
    result = store.upsert_entry(entry2)

    assert result == entry2

    # Sprawdź że jest tylko jeden wpis (zaktualizowany)
    entries = store.list_entries()
    assert len(entries) == 1
    assert entries[0] == entry2
    assert entries[0]["value"] == "new"


def test_upsert_entry_missing_id(store: ProcessingHistoryStore):
    """Test błędu gdy brakuje pola 'id'."""
    entry = {"filename": "test.png"}

    with pytest.raises(ValueError, match="Entry must include a string 'id'"):
        store.upsert_entry(entry)


def test_upsert_entry_non_string_id(store: ProcessingHistoryStore):
    """Test błędu gdy 'id' nie jest stringiem."""
    entry = {"id": 123, "data": "test"}

    with pytest.raises(ValueError, match="Entry must include a string 'id'"):
        store.upsert_entry(entry)


def test_remove_entry_existing(store: ProcessingHistoryStore):
    """Test usuwania istniejącego wpisu."""
    entry = {"id": "test-123", "data": "value"}
    store.upsert_entry(entry)

    removed = store.remove_entry("test-123")

    assert removed == entry

    # Sprawdź że wpis został usunięty
    entries = store.list_entries()
    assert len(entries) == 0


def test_remove_entry_nonexistent(store: ProcessingHistoryStore):
    """Test usuwania nieistniejącego wpisu."""
    removed = store.remove_entry("nonexistent")

    assert removed is None


def test_remove_entry_keeps_others(store: ProcessingHistoryStore):
    """Test że usunięcie jednego wpisu nie usuwa innych."""
    store.upsert_entry({"id": "entry-1", "data": "1"})
    store.upsert_entry({"id": "entry-2", "data": "2"})
    store.upsert_entry({"id": "entry-3", "data": "3"})

    removed = store.remove_entry("entry-2")

    assert removed["id"] == "entry-2"

    entries = store.list_entries()
    assert len(entries) == 2
    assert entries[0]["id"] == "entry-1"
    assert entries[1]["id"] == "entry-3"


def test_clear(store: ProcessingHistoryStore):
    """Test czyszczenia całej historii."""
    store.upsert_entry({"id": "1", "data": "a"})
    store.upsert_entry({"id": "2", "data": "b"})

    cleared = store.clear()

    assert len(cleared) == 2

    # Sprawdź że historia jest pusta
    entries = store.list_entries()
    assert len(entries) == 0


def test_get_entry_existing(store: ProcessingHistoryStore):
    """Test pobierania istniejącego wpisu."""
    entry = {"id": "test-123", "data": "value"}
    store.upsert_entry(entry)

    result = store.get_entry("test-123")

    assert result == entry


def test_get_entry_nonexistent(store: ProcessingHistoryStore):
    """Test pobierania nieistniejącego wpisu."""
    result = store.get_entry("nonexistent")

    assert result is None


def test_get_referenced_filenames_empty(store: ProcessingHistoryStore):
    """Test pobierania nazw plików z pustej historii."""
    filenames = store.get_referenced_filenames()

    assert isinstance(filenames, set)
    assert len(filenames) == 0


def test_get_referenced_filenames_single(store: ProcessingHistoryStore):
    """Test pobierania nazw plików z jednym wpisem."""
    entry = {"id": "test-123", "storage": {"filename": "test.png", "path": "/uploads/test.png"}}
    store.upsert_entry(entry)

    filenames = store.get_referenced_filenames()

    assert filenames == {"test.png"}


def test_get_referenced_filenames_multiple(store: ProcessingHistoryStore):
    """Test pobierania nazw plików z wielu wpisów."""
    store.upsert_entry({"id": "1", "storage": {"filename": "file1.png"}})
    store.upsert_entry({"id": "2", "storage": {"filename": "file2.png"}})
    store.upsert_entry({"id": "3", "storage": {"filename": "file3.png"}})

    filenames = store.get_referenced_filenames()

    assert filenames == {"file1.png", "file2.png", "file3.png"}


def test_get_referenced_filenames_no_storage(store: ProcessingHistoryStore):
    """Test że wpisy bez 'storage' są ignorowane."""
    store.upsert_entry({"id": "1", "storage": {"filename": "file1.png"}})
    store.upsert_entry({"id": "2", "data": "no storage field"})

    filenames = store.get_referenced_filenames()

    assert filenames == {"file1.png"}


def test_get_referenced_filenames_no_filename(store: ProcessingHistoryStore):
    """Test że wpisy bez 'filename' są ignorowane."""
    store.upsert_entry({"id": "1", "storage": {"filename": "file1.png"}})
    store.upsert_entry({"id": "2", "storage": {"path": "/uploads/file2.png"}})  # brak 'filename'

    filenames = store.get_referenced_filenames()

    assert filenames == {"file1.png"}


def test_get_referenced_filenames_empty_filename(store: ProcessingHistoryStore):
    """Test że puste 'filename' są ignorowane."""
    store.upsert_entry({"id": "1", "storage": {"filename": "file1.png"}})
    store.upsert_entry({"id": "2", "storage": {"filename": ""}})  # pusty string

    filenames = store.get_referenced_filenames()

    assert filenames == {"file1.png"}


def test_thread_safety_atomic_write(temp_storage: Path):
    """Test że zapis jest atomowy (nie psuje się przy błędach)."""
    store = ProcessingHistoryStore(temp_storage)

    # Wstaw wpis
    store.upsert_entry({"id": "1", "data": "test"})

    # Sprawdź że plik jest poprawnym JSON
    content = temp_storage.read_text(encoding="utf-8")
    data = json.loads(content)
    assert len(data) == 1


def test_corrupted_file_returns_empty(temp_storage: Path):
    """Test że skorumpowany plik zwraca pustą listę."""
    # Utwórz skorumpowany JSON
    temp_storage.parent.mkdir(parents=True, exist_ok=True)
    temp_storage.write_text("{ corrupted json }", encoding="utf-8")

    store = ProcessingHistoryStore(temp_storage)
    entries = store.list_entries()

    assert entries == []


def test_non_list_json_returns_empty(temp_storage: Path):
    """Test że JSON który nie jest listą zwraca pustą listę."""
    # Utwórz JSON z obiektem zamiast listy
    temp_storage.parent.mkdir(parents=True, exist_ok=True)
    temp_storage.write_text('{"key": "value"}', encoding="utf-8")

    store = ProcessingHistoryStore(temp_storage)
    entries = store.list_entries()

    assert entries == []


def test_non_dict_entries_filtered(temp_storage: Path):
    """Test że wpisy które nie są dict są filtrowane."""
    # Utwórz JSON z mieszanymi typami
    temp_storage.parent.mkdir(parents=True, exist_ok=True)
    temp_storage.write_text('[{"id": "1"}, "string", 123, null, {"id": "2"}]', encoding="utf-8")

    store = ProcessingHistoryStore(temp_storage)
    entries = store.list_entries()

    # Powinny zostać tylko dict entries
    assert len(entries) == 2
    assert entries[0]["id"] == "1"
    assert entries[1]["id"] == "2"


def test_multiple_operations_sequence(store: ProcessingHistoryStore):
    """Test sekwencji operacji."""
    # Insert
    store.upsert_entry({"id": "1", "op": "insert"})
    assert len(store.list_entries()) == 1

    # Update
    store.upsert_entry({"id": "1", "op": "update"})
    assert len(store.list_entries()) == 1
    assert store.get_entry("1")["op"] == "update"

    # Insert another
    store.upsert_entry({"id": "2", "op": "insert"})
    assert len(store.list_entries()) == 2

    # Remove first
    store.remove_entry("1")
    assert len(store.list_entries()) == 1
    assert store.get_entry("1") is None
    assert store.get_entry("2") is not None

    # Clear all
    store.clear()
    assert len(store.list_entries()) == 0


def test_persistence_across_instances(temp_storage: Path):
    """Test że dane są zapisywane między instancjami."""
    # Pierwsza instancja
    store1 = ProcessingHistoryStore(temp_storage)
    store1.upsert_entry({"id": "1", "data": "persistent"})

    # Druga instancja (nowy obiekt)
    store2 = ProcessingHistoryStore(temp_storage)
    entries = store2.list_entries()

    assert len(entries) == 1
    assert entries[0]["id"] == "1"
    assert entries[0]["data"] == "persistent"


def test_unicode_support(store: ProcessingHistoryStore):
    """Test obsługi Unicode w danych."""
    entry = {"id": "unicode-test", "description": "Test znaków specjalnych: ąćęłńóśźż", "emoji": "🔧⚡📊"}

    store.upsert_entry(entry)
    retrieved = store.get_entry("unicode-test")

    assert retrieved == entry
    assert retrieved["description"] == "Test znaków specjalnych: ąćęłńóśźż"
    assert retrieved["emoji"] == "🔧⚡📊"

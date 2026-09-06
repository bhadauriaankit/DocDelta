from app.parsers.models import TableData
from app.table_diff import compare_tables


def _table(name: str, rows: list[list[str]]) -> TableData:
    return TableData(name=name, rows=rows)


def test_identical_tables_are_all_equal():
    rows = [["Name", "Salary"], ["Alice", "45000"], ["Bob", "50000"]]
    result = compare_tables([_table("Sheet1", rows)], [_table("Sheet1", rows)])

    assert len(result.tables) == 1
    table = result.tables[0]
    assert table.stats == {"added": 0, "removed": 0, "modified": 0, "equal": 3}
    assert all(r.type == "equal" for r in table.rows)


def test_detects_a_pure_row_addition():
    original = [["Name", "Salary"], ["Alice", "45000"]]
    modified = [["Name", "Salary"], ["Alice", "45000"], ["Bob", "50000"]]

    result = compare_tables([_table("Sheet1", original)], [_table("Sheet1", modified)])
    table = result.tables[0]

    assert table.stats["added"] == 1
    assert table.stats["equal"] == 2
    added_rows = [r for r in table.rows if r.type == "added"]
    assert added_rows[0].modified == ["Bob", "50000"]


def test_detects_a_pure_row_removal():
    original = [["Name", "Salary"], ["Alice", "45000"], ["Bob", "50000"]]
    modified = [["Name", "Salary"], ["Alice", "45000"]]

    result = compare_tables([_table("Sheet1", original)], [_table("Sheet1", modified)])
    table = result.tables[0]

    assert table.stats["removed"] == 1
    removed_rows = [r for r in table.rows if r.type == "removed"]
    assert removed_rows[0].original == ["Bob", "50000"]


def test_detects_a_modified_cell_within_a_row():
    original = [["Name", "Salary"], ["Alice", "45000"]]
    modified = [["Name", "Salary"], ["Alice", "52000"]]

    result = compare_tables([_table("Sheet1", original)], [_table("Sheet1", modified)])
    table = result.tables[0]

    assert table.stats["modified"] == 1
    modified_row = [r for r in table.rows if r.type == "modified"][0]
    assert len(modified_row.cell_changes) == 1
    change = modified_row.cell_changes[0]
    assert change.col == 1
    assert change.original == "45000"
    assert change.modified == "52000"


def test_row_of_different_width_does_not_crash():
    """A column added mid-row shifts everything after it — this
    shouldn't raise an IndexError, just report the shorter row's missing
    trailing cells as changes against empty string."""
    original = [["Alice", "45000"]]
    modified = [["Alice", "Engineering", "45000"]]

    result = compare_tables([_table("Sheet1", original)], [_table("Sheet1", modified)])
    table = result.tables[0]
    modified_row = [r for r in table.rows if r.type == "modified"][0]
    assert len(modified_row.cell_changes) >= 1  # doesn't matter exactly how many — just that it didn't crash


def test_added_and_removed_sheets_are_tracked_separately_from_row_diffs():
    original = [_table("Q1", [["a"]]), _table("Q2", [["b"]])]
    modified = [_table("Q1", [["a"]]), _table("Q3", [["c"]])]

    result = compare_tables(original, modified)

    assert result.removed_tables == ["Q2"]
    assert result.added_tables == ["Q3"]
    # Q1 unchanged, present in both — should still get a normal row-diff
    assert len(result.tables) == 1
    assert result.tables[0].name == "Q1"
    assert result.tables[0].stats["equal"] == 1


def test_completely_replaced_table_content():
    original = [["old data"]]
    modified = [["completely different"]]

    result = compare_tables([_table("Sheet1", original)], [_table("Sheet1", modified)])
    table = result.tables[0]
    # Single row on each side with no overlap — SequenceMatcher should
    # treat this as one "replace" block, which our code turns into a
    # single "modified" row (paired 1-to-1), not a remove+add pair.
    assert table.stats["modified"] == 1
    assert table.stats["added"] == 0
    assert table.stats["removed"] == 0


def test_empty_tables_produce_no_rows():
    result = compare_tables([_table("Sheet1", [])], [_table("Sheet1", [])])
    table = result.tables[0]
    assert table.rows == []
    assert table.stats == {"added": 0, "removed": 0, "modified": 0, "equal": 0}

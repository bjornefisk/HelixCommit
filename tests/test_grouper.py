from helixcommit.grouper import DEFAULT_ORDER, group_items
from helixcommit.models import ChangeItem


def make_item(title: str, change_type: str, pr_number: str | None = None) -> ChangeItem:
    metadata = {}
    if pr_number is not None:
        metadata["pr_number"] = pr_number
    return ChangeItem(
        title=title,
        type=change_type,
        scope=None,
        breaking=False,
        metadata=metadata,
        references={},
    )


def test_group_items_respects_order_and_sections():
    items = [
        make_item("Add OAuth login", "feat"),
        make_item("Fix crash on startup", "fix"),
        make_item("Update docs", "docs"),
    ]

    sections = group_items(items)

    titles_by_section = {
        section.title: [item.title for item in section.items] for section in sections
    }
    assert next(iter(titles_by_section)) == "Features"
    assert titles_by_section["Features"] == ["Add OAuth login"]
    assert titles_by_section["Fixes"] == ["Fix crash on startup"]
    assert titles_by_section["Documentation"] == ["Update docs"]


def test_dedupe_by_pr_number_keeps_first_occurrence():
    items = [
        make_item("Improve onboarding flow", "feat", "42"),
        make_item("Polish onboarding text", "docs", "42"),
    ]

    sections = group_items(items, dedupe_by="pr_number")
    all_titles = [item.title for section in sections for item in section.items]
    assert all_titles == ["Improve onboarding flow"]


def test_default_order_contains_breaking_first():
    assert DEFAULT_ORDER[0] == "breaking"

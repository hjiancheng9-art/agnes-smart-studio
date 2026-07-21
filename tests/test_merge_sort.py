"""Tests for merge_sort — RED phase: import should fail initially."""

from examples.merge_sort import merge_sort


class TestMergeSort:
    """O(n log n) merge sort test suite."""

    def test_empty_list(self):
        assert merge_sort([]) == []

    def test_single_element(self):
        assert merge_sort([42]) == [42]

    def test_two_elements(self):
        assert merge_sort([2, 1]) == [1, 2]

    def test_sorted_input(self):
        assert merge_sort([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]

    def test_reverse_sorted(self):
        assert merge_sort([5, 4, 3, 2, 1]) == [1, 2, 3, 4, 5]

    def test_duplicates(self):
        assert merge_sort([4, 2, 4, 1, 2]) == [1, 2, 2, 4, 4]

    def test_negative_numbers(self):
        assert merge_sort([0, -5, 3, -1, 2]) == [-5, -1, 0, 2, 3]

    def test_large_input(self):
        import random

        data = [random.randint(-1000, 1000) for _ in range(1000)]
        assert merge_sort(data) == sorted(data)

    def test_not_mutating_original(self):
        original = [3, 1, 2]
        result = merge_sort(original)
        assert result == [1, 2, 3]
        assert original == [3, 1, 2], "should not mutate input"

    def test_stability(self):
        """Verify stable sort: equal elements keep original order."""
        pairs = [(1, "a"), (2, "b"), (1, "c"), (2, "d")]
        sorted_pairs = merge_sort(pairs)  # type: ignore[type-var]
        assert sorted_pairs == [(1, "a"), (1, "c"), (2, "b"), (2, "d")]

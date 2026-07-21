"""Tests for merge_sort — O(n log n) stable sort."""

import pytest

from examples.sorting import merge_sort


class TestMergeSort:
    """Merge sort correctness and edge cases."""

    def test_empty_list(self):
        assert merge_sort([]) == []

    def test_single_element(self):
        assert merge_sort([42]) == [42]

    def test_two_elements_sorted(self):
        assert merge_sort([1, 2]) == [1, 2]

    def test_two_elements_unsorted(self):
        assert merge_sort([2, 1]) == [1, 2]

    def test_sorted_list(self):
        assert merge_sort([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]

    def test_reverse_sorted(self):
        assert merge_sort([5, 4, 3, 2, 1]) == [1, 2, 3, 4, 5]

    def test_duplicates(self):
        assert merge_sort([3, 1, 4, 1, 5, 9, 2, 6, 5, 3]) == [1, 1, 2, 3, 3, 4, 5, 5, 6, 9]

    def test_negative_numbers(self):
        assert merge_sort([0, -5, 3, -1, 2]) == [-5, -1, 0, 2, 3]

    def test_floats(self):
        assert merge_sort([3.14, 1.41, 2.71, 0.0]) == [0.0, 1.41, 2.71, 3.14]

    def test_strings(self):
        assert merge_sort(["banana", "apple", "cherry"]) == ["apple", "banana", "cherry"]

    def test_mixed_types_raises(self):
        with pytest.raises(TypeError):
            merge_sort([1, "a", 2])

    def test_key_function_length(self):
        result = merge_sort(["cat", "apple", "dog", "banana"], key=len)
        assert result == ["cat", "dog", "apple", "banana"]

    def test_key_function_abs(self):
        result = merge_sort([-3, 1, -2, 4], key=abs)
        assert result == [1, -2, -3, 4]

    def test_key_function_negate(self):
        result = merge_sort([1, 2, 3, 4, 5], key=lambda x: -x)
        assert result == [5, 4, 3, 2, 1]

    def test_reverse_default_ascending(self):
        assert merge_sort([3, 1, 2]) == [1, 2, 3]

    def test_reverse_descending(self):
        assert merge_sort([1, 2, 3], reverse=True) == [3, 2, 1]

    def test_reverse_with_key(self):
        result = merge_sort(["apple", "cat", "banana"], key=len, reverse=True)
        assert result == ["banana", "apple", "cat"]

    def test_stable_sort(self):
        pairs = [(1, "a"), (2, "b"), (1, "c"), (2, "d")]
        result = merge_sort(pairs, key=lambda x: x[0])
        assert result == [(1, "a"), (1, "c"), (2, "b"), (2, "d")]

    def test_does_not_mutate_input(self):
        original = [3, 1, 2]
        merge_sort(original)
        assert original == [3, 1, 2]

    def test_large_list_preserves_length(self):
        large = list(range(1000, 0, -1))
        result = merge_sort(large)
        assert len(result) == 1000
        assert result[0] == 1
        assert result[-1] == 1000

    def test_all_equal(self):
        assert merge_sort([7, 7, 7, 7]) == [7, 7, 7, 7]

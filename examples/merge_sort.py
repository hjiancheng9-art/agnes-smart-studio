"""Merge sort: O(n log n) stable sorting algorithm."""

from typing import TypeVar

T = TypeVar("T")


def merge_sort(arr: list[T]) -> list[T]:
    """Sort a list using merge sort (O(n log n) stable sort)."""
    if len(arr) <= 1:
        return arr

    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])

    return _merge(left, right)


def _merge(left: list[T], right: list[T]) -> list[T]:
    """Merge two sorted lists into one sorted list."""
    result: list[T] = []
    i = j = 0

    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1

    result.extend(left[i:])
    result.extend(right[j:])
    return result

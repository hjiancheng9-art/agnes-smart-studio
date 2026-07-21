"""Merge sort implementation — O(n log n) stable sort."""


def merge_sort(arr: list, key=None, reverse: bool = False) -> list:
    """Sort a list using merge sort (O(n log n) stable sort).

    Args:
        arr: Input list to sort.
        key: Optional function to extract comparison key from each element.
        reverse: If True, sort in descending order (default: ascending).

    Returns:
        A new sorted list (does not modify the input list).

    Examples:
        >>> merge_sort([3, 1, 4, 1, 5, 9, 2, 6])
        [1, 1, 2, 3, 4, 5, 6, 9]
        >>> merge_sort([3, 1, 4], reverse=True)
        [4, 3, 1]
        >>> merge_sort(["cat", "apple", "dog"], key=len)
        ['cat', 'dog', 'apple']
    """
    if len(arr) <= 1:
        return list(arr)

    mid = len(arr) // 2
    left = merge_sort(arr[:mid], key=key, reverse=reverse)
    right = merge_sort(arr[mid:], key=key, reverse=reverse)

    return _merge(left, right, key=key, reverse=reverse)


def _merge(left: list, right: list, key=None, reverse: bool = False) -> list:
    """Merge two sorted lists into one sorted list."""
    result = []
    i = j = 0

    # Pre-compute keys if a key function is provided.
    if key is not None:
        left_keys = [key(x) for x in left]
        right_keys = [key(x) for x in right]
    else:
        left_keys = left
        right_keys = right

    def _should_take_left(a_key, b_key) -> bool:
        return a_key >= b_key if reverse else a_key <= b_key

    while i < len(left) and j < len(right):
        if _should_take_left(left_keys[i], right_keys[j]):
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1

    # Append remaining elements.
    result.extend(left[i:])
    result.extend(right[j:])

    return result

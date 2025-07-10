def find_max(numbers):
    """Find maximum number in a list."""
    if not numbers:
        raise ValueError("List cannot be empty")
    return max(numbers)


def find_min(numbers):
    """Find minimum number in a list."""
    if not numbers:
        raise ValueError("List cannot be empty")
    return min(numbers)


def calculate_average(numbers):
    """Calculate average of numbers in a list."""
    if not numbers:
        raise ValueError("List cannot be empty")
    return sum(numbers) / len(numbers)


def remove_duplicates_list(items):
    """Remove duplicates from a list while preserving order."""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def sort_by_length(strings):
    """Sort strings by their length."""
    return sorted(strings, key=len)


def chunk_list(lst, chunk_size):
    """Split a list into chunks of specified size."""
    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive")
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]
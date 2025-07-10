def is_even(number):
    """
    Check if a number is even.

    Args:
        number (int): The number to check.

    Returns:
        bool: True if the number is even, False otherwise.
    """
    if number == 0:
        return True
    elif number % 2 == 0:
        return True
    else:
        return False

import pytest
from generated_code import *

def test_is_even():
    assert is_even(0) == True
    assert is_even(1) == False
    assert is_even(2) == True
    assert is_even(3) == False
    assert is_even(4) == True

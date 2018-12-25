import unittest
from starks.modp import IntegersModP
from starks.rationals_modp import RationalsModP

class TestModP(unittest.TestCase):
  """Basic tests for Mod-p numbers."""

  def test_construction(self):
    """Test that you can initialize a mod-p number."""
    mod7 = IntegersModP(7)

  def test_arithmetic(self):
    """Test Basic arithmetic."""
    mod7 = IntegersModP(7)
    # Check basic equality
    assert mod7(5) == mod7(5)
    assert mod7(5) == mod7(12)

    # Note this works since the @typecheck decorator silently casts the 1 to an IntegerModP 
    assert mod7(5) == 1 / mod7(3) # 3 * 5 = 15 == 1 mod 7
    assert mod7(1) == mod7(3) * mod7(5)
    # Check that the @typecheck decorator works correctly
    assert mod7(3) == mod7(3) * 1
    assert mod7(2) == mod7(5) + mod7(4)

    assert mod7(0) == mod7(3) + mod7(4)

  def test_large_modulus(self):
    """Runs basic tests in large modulus needed for starks."""
    modulus = 2**256 - 2**32 * 351 + 1
    modM = IntegersModP(modulus)
    assert modM(5) != modM(11)
    assert modM(2**32) != modM(2**64)
    assert modM(2**64) != modM(2**128)
    assert modM(2**256) == modM(2**32 * 351 - 1)

  def test_rationals_construction(self):
    """Test that rationals can be constructed."""
    modulus = 3
    ratmod3 = RationalsModP(modulus)
    rational = ratmod3(1, 2) # 1/2

  def test_rationals_arithmetic(self):
    """Test that rational arithmetic is sensible."""
    modulus = 11 
    ratmod = RationalsModP(modulus)
    assert ratmod(1, 2) * ratmod(1, 2) == ratmod(1, 4) 
    print("ratmod(3, 4) * ratmod(5, 6)")
    print(ratmod(3, 4) * ratmod(5, 6))
    assert ratmod(3, 4) * ratmod(5, 6) == ratmod(5, 8) 


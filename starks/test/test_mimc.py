import unittest
from starks.mimc_stark import mimc
from starks.mimc_stark import mk_proof
from starks.mimc_stark import verify_mimc_proof

class TestMiMC(unittest.TestCase):
  """
  Basic tests for MiMC and MiMC-stark implementation. 
  """

  def test_mimc(self):
    """
    Basic tests of MiMC.
    """
    inp = 5
    steps = 3
    round_constants = [2, 7]
    val = mimc(inp, steps, round_constants)

  def test_mimc_stark(self):
    """
    Basic tests of MiMC Stark generation
    """
    inp = 5
    LOGSTEPS = 9 
    steps = 2**LOGSTEPS
    # TODO(rbharath): Why do these constants make sense? Read
    # MiMC paper to see if justification.
    round_constants = [(i**7) ^ 42 for i in range(64)]
    modulus = 2**256 - 2**32 * 351 + 1
    # Factoring out computation
    def mimc_step(inp, i):
      return ((inp**3 + round_constants[i % len(round_constants)]) % modulus)

    def update_fn(f, value):
      """The step update function, in GF(2^n)"""
      return f.exp(value, 3)

    proof = mk_proof(inp, steps, round_constants, mimc_step, update_fn)
    assert isinstance(proof, list)
    assert len(proof) == 4
    (m_root, l_root, branches, fri_proof) = proof
    # TODO(rbharath): Add more tests on these components

  def test_mimc_stark_verification(self):
    """
    Basic tests of MiMC stark verification.
    """
    inp = 5
    LOGSTEPS = 9 
    steps = 2**LOGSTEPS
    round_constants = [(i**7) ^ 42 for i in range(64)]
    modulus = 2**256 - 2**32 * 351 + 1
    def mimc_step(inp, i):
      return ((inp**3 + round_constants[i % len(round_constants)]) % modulus)

    def update_fn(f, value):
      """The step update function, in GF(2^n)"""
      return f.exp(value, 3)
    proof = mk_proof(inp, steps, round_constants, mimc_step, update_fn)

    # The actual MiMC result
    output = mimc(inp, steps, round_constants)
    result = verify_mimc_proof(inp, steps, round_constants,
                               output, proof)
    assert result

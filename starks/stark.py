import time
import numpy as np
from starks.merkle_tree import merkelize, mk_branch, verify_branch, blake
from starks.compression import compress_fri, decompress_fri, compress_branches, decompress_branches, bin_length
from starks.poly_utils import PrimeField
from starks.fft import fft
from starks.fri import prove_low_degree, verify_low_degree_proof
from starks.utils import get_power_cycle, get_pseudorandom_indices, is_a_power_of_2

modulus = 2**256 - 2**32 * 351 + 1
f = PrimeField(modulus)
nonresidue = 7

# Number of bits of security in Merkle-tree check
spot_check_security_factor = 80
# TODO(rbharath): Is this the Galois extension degree?
# I think this is a security factor that gives us more control
# over the security level of the computation, but not sure.
#extension_factor = 8

def merkelize_polynomials(dims, polynomials):
  """Given a list of polynomial evaluations, merkelizes them together.

  Each dimension is merkelized seperately.

  Parameters
  ----------
  dims: Int
    Dimensionality
  polynomials: List
    Each element much be a list of evaluations of a given poly. All of
    these should have the same length.
  """
  mtrees = []
  for dim in range(dims):
    dim_mtree = merkelize([
        b''.join([val[dim].to_bytes(32, 'big') for val in evals])
        for evals in zip(*polynomials)])
    mtrees.append(dim_mtree)
  return mtrees

def get_computational_trace(inp, steps, constants, step_fn):
  """Get the computational trace for the STARK.

  Parameters
  ----------
  inp: Int
    The input for the computation
  """
  computational_trace = [inp]
  deg = len(constants)
  for i in range(steps - 1):
    poly_constants = [constants[d][i] for d in range(deg)]
    # TODO(rbharath): Is there off-by-one error on round_contants?
    next_state = step_fn(f, computational_trace[-1], poly_constants)
    if isinstance(next_state, int):
      next_state = [next_state]
    computational_trace.append(next_state)
  output = computational_trace[-1]
  print('Done generating computational trace')
  return computational_trace, output


class Computation(object):
  """A simple class defining a computation.
  
  Holds the state of the computation. Here are the various
  fields that constitue a computation.

  Fields
  ------
  inp: Int or List
    Either a single int or a list of integers of length dims
  steps: Int
    An int holding the number of steps of this computation.
  output: Int of List
    Either a single int or a list of integers of length dims
  constants: List
    A list of constants. Each element of constants must be a
    list of length steps
  step_fn: Function
    A function that maps a computation state to the next
    state. A state here is either an int of a list of ints of
    length dims.
  """
  def __init__(self, dims, inp, steps, constants, step_fn):
    self.dims = dims
    # Handle 1-d case
    if isinstance(inp, int):
      inp = [inp]
    self.inp = inp
    self.steps = steps
    self.constants = constants
    self.step_fn = step_fn
    self.computational_trace, self.output = get_computational_trace(inp,
        steps, constants, step_fn)

class StarkParams(object):
  """Holds the cryptographic parameters needed for STARK"""
  def __init__(self, comp, modulus, extension_factor):
    self.modulus = modulus
    self.extension_factor = extension_factor
    self.precision = comp.steps * extension_factor

    # Root of unity such that x^precision=1
    self.G2 = f.exp(7, (modulus - 1) // self.precision)

    # Root of unity such that x^steps=1
    self.G1 = f.exp(self.G2, extension_factor)

    # Powers of the higher-order root of unity
    self.xs = get_power_cycle(self.G2, modulus)
    self.last_step_position = self.xs[(comp.steps - 1) * extension_factor]

def construct_computation_polynomial(comp, params):
  """Constructs polynomial for the given computation."""
  # Interpolate the computational trace into a polynomial P,
  # with each step along a successive power of G1
  computational_trace_polynomial = fft(
      comp.computational_trace, params.modulus, params.G1,
      inv=True, dims=comp.dims)
  assert len(computational_trace_polynomial) == comp.steps
  p_evaluations = fft(computational_trace_polynomial,
      params.modulus, params.G2, dims=comp.dims)
  assert len(p_evaluations) == comp.steps*params.extension_factor
  print(
      'Converted computational steps into a polynomial and low-degree extended it'
  )
  return p_evaluations

def construct_constraint_polynomial(comp, params,
    p_evaluations):
  """Construct the constraint polynomial for the given tape.

  This function constructs a constraint polynomial for the
  given computational tape. For now, this function only works
  with MiMC.
  """
  deg = len(comp.constants)
  constants_extensions = []
  for d in range(deg):
    # The extra wrapping is some plumbing since the fft expects a sequence
    # of states, where a state is a list.
    deg_constants = [[constant] for constant in comp.constants[d]]
    skips2 = comp.steps // len(deg_constants)
    # Constants are a 1-d sequence
    constants_mini_polynomial = fft(
        deg_constants, modulus, f.exp(params.G1, skips2),
        inv=True, dims=1)
    constants_mini_extension = fft(constants_mini_polynomial,
        modulus, f.exp(params.G2, skips2), dims=1)
    assert len(constants_mini_extension) == params.precision // skips2
    constants_extensions.append(constants_mini_extension)
  assert len(constants_extensions) == deg
  for extension in constants_extensions:
    assert len(extension) == params.precision // skips2
  print(
      'Converted round constants into a polynomial and low-degree extended it')

  # Create the composed polynomial such that
  #### C(P(x), P(g1*x), K(x)) = P(g1*x) - P(x)**3 - K(x)
  # C(P(x), P(g1*x), K(x)) = P(g1*x) - step_fn(P(x), K(x))
  # here K(x) contains the constants.
  p_next_step_evals = [p_evaluations[(i + params.extension_factor) % params.precision] for i in range(params.precision)]
  # constants_extensions[d] selects constants for the degree d term
  # constants_extensions[d][i] selects the degree d term for i-th step
  # constants_extensions[d][i][0] unpacks the output of fft() which adds an extra list
  step_p_evals = [comp.step_fn(
    f, p_evaluations[i], [constants_extensions[d][i][0] for d in range(deg)]) for i in range(params.precision)]
  # Another wrapping/unwrapping operation
  if comp.dims == 1:
    step_p_evals = [[val] for val in step_p_evals]
  c_of_p_evals = [[p_next[dim] - step_p[dim] % params.modulus for dim in range(comp.dims)] for (p_next, step_p) in zip(p_next_step_evals, step_p_evals)]
  print('Computed C(P, K) polynomial')
  return c_of_p_evals

def construct_remainder_polynomial(comp, params, c_of_p_evaluations):
  """Computes the remainder polynomial for the STARK.
  
  Compute D(x) = C(P(x), P(g1*x), K(x)) / Z(x)
  Z(x) = (x^steps - 1) / (x - x_atlast_step)
  TODO(rbharath): I think this is supposed to equal 
  Z(x) = (x - 1)(x-2)...(x-(steps_1)). How are these equal?
  """
  z_num_evaluations = [
      params.xs[(i * comp.steps) % params.precision] - 1 for i in range(params.precision)
  ]
  z_num_inv = f.multi_inv(z_num_evaluations)
  # (x_i - x_{step-1}) list
  z_den_evaluations = [params.xs[i] - params.last_step_position for i in range(params.precision)]
  d_evaluations = [
      [int(cp[dim] * zd * zni % modulus) for dim in range(comp.dims)]
      for cp, zd, zni in zip(c_of_p_evaluations, z_den_evaluations, z_num_inv)
  ]
  print('Computed D polynomial')
  return d_evaluations

def construct_boundary_polynomial(comp, params, p_evaluations):
  """Polynomial encoding boundary constraints on tape.
  
  Compute interpolant of ((1, input), (x_atlast_step, output))
  """
  inp = comp.inp
  output = comp.output
  i_evaluations = []
  inv_z2_evaluations = []
  for dim in range(comp.dims):
    inp_dim = inp[dim]
    out_dim = output[dim]
    interpolant = f.lagrange_interp_2([1, params.last_step_position], [inp_dim, out_dim])
    i_evaluations_dim = [f.eval_poly_at(interpolant, x) for x in params.xs]
    zeropoly2 = f.mul_polys([-1, 1], [-params.last_step_position, 1])
    inv_z2_evaluations_dim = f.multi_inv([f.eval_poly_at(zeropoly2, x) for x in params.xs])
    # Append to list
    i_evaluations.append(i_evaluations_dim)
    inv_z2_evaluations.append(inv_z2_evaluations_dim)
  i_evaluations = [np.array([i_evaluations[dim][j] for dim in range(comp.dims)]) for j in range(params.precision)]
  inv_z2_evaluations = [np.array([inv_z2_evaluations[dim][j] for dim in range(comp.dims)]) for j in range(params.precision)]
  # B = (P - I) / Z2
  b_evaluations = [
      ((p - i) * invq) % modulus
      for p, i, invq in zip(p_evaluations, i_evaluations, inv_z2_evaluations)
      ]
  print('Computed B polynomial')
  return b_evaluations
  #interpolant = f.lagrange_interp_2([1, params.last_step_position], [comp.inp, comp.output])
  #i_evaluations = [f.eval_poly_at(interpolant, x) for x in params.xs]

  #zeropoly2 = f.mul_polys([-1, 1], [-params.last_step_position, 1])
  #inv_z2_evaluations = f.multi_inv([f.eval_poly_at(zeropoly2, x) for x in params.xs])

  ## B = (P - I) / Z2
  #b_evaluations = [
  #    ((p - i) * invq) % modulus
  #    for p, i, invq in zip(p_evaluations, i_evaluations, inv_z2_evaluations)
  #]
  #print('Computed B polynomial')
  #return b_evaluations


def compute_pseudorandom_linear_combination(comp, params, mtree, d_evaluations, p_evaluations, b_evaluations):
  """Computes a pseudorandom linear combination of polys

  A FRI proofs of low degree for a polynomial takes space.
  There are multiple polynomials (constraint, tape, reminder,
  degree) used in a STARK. This function combines these into a
  single polynomial so that only one FRI proofs needs to be
  generated for all of them. The chances of a collision are
  low.
  """
  # Based on the hashes of P, D and B, we select a random
  # linear combination of P * x^steps, P, B * x^steps, B and
  # D, and prove the low-degreeness of that, instead of
  # proving the low-degreeness of P, B and D separately
  k1 = int.from_bytes(blake(mtree[1] + b'\x01'), 'big')
  k2 = int.from_bytes(blake(mtree[1] + b'\x02'), 'big')
  k3 = int.from_bytes(blake(mtree[1] + b'\x03'), 'big')
  k4 = int.from_bytes(blake(mtree[1] + b'\x04'), 'big')

  # Compute the linear combination. We don't even both
  # calculating it in coefficient form; we just compute the
  # evaluations
  G2_to_the_steps = f.exp(params.G2, comp.steps)
  powers = [1]
  for i in range(1, params.precision):
    powers.append(powers[-1] * G2_to_the_steps % params.modulus)

  l_evaluations = []
  for dim in range(comp.dims):
    l_evaluations_dim = [(
      d_evaluations[i][dim] + p_evaluations[i][dim] * k1 +
      p_evaluations[i][dim] * k2 * powers[i] + b_evaluations[i][dim] * k3 +
      b_evaluations[i][dim] * powers[i] * k4) % modulus
                     for i in range(params.precision)]
    l_evaluations.append(l_evaluations_dim)

  print('Computed random linear combination')
  return l_evaluations

def compute_merkle_spot_checks(mtree, l_mtree, comp, params):
  """Computes pseudorandom spot checks of Merkle tree."""
  # Do some spot checks of the Merkle tree at pseudo-random
  # coordinates, excluding multiples of `extension_factor`
  branches = []
  samples = spot_check_security_factor
  positions = get_pseudorandom_indices(
      l_mtree[1], params.precision, samples, exclude_multiples_of=params.extension_factor)
  for pos in positions:
    branches.append(mk_branch(mtree, pos))
    branches.append(mk_branch(mtree, (pos + params.extension_factor) % params.precision))
    branches.append(mk_branch(l_mtree, pos))
  print('Computed %d spot checks' % samples)
  return branches


# NOTE(rbharath): If you run a deep learning model on a GPU,
# you can add a trace-log which can be exited from the GPU
# without much effort. This trace log can be passed along to
# the STARK prover off-line.

# TODO(rbharath): I think the general strategy is to create a
# "comptutational "trace" of the workload, then constract a
# polynomial constraint with necessary linkage. Easier for
# regular workloads. This is also called a "computation tape"

def mk_proof(inp, steps, constants, step_fn, constraint_degree=2, dims=1, extension_factor=8):
  """Generate a STARK for a MIMC calculation
  
  Parameters
  ----------
  constraint_degree: int
    The degree of the constraint being considered
  dims: int
    The dimension of the state space for the computation.
  """
  start_time = time.time()
  # Some constraints to make our job easier
  assert steps <= 2**32 // extension_factor
  # remove
  assert is_a_power_of_2(steps)
  for poly_constants in constants:
    assert len(poly_constants) <= steps

  comp = Computation(inp, steps, constants, step_fn)
  params = StarkParams(comp, modulus, extension_factor)
  p_evaluations = construct_computation_polynomial(
      comp, params, dims=dims)

  # Construct the constraint polynomial (represented as a list
  # of point evaluations)
  c_of_p_evaluations = construct_constraint_polynomial(
      comp, params, p_evaluations)

  d_evaluations = construct_remainder_polynomial(
      comp, params, c_of_p_evaluations, dims=dims)

  b_evaluations = construct_boundary_polynomial(
      comp, params, p_evaluations, dims=dims)

  # Compute their Merkle root
  mtree = merkelize([
      pval.to_bytes(32, 'big') + dval.to_bytes(32, 'big') + bval.to_bytes(
          32, 'big')
      for pval, dval, bval in zip(p_evaluations, d_evaluations, b_evaluations)
  ])
  print('Computed hash root')

  l_evaluations = compute_pseudorandom_linear_combination(
      comp, params, mtree, d_evaluations, p_evaluations,
      b_evaluations)
  l_mtree = merkelize(l_evaluations)

  branches = compute_merkle_spot_checks(mtree, l_mtree, comp, params)

  # Return the Merkle roots of P and D, the spot check Merkle
  # proofs, and low-degree proofs of P and D
  o = [
      mtree[1], l_mtree[1], branches,
      prove_low_degree(
          l_evaluations,
          params.G2,
          # TODO(rbharath): Why is this 2x?
          steps * constraint_degree,
          modulus,
          exclude_multiples_of=extension_factor)
  ]
  print("STARK computed in %.4f sec" % (time.time() - start_time))
  return o

def verify_proof_at_position(comp, params, proof, ks, i, pos, constants_polynomials):
  """Verifies merkle proof at given position in extended trace"""
  k1, k2, k3, k4 = ks
  m_root, l_root, branches, fri_proof = proof
  x = f.exp(params.G2, pos)
  # TODO(rbharath): Why does exponentiating to steps make
  # sense here?  I think this is to compute the pseudorandom
  # linear combination.
  x_to_the_steps = f.exp(x, comp.steps)
  # TODO(rbharath): Why do i*3, i*3+1, i*3+2 make sense?
  mbranch1 = verify_branch(m_root, pos, branches[i * 3])
  mbranch2 = verify_branch(m_root, (pos + params.extension_factor) % params.precision,
                            branches[i * 3 + 1])
  l_of_x = verify_branch(l_root, pos, branches[i * 3 + 2], output_as_int=True)

  p_of_x = int.from_bytes(mbranch1[:32], 'big')
  p_of_g1x = int.from_bytes(mbranch2[:32], 'big')
  d_of_x = int.from_bytes(mbranch1[32:64], 'big')
  b_of_x = int.from_bytes(mbranch1[64:], 'big')

  zvalue = f.div(f.exp(x, comp.steps) - 1, x - params.last_step_position)
  k_of_xs = []
  for constants_mini_polynomial in constants_polynomials:
    k_of_x = f.eval_poly_at(constants_mini_polynomial, x)
    k_of_xs.append(k_of_x)

  # Check transition constraints C(P(x)) = Z(x) * D(x)
  assert (p_of_g1x - comp.step_fn(f, p_of_x, k_of_xs) - zvalue * d_of_x) % modulus == 0

  # Check boundary constraints B(x) * Q(x) + I(x) = P(x)
  interpolant = f.lagrange_interp_2([1, params.last_step_position], [comp.inp, comp.output])
  zeropoly2 = f.mul_polys([-1, 1], [-params.last_step_position, 1])
  assert (p_of_x - b_of_x * f.eval_poly_at(zeropoly2, x) - f.eval_poly_at(
      interpolant, x)) % modulus == 0

  # Check correctness of the linear combination
  assert (l_of_x - d_of_x - k1 * p_of_x - k2 * p_of_x * x_to_the_steps -
          k3 * b_of_x - k4 * b_of_x * x_to_the_steps) % modulus == 0


def verify_proof(inp, steps, constants, output, proof, step_fn,
    constraint_degree=2, extension_factor=8):
  """Verifies a STARK
  
  Parameters
  ----------
  constraint_degree: int
    The degree of the constraint being considered
  """
  start_time = time.time()
  assert steps <= 2**32 // extension_factor
  m_root, l_root, branches, fri_proof = proof
  comp = Computation(inp, steps, constants, step_fn)
  params = StarkParams(comp, modulus, extension_factor)
  # ALl constants should be of same length so we check the first
  assert is_a_power_of_2(steps)
  assert len(constants[0]) <= steps

  # Gets the polynomial representing the constants

  deg = len(constants)
  constants_polynomials = []
  constants_extensions = []
  for d in range(deg):
    deg_constants = constants[d]
    constants_mini_polynomial = fft(
        deg_constants, modulus, f.exp(params.G2, params.extension_factor), inv=True)
    constants_mini_extension = fft(
        constants_mini_polynomial, modulus, params.G2)
    assert len(constants_mini_extension) == params.precision
    constants_polynomials.append(constants_mini_polynomial)
    constants_extensions.append(constants_mini_extension)

  # Verifies the low-degree proofs
  assert verify_low_degree_proof(
      l_root,
      params.G2,
      fri_proof,
      steps * constraint_degree,
      modulus,
      exclude_multiples_of=extension_factor)

  # Performs the spot checks
  k1 = int.from_bytes(blake(m_root + b'\x01'), 'big')
  k2 = int.from_bytes(blake(m_root + b'\x02'), 'big')
  k3 = int.from_bytes(blake(m_root + b'\x03'), 'big')
  k4 = int.from_bytes(blake(m_root + b'\x04'), 'big')
  ks = [k1, k2, k3, k4]
  samples = spot_check_security_factor
  positions = get_pseudorandom_indices(
      l_root, params.precision, samples,
      exclude_multiples_of=params.extension_factor)
  for i, pos in enumerate(positions):
    verify_proof_at_position(comp, params, proof, ks, i, pos, constants_polynomials)

  print('Verified %d consistency checks' % spot_check_security_factor)
  print('Verified STARK in %.4f sec' % (time.time() - start_time))
  return True

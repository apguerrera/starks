"""This file contains a number of polynomial utility functions."""
import random
import itertools
from typing import List
from typing import Dict
from typing import Tuple
from typing import Callable
#from primefac import factorint
from sympy.ntheory import factorint
from starks.polynomial import Poly
from starks.modp import IntegersModP
from starks.polynomial import polynomials_over
from starks.euclidean import gcd
from starks.numbertype import Field
from starks.numbertype import FieldElement
from starks.numbertype import MultiVarPoly 
from starks.multivariate_polynomial import multivariates_over
from starks.reedsolomon import AffineSpace
from starks.numbertype import Field
from starks.numbertype import Poly
from starks.numbertype import MultiVarPoly
from starks.numbertype import FieldElement

def make_multivar(poly: Poly, i: int, field: Field, width: int) -> MultiVarPoly:
  """Converts a univariate polynomial into multivariate.
 
  Suppose poly = x^2 + 3

  Suppose that width = 5, i = 2. Then returns

  x_2^2 + 3
  """
  polysOver = multivariates_over(field, width).factory
  pre = (0,) * i
  post = (0,) * (width - (i+1))
  index = pre + (1,) + post
  X_i = polysOver({index: field(1)})
  up_poly = 0
  for degree, coeff in enumerate(poly.coefficients):
    up_poly += coeff * X_i**degree
  return up_poly

def project_to_univariate(multivar_poly: MultiVarPoly, i: int, field: Field, width: int) -> Poly:
  """Projects a multivariate polynomial to a univariate polynomial over one var."""
  multivars = multivariates_over(field, width-1)
  multiVarsOver = multivars.factory
  polysOver = polynomials_over(multivars).factory
  X = polysOver([0, 1])
  out = 0 
  for (term, coeff) in multivar_poly:
    # Remove i-th variable 
    term_minus_i = term[:i] + term[i+1:]
    coeff = multiVarsOver({term_minus_i: coeff})
    out += polysOver([coeff]) * X**term[i]
  return out

def draw_random_interpolant(degree, xs, ys):
  """Constructs a random interpolating polynomial of <= specified degree."""
  # TODO(rbharath): Need to implement this correctly
  return 0

def construct_affine_vanishing_polynomial(field: Field, aff: AffineSpace) -> Poly:
  """Constructs a polynomial which vanishes over a given affine space."""
  # TODO(rbharath): Need to implement this correctly.
  aff_elts = [field(elt) for elt in aff]
  ##############################################
  # TODO(rbharath): This doesn't work for arbitrary finite fields! 
  # Ok the error here is that aff_elts are not being interpreted as finite field elements? How to fix?
  ##############################################
  return zpoly(field, aff_elts)

def construct_affine_vanishing_polynomial_Moore(field: Field, aff: AffineSpace) -> Poly:
  """Constructs a polynomial which vanishes over a given affine space."""
  # pick a basis a_1, ..., a_d for the space
  b = aff.basis
  #construct Moore matrix with d+1 colums, The Moore matrix has successive powers of the Frobenius automorphism applied to its columns
  Moore = []
  for i in range(len(b)):
    temp_l = []
    temp_l.append(b[i])
    for j in range(len(b)):
      # I consider 2 for the pow because of binary finite field, 
      temp_l.append(temp_l[0]**(2**(j+1)))
    Moore.append(temp_l)
  print(Moore)
  # compute Moore's nonzero kernel element by using gaussian elimination
  kernel = gauss(Moore, len(b), field)
  # testing the output of gaussian elimination (this part can be removed because of its overhead)
  for i in range(len(b)):
    temp = Moore[i][0] * kernel[0]
    for j in range(len(b)-1):
      temp = temp + Moore[i][j+1] * kernel[j+1]
    assert temp == Moore[i][len(b)]

  # constructing the polynomial where kernel is the vector of coefficients
  polysOver = polynomials_over(field).factory
  return polysOver(kernel)

def gauss(M, row, field):
  for i in range(row):
    # Search for maximum in this column
    maxEl = M[i][i]
    maxRow = i

    for k in range(i+1, row):
      if max(M[k][i], maxEl) == 1:
        maxEl = M[k][i]
        maxRow = k

    # Swap maximum row with current row (column by column)
    for k in range(i, row+1):
      tmp = M[maxRow][k]
      M[maxRow][k] = M[i][k]
      M[i][k] = tmp

    
    polysOver = polynomials_over(field).factory
    zero = polysOver([0])

    # Make all rows below this one 0 in current column
    for k in range(i+1, row):
      c = -M[k][i]/M[i][i]
      for j in range(i, row+1):
        if i == j:
          M[k][j] = 0
        else:
          M[k][j] = M[k][j] + c * M[i][j]

  # Solve equation Mx=b for an upper triangular matrix M
  x = [0 for i in range(row)]
  for i in range(row-1, -1, -1):
    x[i] = M[i][row]/M[i][i]
    for k in range(i-1, -1, -1):
      M[k][row] =  M[k][row] - M[k][i] * x[i]

  return x

# compute whether a is bigger than b or not where a and b both are polynomials
def max(a, b):
  aD = a.degree()
  bD = b.degree()
  if aD > bD:
    return 1
  elif bD > aD:
    return 0
  else:
    for i in range(aD+1):
      if a.coefficients[aD-i] is not b.coefficients[aD-i]:
        if str(a.coefficients[aD-i])[0] == "1":
          return 1
        else:
          return 0

  return 1

def is_irreducible(polynomial: Poly, p: int) -> bool:
  """is_irreducible: Polynomial, int -> bool

  Determine if the given monic polynomial with coefficients in Z/p is
  irreducible over Z/p where p is the given integer
  Algorithm 4.69 in the Handbook of Applied Cryptography
  """
  ZmodP = IntegersModP(p)
  if polynomial.ring is not ZmodP:
    raise TypeError("Given a polynomial that's not over %s, but instead %r" %
                    (ZmodP.__name__, polynomial.ring.__name__))

  poly = polynomials_over(ZmodP).factory
  x = poly([0, 1])
  power_term = x
  is_unit = lambda p: p.degree() == 0

  for _ in range(int(polynomial.degree() / 2)):
    power_term = power_term.powmod(p, polynomial)
    gcd_over_Zmodp = gcd(polynomial, power_term - x)
    if not is_unit(gcd_over_Zmodp):
      return False

  return True

def generate_irreducible_polynomial(modulus: int, degree: int) -> Poly:
  """ 
  Generate a random irreducible polynomial of a given degree over Z/p, where p
  is given by the integer 'modulus'. This algorithm is expected to terminate
  after 'degree' many irreducibility tests. By Chernoff bounds the probability
  it deviates from this by very much is exponentially small.
  """
  Zp = IntegersModP(modulus)
  Polynomial = polynomials_over(Zp)

  while True:
    coefficients = [Zp(random.randint(0, modulus - 1)) for _ in range(degree)]
    random_monic_polynomial = Polynomial(coefficients + [Zp(1)])

    if is_irreducible(random_monic_polynomial, modulus):
      return random_monic_polynomial

def generate_primitive_polynomial(modulus: int, degree: int) -> Poly:
  """Generates a primitive polynomial over Z/modulus.
  
  Follows algorithm 4.78 in the Handbook of Applied Cryptography
  (http://math.fau.edu/bkhadka/Syllabi/A%20handbook%20of%20applied%20cryptography.pdf).
  Generates a random irreducible polynomial and then checks if it's prime.
  
  """
  Zp = IntegersModP(modulus)
  Polynomial = polynomials_over(Zp)
  while True:
    irred_poly = generate_irreducible_polynomial(modulus, degree)
    if is_primitive(irred_poly, modulus, degree):
      return irred_poly

def is_monic(poly: Poly) -> bool:
  """Tests whether a polynomial is monic."""
  return poly.coefficients[-1] == 1

def is_primitive(irred_poly: Poly, modulus: int, degree: int) -> bool:
  """Returns true if given polynomial is primitve.
  
  Follows algorithm 4.78 in the Handbook of Applied Cryptography
  (http://math.fau.edu/bkhadka/Syllabi/A%20handbook%20of%20applied%20cryptography.pdf).
  """
  # All primitive polynomials are irreducible
  if not is_irreducible(irred_poly, modulus):
    return False
  # factorize p^m - 1
  prime_factors = factorint(modulus**degree - 1)
  # This is returned as dictionary with multiplicities. Turn into list
  prime_factors = [int(factor) for factor in prime_factors.keys()]
  Zp = IntegersModP(modulus)
  polysOver = polynomials_over(Zp)
  x = polysOver([0, 1])
  # This is 1 right?
  one = polysOver([1])
  for i, factor in enumerate(prime_factors):
    power = (modulus**degree - 1) // factor
    l_x = (x**power) % irred_poly
    if l_x == one:
      return False
  return True

def construct_multivariate_dirac_delta(field: Field, values: List[FieldElement], n:int) -> MultiVarPoly:
  """Constructs the multivariate dirac delta polynomial at 0.

  1_0(x) = \prod_{i=1}^n (1 - x_i^{q-1})

  This can be generalized into the the dirac polynomial at y as follows.

  1_y(x)\prod_{i=1}^n (1 - (x_i - y_i)^{q-1})
  """
  multi = multivariates_over(field, n).factory
  q = field.field_size
  base = field(1)
  for i, val in enumerate(values):
    # x_i_term = (0,...1,...0) with the 1 in the ith-term
    x_i_term = [0] * n
    x_i_term[i] = 1 
    term = multi({(0,)*n: -values[i], tuple(x_i_term): 1})
    term = field(1) - term**(q-1)
    base = base * term
  return base


def construct_multivariate_coefficients(field: Field, step_fn: Callable, n:int) -> Dict[Tuple[int, ...], FieldElement]:
  """Transforms a function over vector of finite fields into a polynomial.

  Every function f: F_q^n -> F_q is a polynomial if F is a finite field of size
  q. (See Lemma 7 of http://math.uga.edu/~pete/4400ChevalleyWarning.pdf). The
  key trick used in this transformation is the creation of a "dirac-delta"
  multivariate polynomial which is 1 iff all n of its inputs are 0.

  1_0(x) = \prod_{i=1}^n (1 - x_i^{q-1})

  Why does this make sense? For any non-zero element x in F_q, x^{q-1} = 1. How
  can we convert an aribtrary function using these dirac-delta polynomials?

  P_f(x) = \sum_{y \in F_q^n} f(y) \prod_{i=1}^n (1 - (x_i - y_i)^{q-1})

  The idea is that we construct the polynomial term-wise.
  """
  multi = multivariates_over(field, n).factory
  poly = multi(0)
  field_size = field.field_size
  # Finite field case
  if field.__name__[:2] == "F_":
    p = field.p
    m = field.m
  elif field.__name__[:2] == "Z/":
    p = field.p
    m = 1
  else:
    raise ValueError
  # Iterate over field indices
  field_indices = itertools.product(*[range(p) for _ in range(m)])
  for index in field_indices:
    index = [field(ind) for ind in list(index)]
    term = construct_multivariate_dirac_delta(field, index, n)
    poly += step_fn(index) * term
  return poly

def multi_inv(field, values):
  """Use one field inversion to invert many values simultaneously.
  
  TODO(rbharath): Find a reference for this algorithm.
  """
  partials = [field(1)]
  for val in values:
    if val == 0:
      mul_value = 1
    else:
      mul_value = val
    partials.append(partials[-1] * mul_value)
  assert len(partials) == len(values) + 1
  inv = 1 / partials[-1]
  outputs = [0] * len(values)
  for i in range(len(values), 0, -1):
    outputs[i - 1] = partials[i - 1] * inv if values[i - 1] else 0
    if values[i-1] != 0:
      inv = inv * values[i - 1]
  return outputs

def zpoly(field, roots):
  """Build a polynomial with the specified roots over the given field.
  
  TODO(rbharath): Find a reference for this implementation. 
  """
  polysOver = polynomials_over(field).factory
  root = [field(1)]
  for x in roots:
    root.insert(0, field(0))
    for j in range(len(root) - 1):
      root[j] -= root[j + 1] * x
  print("root")
  print(root)
  return polysOver(root)

def lagrange_interp(field: Field, xs: List[FieldElement], ys: List[FieldElement]):
  """
  Given p+1 y values and x values with no errors, recovers the original
  p+1 degree polynomial. Lagrange interpolation works roughly in the following way.

  1. Suppose you have a set of points, eg. x = [1, 2, 3], y = [2, 5, 10]
  2. For each x, generate a polynomial which equals its corresponding
     y coordinate at that point and 0 at all other points provided.
  3. Add these polynomials together.
  """
  # Generate master numerator polynomial, eg. (x - x1) * (x - x2) * ... * (x - xn)
  root = zpoly(field, xs)
  polysOver = polynomials_over(field).factory
  assert len(root) == len(ys) + 1
  # Generate per-value numerator polynomials, eg. for x=x2,
  # (x - x1) * (x - x3) * ... * (x - xn), by dividing the master
  # polynomial back by each x coordinate
  nums = [root / polysOver([-x, 1]) for x in xs]
  # Generate denominators by evaluating numerator polys at each x
  denoms = [nums[i](xs[i]) for i in range(len(xs))]
  #invdenoms = multi_inv(mod, denoms)
  invdenoms = multi_inv(field, denoms)
  # Generate output polynomial, which is the sum of the per-value numerator
  # polynomials rescaled to have the right y values
  b = [0 for y in ys]
  for i in range(len(xs)):
    yslice = ys[i] * invdenoms[i]
    num_coefficients = nums[i].coefficients
    for j in range(len(ys)):
      if num_coefficients[j] and ys[i]:
        b[j] += num_coefficients[j] * yslice
  return polysOver(b)

# Optimized version of the above restricted to deg-4 polynomials
def lagrange_interp_4(field, xs, ys):
  polysOver = polynomials_over(field).factory
  x01, x02, x03, x12, x13, x23 = \
      xs[0] * xs[1], xs[0] * xs[2], xs[0] * xs[3], xs[1] * xs[2], xs[1] * xs[3], xs[2] * xs[3]
  eq0 = polysOver([-x12 * xs[3], (x12 + x13 + x23), -xs[1] - xs[2] - xs[3], 1])
  eq1 = polysOver([-x02 * xs[3], (x02 + x03 + x23), -xs[0] - xs[2] - xs[3], 1])
  eq2 = polysOver([-x01 * xs[3], (x01 + x03 + x13), -xs[0] - xs[1] - xs[3], 1])
  eq3 = polysOver([-x01 * xs[2], (x01 + x02 + x12), -xs[0] - xs[1] - xs[2], 1])
  e0 = eq0(xs[0])
  e1 = eq1(xs[1])
  e2 = eq2(xs[2])
  e3 = eq3(xs[3])
  e01 = e0 * e1
  e23 = e2 * e3
  invall = 1 / (e01 * e23)
  inv_y0 = ys[0] * invall * e1 * e23 
  inv_y1 = ys[1] * invall * e0 * e23 
  inv_y2 = ys[2] * invall * e01 * e3
  inv_y3 = ys[3] * invall * e01 * e2
  return polysOver([
      (eq0.coefficients[i] * inv_y0 + eq1.coefficients[i] * inv_y1 + eq2.coefficients[i] * inv_y2 + eq3.coefficients[i] * inv_y3)
      for i in range(4)
  ])


# Optimized version of the above restricted to deg-2 polynomials
def lagrange_interp_2(field, xs, ys):
  polysOver = polynomials_over(field).factory
  if not isinstance(xs, list):
    xs = xs.coefficients
  if not isinstance(ys, list):
    ys = ys.coefficients
  eq0 = polysOver([-xs[1], 1])
  eq1 = polysOver([-xs[0], 1])
  e0 = eq0(xs[0])
  e1 = eq1(xs[1])
  invall = 1/(e0 * e1)
  inv_y0 = ys[0] * invall * e1
  inv_y1 = ys[1] * invall * e0
  return polysOver([(eq0.coefficients[i] * inv_y0 + eq1.coefficients[i] * inv_y1) for i in range(2)])

def multi_interp_4(field, xsets, ysets):
  """Optimized version of the above restricted to deg-4 polynomials"""
  polysOver = polynomials_over(field).factory
  data = []
  invtargets = []
  for xs, ys in zip(xsets, ysets):
    x01, x02, x03, x12, x13, x23 = \
        xs[0] * xs[1], xs[0] * xs[2], xs[0] * xs[3], xs[1] * xs[2], xs[1] * xs[3], xs[2] * xs[3]
    eq0 = polysOver([-x12 * xs[3], (x12 + x13 + x23), -xs[1] - xs[2] - xs[3], 1])
    eq1 = polysOver([-x02 * xs[3], (x02 + x03 + x23), -xs[0] - xs[2] - xs[3], 1])
    eq2 = polysOver([-x01 * xs[3], (x01 + x03 + x13), -xs[0] - xs[1] - xs[3], 1])
    eq3 = polysOver([-x01 * xs[2], (x01 + x02 + x12), -xs[0] - xs[1] - xs[2], 1])
    e0 = eq0(xs[0])
    e1 = eq1(xs[1])
    e2 = eq2(xs[2])
    e3 = eq3(xs[3])
    data.append([ys, eq0, eq1, eq2, eq3])
    invtargets.extend([e0, e1, e2, e3])
  invalls = multi_inv(field, invtargets)
  o = []
  for (i, (ys, eq0, eq1, eq2, eq3)) in enumerate(data):
    invallz = invalls[i * 4:i * 4 + 4]
    inv_y0 = ys[0] * invallz[0]
    inv_y1 = ys[1] * invallz[1]
    inv_y2 = ys[2] * invallz[2]
    inv_y3 = ys[3] * invallz[3]
    o.append(polysOver([(eq0.coefficients[i] * inv_y0 + eq1.coefficients[i] * inv_y1 + eq2.coefficients[i] * inv_y2 +
               eq3.coefficients[i] * inv_y3) for i in range(4)]))
  return o

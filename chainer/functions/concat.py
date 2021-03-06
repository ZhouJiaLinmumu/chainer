import numpy
from chainer import cuda, Function

_args = 'const float* x, float* y, int cdimx, int cdimy, int rdim, int coffset'
_preamble = '''
#define COPY(statement) \
    int l   = i / (rdim * cdimx);  \
    int c   = i / rdim % cdimx + coffset;  \
    int r   = i % rdim;  \
    int idx = r + rdim * (c + cdimy * l);  \
    statement;
'''

class Concat(Function):
    """Concatenate multiple tensors towards specified axis."""

    def __init__(self, axis=1):  # concat along the channel dimension by default
        self.axis = axis

    def forward_cpu(self, xs):
        return numpy.concatenate(xs, axis=self.axis),

    def forward_gpu(self, xs):
        # TODO(beam2d): Unify the process into a single kernel.
        shape = list(xs[0].shape)
        for x in xs[1:]:
            shape[self.axis] += x.shape[self.axis]
        self.shape = shape

        y = cuda.empty(shape, dtype=xs[0].dtype)
        self.cdimy = y.shape[self.axis]
        self.rdim  = numpy.prod(shape[self.axis + 1:])

        coffset = 0
        kernel  = cuda.elementwise(
            _args, 'COPY(y[idx] = x[i])', 'concat_fwd', preamble=_preamble)
        for x in xs:
            cdimx = x.shape[self.axis]
            kernel(x, y, cdimx, self.cdimy, self.rdim, coffset)
            coffset += cdimx

        return y,

    def backward_cpu(self, xs, gy):
        sizes = numpy.array([x.shape[self.axis] for x in xs[:-1]]).cumsum()
        return numpy.split(gy[0], sizes, axis=self.axis)

    def backward_gpu(self, xs, gy):
        gxs = tuple(cuda.empty_like(x) for x in xs)

        coffset = 0
        kernel  = cuda.elementwise(
            _args, 'COPY(x[i] = y[idx])', 'concat_bwd', preamble=_preamble)
        for gx in gxs:
            cdimx = gx.shape[self.axis]
            kernel(gx, gy[0], cdimx, self.cdimy, self.rdim, coffset)
            coffset += cdimx

        return gxs

def concat(xs, axis=1):
    """Concatenates given variables along an axis.

    Args:
        xs (tuple of Variables): Variables to be concatenated.
        axis (int): Axis that the input arrays are concatenated along.

    Returns:
        ~chainer.Variable: Output variable.

    """
    return Concat(axis=axis)(*xs)

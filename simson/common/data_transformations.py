import numpy as np


def broadcast_trailing_dimensions(array: np.ndarray, to_shape_of: np.ndarray) -> np.ndarray:
    """Broadcasts array to shape of to_shape_of, adding dimensions if necessary."""
    new_shape = array.shape + (1,) * (len(to_shape_of.shape) - len(array.shape))
    b_reshaped = np.reshape(array, new_shape)
    b_broadcast = np.broadcast_to(b_reshaped, to_shape_of.shape)
    return b_broadcast

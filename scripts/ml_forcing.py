"""Load weights and model of neural net and computes closure term for coarsed grain simulation"""

import unet
import numpy as np
from parameters import *
import tensorflow as tf
import xarray

model = unet.Unet(stacks,stack_width,filters_base,output_channels, **unet_kw)

checkpoint = tf.train.Checkpoint(net=model)
checkpoint.restore("checkpoints/unet-" + str(epochs-1))

# Call the model a first time to create variables. Once the variables are created, the checkpoint object
# will be able to associate the weights from the checkpoint file with the correct model variables.
model.call(np.zeros((1,1,Nx,Ny,output_channels)))

def array_of_tf_components(tf_tens):
    """Create object array of tensorflow packed tensor components."""
    # Collect components
    # Tensorflow shaped as (batch, *shape, channels)
    comps = ['xx', 'yy', 'xy']
    c = {comp: tf_tens[..., n] for n, comp in enumerate(comps)}
    c['yx'] = c['xy']
    # Build object array
    tens_array = np.array([[None, None],
                           [None, None]], dtype=object)
    for i, si in enumerate(['x', 'y']):
        for j, sj in enumerate(['x', 'y']):
            tens_array[i, j] = c[si+sj]
    return tens_array

def deviatoric_part(tens):
    """Compute deviatoric part of tensor."""
    tr_tens = np.trace(tens)
    tens_d = tens.copy()
    N = tens.shape[0]
    for i in range(N):
        tens_d[i, i] = tens[i, i] - tr_tens / N
    return tens_d
    
def update_forcing(ux,uy,domain):

    txx = domain.new_field(name='txx')
    tyy = domain.new_field(name='tyy')
    txy = tyx =  domain.new_field(name='txy')
    dx = domain.bases[0].Differentiate
    dy = domain.bases[1].Differentiate

    Sxx = dx(ux).evaluate()
    Syy = dy(uy).evaluate()
    Sxy = Syx = (0.5*(dx(uy) + dy(ux))).evaluate()
    S = [Sxx['g'],Syy['g'],Syx['g']]

    inputs = np.moveaxis(np.array(S), 0, -1)[None]

    tf_inputs = [tf.cast(inputs,datatype)]
    tf_outputs = model.call(tf_inputs)

    tau_pred = deviatoric_part(array_of_tf_components(tf_outputs))

    txx['g'] = tau_pred[0,0]
    txy['g'] = tau_pred[0,1]
    tyx['g'] = tau_pred[1,0]
    tyy['g'] = tau_pred[1,1]

    Fx_temp = (dx(txx) + dy(tyx)).evaluate()
    Fy_temp = (dx(txy) + dy(tyy)).evaluate()

    # Compute the laplacian of the velocity fields
    diss_ux_grid = (dx(dx(ux)) + dy(dy(ux))).evaluate()
    diss_uy_grid = (dx(dx(uy)) + dy(dy(uy))).evaluate()

    # Regularization for machine learning prediction
    correct_Fx = Fx_temp['g']*diss_ux_grid['g'] > 0
    correct_Fy = Fy_temp['g']*diss_uy_grid['g'] > 0
    
    Fx_temp['g'] *= correct_Fx
    Fy_temp['g'] *= correct_Fy
    
    return Fx_temp['g'], Fy_temp['g']



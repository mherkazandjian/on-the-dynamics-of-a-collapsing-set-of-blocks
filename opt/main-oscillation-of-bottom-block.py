import numpy as np
import math
import time
import os
import argparse
import scipy.io

start_time = time.time()

# optaining certain parametric arguments from an input file
def parse_args():
    parser = argparse.ArgumentParser(description='Process some integers and floats.')
    parser.add_argument('n', type=int, help='Number of blocks (integer)')
    parser.add_argument('k', type=float, help='Oscillations amplitude = k*block_width(float)')
    parser.add_argument('ang_frq', type=float, help='Angular velocity of oscillations (float)')
    parser.add_argument('mu_val', type=float, help='coefficient of friction (float)')
    parser.add_argument('n_oscillations', type=float, default = 5, help='Number of oscillations to simulate (float)')
    parser.add_argument('iters_per_oscillation', type=float, default = 35, help='Number of iterations per oscillations (float)')
    parser.add_argument('--output_path', '-o', type=str, help='Output path (optional)')

    args = parser.parse_args()

    return args.n, args.k, args.ang_frq, args.mu_val, args.n_oscillations, args.iters_per_oscillation, args.output_path

n, k, ang_frq, mu_val, n_oscillations, iters_per_oscillation, output_path = parse_args()

# ############################
# # the following 7 lines are for debugging purposes only.
# n = 6
# k = 1
# ang_frq = 01.5707
# mu_val = 0.3
# n_oscillations = 3
# iters_per_oscillation = 60
# output_path = "/Users/theresahonein/Desktop/blocks-duplicate-repo/original-on-the-dynamics-of-a-collapsing-set-of-blocks/outputs/debug"
# ############################

# Define failure to occur when any two consecutive blocks loose contact.
# If you would like to stop solving for the motion of the stack beyond the timestep
# when failure is detected, set the 'reduce_ntime_if_fail = 1'. Otherwise set
# 'reduce_ntime_if_fail = 0'.
# The solution is stopped by reducing ntime to the iteration when failure is detected.
reduce_ntime_if_fail = 1

# Specify the maximum duration in hours for one run
max_hours = 23

# Specify the maximum number of leaves beyond which the code will stop running
max_leaves = 4

# creating custom exceptions
class MaxNewtonIterAttainedError(Exception):
    """This exception is raised when the maximum number of Newton iterations is attained
      whilst the iterations have not yet converged and the solution was not yet obtained."""
    def __init__(self, message="This exception is raised when the maximum number of Newton iterations is attained."):
        self.message = message
        super().__init__(self.message)

class RhoInfInfiniteLoop(Exception):
    """This exception is raised when we have possibly entered in an infinite loop through updating rho_inf."""
    def __init__(self, message="This exception is raised when we have possibly entered in an infinite loop through updating rho_inf."):
        self.message = message
        super().__init__(self.message)

class MaxHoursAttained(Exception):
    """This exception is raised when the maximum number of run hours specified by the use is exceeded."""
    def __init__(self, message="This exception is raised when the maximum run time is exceeded."):
        self.message = message
        super().__init__(self.message)

class MaxLeavesAttained(Exception):
    """This exception is raised when the maximum number of run leaves specified by the use is exceeded."""
    def __init__(self, message="This exception is raised when the maximum number of leaves is exceeded."):
        self.message = message
        super().__init__(self.message)

class FailureDetected(Exception):
    """This exception is raised when failure is detected if user chose to end the program when failure is detected."""
    def __init__(self, message="This exception is raised when failure is detected if user chose it."):
        self.message = message
        super().__init__(self.message)

# f is an output file that logs failed runs
# it is saved in the directory containing the output file
directory_containing_output = os.path.dirname(output_path)
f = open(f"{directory_containing_output}/run_failures_log.txt",'a')

# g contains a sketch of the bifurcation map
g = open(f"{output_path}/bifurcation_map.txt",'w')

# nondimensionalization parameters
l_nd = 1                    # m, length nondimensionalization paramter
m_nd = 1                    # kg, mass nondimensionalization parameter
a_nd = 9.81                 # m/(s**2), acceleration nondimensionalization parameter
t_nd = np.sqrt(l_nd/a_nd)   # s, time nondimensionalization parameter

# quantites following this line are nondimensional

# the motion of the first block is prescribed (acts like a base plate)
ndof = 3*(n-1)              # total number of degress of freedom
gr = 9.81/a_nd              # gravitational acceleration

# block dimensions
m = np.ones(n)/m_nd         # block mass
w = 0.2*np.ones(n)/l_nd     # block width
w[0] = 1/l_nd               # bottom block width is increases
h = 0.4*np.ones(n) /l_nd    # block height
h[0] = 0.2/l_nd             # bottom block height is decreases
mu = mu_val*np.ones(n)      # friction coefficient, the same for all contact interfaces

# parameters of oscillation motion of bottom block
a = k*w[1]                  # amplitude

# simulation (time) parameters
# period of one oscillation in sec/cylcle
oscillation_period = 2*np.pi/ang_frq                    # time per oscillation
tf = n_oscillations*oscillation_period                  # final time, simulation duration
dtime = oscillation_period/iters_per_oscillation        # duration of iteration
ntime = math.ceil(n_oscillations*iters_per_oscillation) # number of iterations
ntime_init = ntime  # saving the initial number of iterations to be completed, ntime can change
t = np.linspace(0,tf,ntime)          # time array

# motion of bottom block (bb)
xbb = a*np.sin(ang_frq*t)
xbbdot = a*ang_frq*np.cos(ang_frq*t)
xbbddot = -a*(ang_frq**2)*np.sin(ang_frq*t)

g.write(f"Period of oscillation: {oscillation_period} time/cycle.\n")
g.write(f"Total duration of simulation: {tf}.\n\n")

# constraint count
ng = 0          # number of constraints at position level
ngamma = 0      # number of constraints at velocity level
nN = 2*(n-1)    # number of gap distance constraints
nF = n-1        # number of friction constraints
nX = 3*ndof+3*ng+3*ngamma+3*nN+2*nF     # total number of constraints with their derivative

# fixed basis vectors
Ex = np.array([1,0])
Ey = np.array([0,1])

# generalized alpha parameters
MAXITERn = 20
r = 0.3
rho_inf = 0.5
rho_infinity_initial = rho_inf
# eq. 72
alpha_m = (2*rho_inf-1)/(rho_inf+1)
alpha_f = rho_inf/(rho_inf+1)
gama = 0.5+alpha_f-alpha_m
beta = 0.25*(0.5+gama)**2

# coefficients of restitution
eN = 0                  # normal coefficient of restitution
eF = 0                  # friction coefficient of retitution

# mass matrix (constant)
M_diagonal = np.zeros(ndof)
for i in range(1,n):
    M_diagonal[(i-1)*3:i*3] = np.array([m[i], m[i], m[i]/12*(w[i]**2+h[i]**2)])
M = np.diag(M_diagonal.flatten())

# applied forces (weight)
force = np.zeros(ndof)
for i in range(1,n):
    force[(i-1)*3:i*3] = np.array([0,-m[i]*gr,0])

def save_arrays():
    global q_save, u_save, X_save, gNdot_save, gammaF_save, AV_save

    # save current arrays to file
    block0 = np.stack((xbb,h[0]/2*np.ones((ntime_init)),np.zeros((ntime_init))))
    block0_tiled = np.tile(block0,(np.shape(q_save)[0],1,1))
    q_save_total = np.concatenate((block0_tiled,q_save),axis=1)

    file_name = str(f'{output_path}/q.mat')
    scipy.io.savemat(file_name,dict(q=q_save_total))
    file_name_corners = str(f'{output_path}/corners.mat')
    scipy.io.savemat(file_name_corners,dict(corners=corners_save))

    np.save(f'{output_path}q_save.npy', q_save)
    np.save(f'{output_path}u_save.npy', u_save)
    np.save(f'{output_path}X_save.npy', X_save)
    np.save(f'{output_path}gNdot_save.npy', gNdot_save)
    np.save(f'{output_path}gammaF_save.npy', gammaF_save)
    np.save(f'{output_path}AV_save.npy', AV_save)

    return

def remove_last_line(file_path):
    # Read all lines from the file
    with open(file_path, 'r') as file:
        lines = file.readlines()

    # Rewrite the file without the last line
    with open(file_path, 'w') as file:
        file.writelines(lines[:-1])

def get_gN(q,u,a):
    """Calculate the normal contact constraint"""

    # saving position, velocity, and acceleration coordinates of stack (without the bottom block)
    q_copy = q
    u_copy = u
    a_copy = a

    # position, velocity, and acceleration coordinates of the bottom block
    qbb = np.array([xbb[iter],h[0]/2,0])
    ubb = np.array([xbbdot[iter],0,0])
    abb = np.array([xbbddot[iter],0,0])

    # combining the position, velocity, and acceleration coordinates of all the stack
    q = np.concatenate((qbb,q),axis=None)
    u = np.concatenate((ubb,u),axis=None)
    a = np.concatenate((abb,a),axis=None)

    # divide coordinates components
    x, y, theta = get_xyt(q)
    xdot, ydot, thetadot = get_xyt(u)
    xddot, yddot, thetaddot = get_xyt(a)

    # initializing the corotational vectors and their derivatives
    #ex = np.zeros((n,2))
    #ey = np.zeros((n,2))

    #exdot = np.zeros((n,2))
    #eydot = np.zeros((n,2))

    #exddot = np.zeros((n,2))
    #eyddot = np.zeros((n,2))

    # initializing the position, velocity, and acceleration vectors to the center of mass of each block
    #r = np.zeros((n,2))
    #v = np.zeros((n,2))
    #a = np.zeros((n,2))

    # initializing the position, velocity, and acceleration vectors to each of the 4 corners
    #ra = np.zeros((n,2))
    #rb = np.zeros((n,2))
    #rc = np.zeros((n,2))
    #rd = np.zeros((n,2))

    #va = np.zeros((n,2))
    #vb = np.zeros((n,2))
    #vc = np.zeros((n,2))
    #vd = np.zeros((n,2))

    #aa = np.zeros((n,2))
    #ab = np.zeros((n,2))
    #ac = np.zeros((n,2))
    #ad = np.zeros((n,2))

    ct = np.cos(theta)
    st = np.sin(theta)

    st_i_t_i_1 = np.zeros(len(theta))
    ct_i_t_i_1 = np.zeros(len(theta))

    # sin(A-B) = sin(A)cos(B) - cos(A)sin(B)
    # cos(A-B) = cos(A)cos(B) + sin(A)sin(B)
    st_i_t_i_1[1:] = st[1:]*ct[:-1] - ct[1:]*st[:-1]
    ct_i_t_i_1[1:] = ct[1:]*ct[:-1] + st[1:]*st[:-1]

    ex = np.column_stack((ct, st))
    ey = np.column_stack((-st, ct))

    _thetadot = thetadot[:, None]
    exdot = _thetadot * ey
    eydot = -_thetadot * ex

    _thetaddot = thetaddot[:, None]
    _thetadot_2 = (thetadot**2)[:, None]
    exddot =  _thetaddot * ey - _thetadot_2 * ex
    eyddot = -_thetaddot * ex - _thetadot_2 * ey

    r = np.column_stack((x, y))
    v = np.column_stack((xdot, ydot))
    a = np.column_stack((xddot, yddot))

    w_half = w[:,None]/2
    h_half = h[:,None]/2

    w_half_ex = w_half * ex
    h_half_ey = h_half * ey
    r_plus_w_half_ex = r + w_half_ex
    r_min_w_half_ex = r - w_half_ex
    ra = r_plus_w_half_ex + h_half_ey
    rb = r_min_w_half_ex  + h_half_ey
    rc = r_min_w_half_ex  - h_half_ey
    rd = r_plus_w_half_ex - h_half_ey

    w_half_exdot = w_half * exdot
    h_half_eydot = h_half * eydot
    v_plus_w_half_exdot = v + w_half_exdot
    v_min_w_half_exdot = v - w_half_exdot
    va = v_plus_w_half_exdot + h_half_eydot
    vb = v_min_w_half_exdot + h_half_eydot
    vc = v_min_w_half_exdot - h_half_eydot
    vd = v_plus_w_half_exdot - h_half_eydot

    w_half_exddot = w_half * exddot
    h_half_eyddot = h_half * eyddot
    a_plus_w_half_exddot = a + w_half_exddot
    a_min_w_half_exddot = a - w_half_exddot
    aa = a_plus_w_half_exddot + h_half_eyddot
    ab = a_min_w_half_exddot + h_half_eyddot
    ac = a_min_w_half_exddot - h_half_eyddot
    ad = a_plus_w_half_exddot - h_half_eyddot

    # intializing the gap distances and slip speeds measured from each
    # corner (4 per contact interface) and their derivatives and gradients
    gNa = np.zeros(n)
    gNb = np.zeros(n)
    gNc = np.zeros(n)
    gNd = np.zeros(n)

    dgNa_dq = np.zeros((n,3*n))
    dgNb_dq = np.zeros((n,3*n))
    dgNc_dq = np.zeros((n,3*n))
    dgNd_dq = np.zeros((n,3*n))

    gNa_dot = np.zeros(n)
    gNb_dot = np.zeros(n)
    gNc_dot = np.zeros(n)
    gNd_dot = np.zeros(n)

    gNa_ddot = np.zeros(n)
    gNb_ddot = np.zeros(n)
    gNc_ddot = np.zeros(n)
    gNd_ddot = np.zeros(n)

    gammaF_allcases = np.zeros((n,4))
    dgammaF_dq_allcases = np.zeros((n,4,3*n))
    gammaFdot_allcases = np.zeros((n,4))

    gN = np.zeros(nN)
    gNdot = np.zeros(nN)
    gNddot = np.zeros(nN)
    WN = np.zeros((nN,3*n))

    # an array to keep track of the gap distance selection at each contact interface
    corners = np.zeros(nN,dtype=np.int8)

    # Get indices for vectorized operations
    indices = np.arange(1, n)
    prev_indices = indices - 1

    rc_ra = rc[indices] - ra[prev_indices]
    rc_rb = rc[indices] - rb[prev_indices]
    rd_ra = rd[indices] - ra[prev_indices]

    vc_va = vc[indices] - va[prev_indices]
    vc_vb = vc[indices] - vb[prev_indices]
    vd_va = vd[indices] - va[prev_indices]

    ac_aa = ac[indices] - aa[prev_indices]
    vc_va = vc[indices] - va[prev_indices]
    rc_ra = rc[indices] - ra[prev_indices]
    ac_ab = ac[indices] - ab[prev_indices]
    vc_vb = vc[indices] - vb[prev_indices]
    rc_rb = rc[indices] - rb[prev_indices]
    ac_ab = ac[indices] - ab[prev_indices]
    vc_vb = vc[indices] - vb[prev_indices]
    rc_rb = rc[indices] - rb[prev_indices]
    ad_aa = ad[indices] - aa[prev_indices]
    vd_va = vd[indices] - va[prev_indices]
    rd_ra = rd[indices] - ra[prev_indices]
    va_vc_p = va[prev_indices] - vc[indices]
    va_vd_p = va[prev_indices] - vd[indices]
    vb_vc_p = vb[prev_indices] - vc[indices]
    aa_ac_p = aa[prev_indices] - ac[indices]
    vb_vc_p = vb[prev_indices] - vc[indices]
    ab_ac_p = ab[prev_indices] - ac[indices]
    aa_ad_p = aa[prev_indices] - ad[indices]

    # Compute gNa for all blocks at once using einsum
    #gNa[indices] = np.einsum('ij,ij->i', rc[indices] - ra[prev_indices], _ey)
    #gNb[indices] = np.einsum('ij,ij->i', rc[indices] - rb[prev_indices], _ey)
    #gNc[indices] = np.einsum('ij,ij->i', rc[indices] - rb[prev_indices], ey[prev_indices])
    #gNd[indices] = np.einsum('ij,ij->i', rd[indices] - ra[prev_indices], ey[prev_indices])

    _ey = ey[indices]
    _ey_p = ey[prev_indices]
    _eydot = eydot[indices]
    _eydot_p = eydot[prev_indices]
    _eyddot = eyddot[indices]
    _eyddot_p = eyddot[prev_indices]

    _ex = ex[indices]
    _ex_p = ex[prev_indices]
    _exdot = exdot[indices]
    _exdot_p = exdot[prev_indices]

    def dot_axis1(A, B):
        return np.einsum('ij,ij->i', A, B)
        #return np.sum(A * B, axis=1)

    gNa[indices] = dot_axis1(rc_ra, _ey)
    gNb[indices] = dot_axis1(rc_rb, _ey)
    gNc[indices] = dot_axis1(rc_rb, _ey_p)
    gNd[indices] = dot_axis1(rd_ra, _ey_p)

    gNa_dot[indices] = dot_axis1(vc_va, _ey) + dot_axis1(rc_ra, _eydot)
    gNb_dot[indices] = dot_axis1(vc_vb, _ey) + dot_axis1(rc_rb, _eydot)
    gNc_dot[indices] = dot_axis1(vc_vb, _ey_p) + dot_axis1(rc_rb, _eydot_p)
    gNd_dot[indices] = dot_axis1(vd_va, _ey_p) + dot_axis1(rd_ra, _eydot_p)

    gNa_ddot[indices] = dot_axis1(ac_aa, _ey) + 2 * dot_axis1(vc_va, _eydot) + dot_axis1(rc_ra, _eyddot)
    gNb_ddot[indices] = dot_axis1(ac_ab, _ey) + 2 * dot_axis1(vc_vb, _eydot) + dot_axis1(rc_rb, _eyddot)
    gNc_ddot[indices] = dot_axis1(ac_ab, _ey_p) + 2 * dot_axis1(vc_vb, _eydot_p) + dot_axis1(rc_rb, _eyddot_p)
    gNd_ddot[indices] = dot_axis1(ad_aa, _ey_p) + 2 * dot_axis1(vd_va, _eydot_p) + dot_axis1(rd_ra, _eyddot_p)

    #gammaF_allcases[indices, 0] = dot_axis1(va_vc_p, _ex)
    #gammaF_allcases[indices, 1] = dot_axis1(vb_vc_p, _ex)
    #gammaF_allcases[indices, 2] = dot_axis1(va_vc_p, _ex_p)
    #gammaF_allcases[indices, 3] = dot_axis1(va_vd_p, _ex_p)

    A_combined = np.stack([va_vc_p, vb_vc_p, va_vc_p, va_vd_p], axis=1)
    B_combined = np.stack([_ex, _ex, _ex_p, _ex_p], axis=1)
    gammaF_allcases[indices, :] = np.sum(A_combined * B_combined, axis=2)

    #gammaFdot_allcases[indices, 0] = dot_axis1(va_vc_p, _exdot) + dot_axis1(aa_ac_p, _ex)
    #gammaFdot_allcases[indices, 1] = dot_axis1(vb_vc_p, _exdot) + dot_axis1(ab_ac_p, _ex)
    #gammaFdot_allcases[indices, 2] = dot_axis1(va_vc_p, _exdot_p) + dot_axis1(aa_ac_p, _ex_p)
    #gammaFdot_allcases[indices, 3] = dot_axis1(va_vd_p, _exdot_p) + dot_axis1(aa_ad_p, _ex_p)

    # Stack the arrays for combined computation
    A1_combined = np.stack([va_vc_p, vb_vc_p, va_vc_p, va_vd_p], axis=1)  # Shape: (n, 4, m)
    B1_combined = np.stack([_exdot, _exdot, _exdot_p, _exdot_p], axis=1)   # Shape: (n, 4, m)
    A2_combined = np.stack([aa_ac_p, ab_ac_p, aa_ac_p, aa_ad_p], axis=1)  # Shape: (n, 4, m)
    B2_combined = np.stack([_ex, _ex, _ex_p, _ex_p], axis=1)              # Shape: (n, 4, m)
    gammaFdot_allcases[indices, :] = np.sum(A1_combined * B1_combined, axis=2) + np.sum(A2_combined * B2_combined, axis=2)

    indices = np.arange(1, n)
    prev_indices = indices - 1

    # Pre-compute all position differences
    diff1 = rb[prev_indices] - rd[indices]  # rb[i-1] - rd[i]
    diff2 = ra[prev_indices] - rc[indices]  # ra[i-1] - rc[i]
    diff3 = rb[prev_indices] - rc[indices]  # rb[i-1] - rc[i]
    diff4 = ra[prev_indices] - rd[indices]  # ra[i-1] - rd[i]

    # Get unit vectors for all indices
    exi = ex[indices]  # ex[i]

    # Compute all dot products at once using einsum or sum
    crit1v = np.sum(diff1 * exi, axis=1)  # diff1 @ exi
    crit2v = np.sum(diff2 * exi, axis=1)  # diff2 @ exi
    crit3v = np.sum(diff3 * exi, axis=1)  # diff3 @ exi
    crit4v = np.sum(diff4 * exi, axis=1)  # diff4 @ exi

    for i in range(1,n):
        ct_i, st_i = ct[i], st[i]
        ct_i_1, st_i_1 = ct[i-1], st[i-1]

        sin_t_i_t_i_1_o_2 = st_i_t_i_1[i]/2
        cos_t_i_t_i_1_o_2 = ct_i_t_i_1[i]/2

        f1 = h[i-1]*sin_t_i_t_i_1_o_2
        f2 = w[i-1]*cos_t_i_t_i_1_o_2
        f3 = h[i]*sin_t_i_t_i_1_o_2
        f4 = w[i]*cos_t_i_t_i_1_o_2
        f5 = -x[i]*ct_i_1 + x[i-1]*ct_i_1 - y[i]*st_i_1 + y[i-1]*st_i_1
        f6 = -h[i]*cos_t_i_t_i_1_o_2
        f7 = w[i]*sin_t_i_t_i_1_o_2
        f8 = -h[i-1]*cos_t_i_t_i_1_o_2
        f9 = w[i-1]*sin_t_i_t_i_1_o_2
        f10 = -f3 + f5

        g1 = x[i]*ct_i
        g2 = x[i-1]*ct_i
        g3 = y[i]*st_i
        g4 = y[i-1]*st_i
        g5 = -g1 + g2 - g3 + g4

        z1 = f1 + g5

        m1 = -h[i]/2
        m2 = -h[i-1]/2

        dgNa_dq[i,3*(i-1):3*(i+1)] = np.array([ st_i  , -ct_i  , -f1 - f2, -st_i, ct_i, z1 + f2])
        dgNb_dq[i,3*(i-1):3*(i+1)] = np.array([ st_i  , -ct_i  , -f1 + f2, -st_i, ct_i, z1 - f2])
        dgNc_dq[i,3*(i-1):3*(i+1)] = np.array([ st_i_1, -ct_i_1, f10 + f4, -st_i_1, ct_i_1, f3 - f4 ])
        dgNd_dq[i,3*(i-1):3*(i+1)] = np.array([ st_i_1, -ct_i_1, f10 - f4, -st_i_1, ct_i_1, f3 + f4 ])

        dgammaF_dq_allcases[i,0,3*(i-1):3*(i+1)] = np.array([ct_i  , st_i  , f8 + f9, -ct_i  , -st_i  , m1])
        dgammaF_dq_allcases[i,1,3*(i-1):3*(i+1)] = np.array([ct_i  , st_i  , f8 - f9, -ct_i  , -st_i  , m1])
        dgammaF_dq_allcases[i,2,3*(i-1):3*(i+1)] = np.array([ct_i_1, st_i_1,      m2, -ct_i_1, -st_i_1, f6 - f7])
        dgammaF_dq_allcases[i,3,3*(i-1):3*(i+1)] = np.array([ct_i_1, st_i_1,      m2, -ct_i_1, -st_i_1, f6 + f7])

    for i in range(1,n):
        # selecting the appropriate gap distance constraints for the left and right of each block
        # the selection is saved in the corners array
        #diff1 = rb[i-1,:] - rd[i,:]
        #diff2 = ra[i-1,:] - rc[i,:]
        #exi = ex[i,:]
        #crit1 = np.dot(diff1, ex[i,:])
        #crit2 = np.dot(diff2, ex[i,:])
        #crit1 = diff1 @ exi
        #crit2 = diff2 @ exi
        crit1 = crit1v[i-1]
        crit2 = crit2v[i-1]
        if crit1 > 0 or crit2 < 0:
            # complete horizontal detachement
            corners[2*(i-1)] = 4
            corners[2*(i-1)+1] = 4
        else:
            #diff3 = rb[i-1,:] - rc[i,:]
            #crit3 = diff3 @ exi
            crit3 = crit3v[i-1]
            if crit3>0:
                # b = 1
                gN[2*(i-1)] = gNb[i]
                gNdot[2*(i-1)] = gNb_dot[i]
                gNddot[2*(i-1)] = gNb_ddot[i]
                WN[2*(i-1),:] = dgNb_dq[i,:]
                corners[2*(i-1)] = 1
            else:
                # c = 2
                gN[2*(i-1)] = gNc[i]
                gNdot[2*(i-1)] = gNc_dot[i]
                gNddot[2*(i-1)] = gNc_ddot[i]
                WN[2*(i-1),:] = dgNc_dq[i,:]
                corners[2*(i-1)] = 2

            #diff4 = ra[i-1,:] - rd[i,:]
            #crit4 = diff4 @ exi
            crit4 = crit4v[i-1]
            if crit4<0:
                # a = 0
                gN[2*(i-1)+1] = gNa[i]
                gNdot[2*(i-1)+1] = gNa_dot[i]
                gNddot[2*(i-1)+1] = gNa_ddot[i]
                WN[2*(i-1)+1,:] = dgNa_dq[i,:]
                corners[2*(i-1)+1] = 0
            else:
                # d = 3
                gN[2*(i-1)+1] = gNd[i]
                gNdot[2*(i-1)+1] = gNd_dot[i]
                gNddot[2*(i-1)+1] = gNd_ddot[i]
                WN[2*(i-1)+1,:] = dgNd_dq[i,:]
                corners[2*(i-1)+1] = 3

    # Remove derivatives wrt coordinates of first block
    WN = np.transpose(WN[:,3:3*n])

    q = q_copy
    u = u_copy
    a = a_copy

    if 0:
        sum = 0
        sum += np.sum(gN)
        sum += np.sum(gNdot)
        sum += np.sum(gNddot)
        sum += np.sum(WN)
        sum += np.sum(corners)
        sum += np.sum(gammaF_allcases)
        sum += np.sum(dgammaF_dq_allcases)
        sum += np.sum(gammaFdot_allcases)
        #print(f'checksum = {sum:-21.15e}')
        checksum_expected = 4.333142370723672e+01
        #print(f'checksum_expected = {checksum_expected:-21.15e}')
        print(f'checksum relative error = {(sum-checksum_expected)/checksum_expected:-21.15e}')

    return gN, gNdot, gNddot, WN, corners, gammaF_allcases, dgammaF_dq_allcases, gammaFdot_allcases

def get_R(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,*index_sets):
    """Calculates the residual"""
    global corners_save, leaves_counter, iter, ntime

    [prev_a,_,_,_,_,_,_,_,_,_,prev_lambdaN,_,prev_lambdaF] = get_X_components(prev_X)
    [a,U,Q,Kappa_g,Lambda_g,lambda_g,Lambda_gamma,lambda_gamma,
     KappaN,LambdaN,lambdaN,LambdaF,lambdaF] = get_X_components(X)

    # AV - Auxiliary Variables [abar, lambdaNbar, lambdaFbar]
    prev_abar = prev_AV[0:ndof]
    prev_lambdaNbar = prev_AV[ndof:ndof+nN]
    prev_lambdaFbar = prev_AV[ndof+nN:ndof+nN+nF]

    # auxiliary variables update
    # eq. 49
    abar = (alpha_f*prev_a+(1-alpha_f)*a-alpha_m*prev_abar)/(1-alpha_m)
    # eq. 96
    lambdaNbar = (alpha_f*prev_lambdaN+(1-alpha_f)*lambdaN-alpha_m*prev_lambdaNbar)/(1-alpha_m)
    # eq. 114
    lambdaFbar = (alpha_f*prev_lambdaF+(1-alpha_f)*lambdaF-alpha_m*prev_lambdaFbar)/(1-alpha_m)

    AV = np.concatenate((abar,lambdaNbar,lambdaFbar),axis=None)

    # velocity update (73)
    u = prev_u+dtime*((1-gama)*prev_abar+gama*abar)+U
    # position update (73)
    q = prev_q+dtime*prev_u+dtime**2/2*((1-2*beta)*prev_abar+2*beta*abar)+Q

    # bilateral constraints at position level
    g = np.zeros((ng))
    gdot = np.zeros((ng))
    gddot = np.zeros((ng))
    Wg = np.zeros((ndof,ng))

    # bilateral constraints at velocity level
    gamma = np.zeros((ngamma))
    gammadot = np.zeros((ngamma))
    Wgamma = np.zeros((ndof,ngamma))

    # normal gap distance constraints and some frictional quantities
    gN, gNdot, gNddot, WN, corners, gammaF_allcases, dgammaF_dq_allcases, gammaFdot_allcases = get_gN(q,u,a)

    # eq. 44
    ksiN = gNdot+eN*prev_gNdot
    # discrete normal percussion eq. 95
    PN = LambdaN+dtime*((1-gama)*prev_lambdaNbar+gama*lambdaNbar)
    # eq. 102
    Kappa_hat_N = KappaN+dtime**2/2*((1-2*beta)*prev_lambdaNbar+2*beta*lambdaNbar)

    # slip speed frictional constraints
    gammaF = np.zeros((nF))
    gammaFdot = np.zeros((nF))
    WF = np.zeros((ndof,nF))

    if index_sets == ():
        A = np.zeros(nN, dtype=int)
        B = np.zeros(nN, dtype=int)
        C = np.zeros(nN, dtype=int)

        for i in range(nN):
            # check for contact if blocks are not horizontally detached
            if corners[i] != 4 and r*gN[i] - Kappa_hat_N[i] <=0:
                A[i] = 1
                if r*ksiN[i]-PN[i] <= 0:
                    B[i] = 1
                    if r*gNddot[i]-lambdaN[i] <= 0:
                        C[i] = 1
    else:
        A = index_sets[0]
        B = index_sets[1]
        C = index_sets[2]
        D = index_sets[3]
        E = index_sets[4]

        # if the blocks got horizontally detached, update the contact regions accordinly
        flag_slip_check = False

        for i in range(nN):
            if corners[i] == 4 and (A[i]!=0 or B[i]!=0 or C[i]!=0):
                flag_slip_check = True
                A[i] = 0
                B[i] = 0
                C[i] = 0

        if flag_slip_check == True:
            for i in range(nF):
                if A[2*i] == 0 and A[2*i+1] == 0:
                    D[i] = 0
                    E[i] = 0


    # Assigning the friction force based on the contact region
    for i in range(nF):
        if A[2*i] == 1:
            # if first contact is closed
            gammaF[i] = gammaF_allcases[i+1,corners[2*i]]
            gammaFdot[i] = gammaFdot_allcases[i+1,corners[2*i]]
            WF[:,i] = np.transpose(dgammaF_dq_allcases[i+1,corners[2*i],3:3*n])
        else:
            # the second contact is closed (A[2*i+1] == 1) OR both contacts are open
            # if the contact is open, the following values do not matter
            gammaF[i] = gammaF_allcases[i+1,corners[2*i+1]%4]
            gammaFdot[i] = gammaFdot_allcases[i+1,corners[2*i+1]%4]
            WF[:,i] = np.transpose(dgammaF_dq_allcases[i+1,corners[2*i+1]%4,3:3*n])

    # eq. 48
    ksiF = gammaF+eN*prev_gammaF
    # eq. 113
    PF = LambdaF+dtime*((1-gama)*prev_lambdaFbar+gama*lambdaFbar)

    if index_sets == ():
        D = np.zeros(nF, dtype=int)
        E = np.zeros(nF, dtype=int)

        for i in range(nF):
            if A[2*i] == 1 or A[2*i+1] == 1:
                if np.abs(r*ksiF[i]-PF[i])<=mu[i+1]*(PN[2*i]+PN[2*i+1]):
                    # D-stick
                    D[i] = 1
                    # if B[2*i] == 1 or B[2*i+1] == 1:
                    if np.abs(r*gammaFdot[i]-lambdaF[i])<=mu[i+1]*(lambdaN[2*i]+lambdaN[2*i+1]):
                        # E-stick
                        E[i] = 1

    # calculating contact residual
    R_LambdaN = np.zeros(nN)
    R_lambdaN = np.zeros(nN)
    R_KappaN = np.zeros(nN)
    for i in range(nN):
        if A[i] == 1:
            R_KappaN[i] = gN[i]
        else:
            R_KappaN[i] = Kappa_hat_N[i]
        if B[i] == 1:
            R_LambdaN[i] = ksiN[i]
        else:
            R_LambdaN[i] = PN[i]
        if C[i] == 1:
            R_lambdaN[i] = gNddot[i]
        else:
            R_lambdaN[i] = lambdaN[i]

    R_LambdaF = np.zeros(nF)
    R_lambdaF = np.zeros(nF)
    for i in range(nF):
        if A[2*i] == 1 or A[2*i+1] == 1:
            if D[i] == 1:
                # D-stick
                R_LambdaF[i] = ksiF[i]
                if E[i] == 1:
                    # E_stick
                    R_lambdaF[i] = gammaFdot[i]
                else:
                    # E_slip
                    R_lambdaF[i] = lambdaF[i]+mu[i+1]*(lambdaN[2*i]+lambdaN[2*i+1])*gammaFdot[i]/np.abs(gammaFdot[i])
            else:
                # D_slip
                R_LambdaF[i] = PF[i]+mu[i+1]*(PN[2*i]+PN[2*i+1])*ksiF[i]/np.abs(ksiF[i])
                R_lambdaF[i] = lambdaF[i]+mu[i+1]*(lambdaN[2*i]+lambdaN[2*i+1])*gammaF[i]/np.abs(gammaF[i])
        else: # no touch
            R_LambdaF[i] = PF[i]
            R_lambdaF[i] = lambdaF[i]


    Rs = np.concatenate(([M@a-force-Wg@lambda_g-Wgamma@lambda_gamma-WN@lambdaN-WF@lambdaF],
               [M@U-Wg@Lambda_g-Wgamma@Lambda_gamma-WN@LambdaN-WF@LambdaF],
               [M@Q-Wg@Kappa_g-WN@KappaN-dtime/2*(Wgamma@Lambda_gamma+WF@LambdaF)],
               g,
               gdot,
               gddot,
               gamma,
               gammadot),axis=None)

    Rc = np.concatenate((R_KappaN, R_LambdaN, R_lambdaN, R_LambdaF, R_lambdaF),axis=None)

    R = np.concatenate([Rs, Rc],axis=None)

    if index_sets == ():
        # in this case, get_R is called to calculate the actual residual, not as part of calculating the Jacobian
        #print(f"A={A}")
        #print(f"B={B}")
        #print(f"C={C}")
        #print(f"D={D}")
        #print(f"E={E}")
        corners_save[leaves_counter,:,iter] = corners
        return R, AV, q, u, gNdot, gammaF, A, B, C, D, E
    else:
        # in this case, get_R is called as part of calculating the Jacobian for fixed contact regions
        return R, AV, q, u, gNdot, gammaF

def get_R_J(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,*fixed_contact):
    global A_save, B_save, C_save, D_save, E_save
    global iter

    epsilon = 1e-6
    fixed_contact_regions = False

    if fixed_contact != ():
        # here, the contact is fixed if a solve_bifurcation is being run
        fixed_contact = fixed_contact[0]
        fixed_contact_regions = True
        A = fixed_contact[0:nN]
        B = fixed_contact[nN:2*nN]
        C = fixed_contact[2*nN:3*nN]
        D = fixed_contact[3*nN:3*nN+nF]
        E = fixed_contact[3*nN+nF:3*nN+2*nF]
        R, AV, q, u, gNdot, gammaF =  get_R(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF, A, B, C, D, E)
    else:
        R, AV, q, u, gNdot, gammaF, A, B, C, D, E = get_R(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF)
        contacts_nu = np.concatenate((A,B,C,D,E),axis=None)

    # Initializing the Jacobian
    J = np.zeros((nX,nX))
    I = np.identity(nX)

    A_save[:,iter] = A
    B_save[:,iter] = B
    C_save[:,iter] = C
    D_save[:,iter] = D
    E_save[:,iter] = E

    # Constructing the Jacobian column by column
    for i in range(nX):
        # print(i)
        R_plus_epsilon,_,_,_,_,_ = get_R(X+epsilon*I[:,i],prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF, A, B, C, D, E)
        J[:,i] = (R_plus_epsilon-R)/epsilon

    if fixed_contact_regions:
        return R, AV, q, u, gNdot, gammaF, J
    else:
        # return the contact regions 'contacts_nu' to be saved in case they are needed (in the case of unconverged iterations)
        return R, AV, q, u, gNdot, gammaF, J, contacts_nu

def update(prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,*fixed_contact):
    """Takes components at time t and return values at time t+dt"""
    global ntime

    nu = 0
    X = prev_X

    if fixed_contact != ():
        # the contact region is fixed if solve_bifuration is calling update
        # the fixed_contact data is inputted into get_R_J
        fixed_contact = fixed_contact[0]
        fixed_contact_regions = True
    else:
        fixed_contact_regions = False

    try:
        if fixed_contact_regions == True:
            R, AV, q, u, gNdot, gammaF, J = get_R_J(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,fixed_contact)
        else:
            R, AV, q, u, gNdot, gammaF, J, contacts_nu = get_R_J(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF)
            contacts = np.zeros((MAXITERn+1,3*nN+2*nF),dtype=int)
            contacts[nu,:] = contacts_nu
        norm_R = np.linalg.norm(R,np.inf)
        #print(f"nu = {nu}")
        print(f"1-norm(R) = {norm_R}")

        while np.abs(np.linalg.norm(R,np.inf))>10**(-10) and nu<MAXITERn:
            # Newton Update
            X = X-np.linalg.solve(J,R)
            # Calculate new EOM and residual
            nu = nu+1
            if fixed_contact_regions:
                R, AV, q, u, gNdot, gammaF, J = get_R_J(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,fixed_contact)
            else:
                R, AV, q, u, gNdot, gammaF, J, contacts_nu = get_R_J(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF)
                contacts[nu,:] = contacts_nu
            norm_R = np.linalg.norm(R,np.inf)
            #print(f"nu = {nu}")
            print(f"2-norm(R) = {norm_R}")
            print(f"2-norm(R) rdiff = {1.0 - norm_R/2.6506297157169456e-11}")
        if nu == MAXITERn:
            print(f"No Convergence for nu = {nu} at rho_inf = {rho_inf}")
            raise MaxNewtonIterAttainedError

        if reduce_ntime_if_fail == 1:   # if we ask to stop code after failure is detected
            if 4 in corners_save:       # if failure is detected
                f.write(f"ntime changed from {ntime} to {iter}.\n")
                ntime = iter
                f.write(f"Failure Detected at {iter}.\n")
                # raise FailureDetected

    except MaxNewtonIterAttainedError as e:
        if fixed_contact_regions is False:
            # if unique contact regions were already determined, don't recalculate them
            unique_contacts = np.unique(contacts, axis=0)
            do_not_unpack = True
            # because if the number of contact regions is 6 which is the original number
            # of outputs of update, each row of unique contacts will be assinged as an output variable
            return unique_contacts, do_not_unpack
        return
    except np.linalg.LinAlgError as e:
        # the Jacobian matrix is singular, not invertable
        print(e)
        # increment rho_inf
        update_rho_inf()
        # calling function recursively
        update(prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,fixed_contact)
    except Exception as e:
        # any other exception
        raise e

    return X,AV,q,u,gNdot,gammaF

def update_rho_inf():
    global rho_inf, alpha_m, alpha_f, gama, beta
    rho_inf = rho_inf+0.05  #0.01
    print(rho_inf)
    if np.abs(rho_inf - rho_infinity_initial) < 0.001:
        print("possibility of infinite loop")
        raise RhoInfInfiniteLoop
    if rho_inf > 1.001:
        rho_inf = 0
    # eq. 72
    alpha_m = (2*rho_inf-1)/(rho_inf+1)
    alpha_f = rho_inf/(rho_inf+1)
    gama = 0.5+alpha_f-alpha_m
    beta = 0.25*(0.5+gama)**2

def get_X_components(X):
    a = X[0:ndof]
    U = X[ndof:2*ndof]
    Q = X[2*ndof:3*ndof]
    Kappa_g = X[3*ndof:3*ndof+ng]
    Lambda_g = X[3*ndof+ng:3*ndof+2*ng]
    lambda_g = X[3*ndof+2*ng:3*ndof+3*ng]
    Lambda_gamma = X[3*ndof+3*ng:3*ndof+3*ng+ngamma]
    lambda_gamma = X[3*ndof+3*ng+ngamma:3*ndof+3*ng+2*ngamma]
    Kappa_N = X[3*ndof+3*ng+2*ngamma:3*ndof+3*ng+2*ngamma+nN]
    Lambda_N = X[3*ndof+3*ng+2*ngamma+nN:3*ndof+3*ng+2*ngamma+2*nN]
    lambda_N = X[3*ndof+3*ng+2*ngamma+2*nN:3*ndof+3*ng+2*ngamma+3*nN]
    Lambda_F = X[3*ndof+3*ng+2*ngamma+3*nN:3*ndof+3*ng+2*ngamma+3*nN+nF]
    lambda_F = X[3*ndof+3*ng+2*ngamma+3*nN+nF:3*ndof+3*ng+2*ngamma+3*nN+2*nF]
    return a,U,Q,Kappa_g,Lambda_g,lambda_g,Lambda_gamma,lambda_gamma,\
        Kappa_N,Lambda_N,lambda_N,Lambda_F,lambda_F

def get_xyt(q):
    x = np.zeros(n)
    y = np.zeros(n)
    theta = np.zeros(n)
    for i in range(n):
        x[i] = q[3*i]
        y[i] = q[3*i+1]
        theta[i] = q[3*i+2]
    return x, y, theta

def increment_saved_arrays():
    global q_save, u_save, X_save, gNdot_save, gammaF_save, AV_save, corners_save

    save_arrays()

    # increment saved arrays
    q_save_addition = np.tile(q_save[leaves_counter,:,:],(1,1,1))
    q_save = np.vstack((q_save,q_save_addition))
    u_save_addition = np.tile(u_save[leaves_counter,:,:],(1,1,1))
    u_save = np.vstack((u_save,u_save_addition))
    X_save_addition = np.tile(X_save[leaves_counter,:,:],(1,1,1))
    X_save = np.vstack((X_save,X_save_addition))
    gNdot_save_addition = np.tile(gNdot_save[leaves_counter,:,:],(1,1,1))
    gNdot_save = np.vstack((gNdot_save,gNdot_save_addition))
    gammaF_save_addition = np.tile(gammaF_save[leaves_counter,:,:],(1,1,1))
    gammaF_save = np.vstack((gammaF_save,gammaF_save_addition))
    AV_save_addition = np.tile(AV_save[leaves_counter,:,:],(1,1,1))
    AV_save = np.vstack((AV_save,AV_save_addition))
    corners_save_addition = np.tile(corners_save[leaves_counter,:,:],(1,1,1))
    corners_save = np.vstack((corners_save,corners_save_addition))

def solve(iter_start):
    global q_save, u_save, X_save, gNdot_save, gammaF_save, AV_save, corners_save
    global leaves_counter
    global iter
    global rho_infinity_initial, rho_inf

    fixed_contact_regions = False
    increment_leaves = True

    # f.write(f'Running solve starting from iteration at leaf {leaves_counter}\n')
    g.write(f'{iter_start}-')

    prev_X = X_save[leaves_counter,:,iter_start-1]
    prev_AV = AV_save[leaves_counter,:,iter_start-1]
    prev_q = q_save[leaves_counter,:,iter_start-1]
    prev_u = u_save[leaves_counter,:,iter_start-1]
    prev_gNdot = gNdot_save[leaves_counter,:,iter_start-1]
    prev_gammaF = gammaF_save[leaves_counter,:,iter_start-1]
    iter = iter_start
    # for iter in range(iter_start,ntime):

    while iter<ntime:
        _t0 = time.time()
        print(f"iteration {iter}")

        current_time = time.time()
        if current_time-start_time>(3600*max_hours):
            f.write(f'Program quit because max execution time {max_hours} hours was exceeded.')
            raise MaxHoursAttained
            # instead set ntime = iter to reduce ntime instead of directly quitting program

        # f.write(f'Iteration {iter}\n')

        try:
            X,AV,q,u,gNdot,gammaF = update(prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF)
            # this line will return a value error if the MaxNewtonIterAttainedError exception was handeled in update

            prev_X = X
            prev_AV = AV
            prev_q = q
            prev_u = u
            prev_gNdot = gNdot
            prev_gammaF = gammaF

            q_save[leaves_counter,:,iter] = prev_q
            u_save[leaves_counter,:,iter] = prev_u
            X_save[leaves_counter,:,iter] = prev_X
            gNdot_save[leaves_counter,:,iter] = prev_gNdot
            gammaF_save[leaves_counter,:,iter] = prev_gammaF
            AV_save[leaves_counter,:,iter] = prev_AV

            # reset initial value
            rho_infinity_initial = rho_inf

        except ValueError as e:
            unique_contacts,_ = update(prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF)
            # f.write(f'Detected a bifurcation at leaf {leaves_counter} at iter {iter}\n')
            g.write(f'{iter}\n')
            solve_bifurcation(iter,unique_contacts)
            increment_leaves = False
            break   # this break is important
        except Exception as e:
            # f.write(f'Bifurcation branch did not pan out for leaf {leaves_counter} at {iter}\n')
            raise e

        iter = iter+1

        if iter%25 == 0:
            save_arrays()

        _t1 = time.time()
        _dt = _t1 - _t0
        print(f"dt = {_dt}")
        print('---------------------------------')

    if increment_leaves == True:

        g.write(f'end (leaf {leaves_counter})\n')

        increment_saved_arrays()

        # q_save_shape = np.shape(q_save)
        # f.write(f'The shape of q_save was incremented to {q_save_shape}\n')

        leaves_counter = leaves_counter + 1
        # f.write(f'leaves counter incremented to leaf {leaves_counter}\n')
        print(f'leaves_counter = {leaves_counter}')

        # if leaves_counter>max_leaves:
        #     f.write(f'Program quit because max number of leaves that is {max_leaves} was exceeded.\n')
        #     raise Exception
        t1 = time.time()

    return

global bif_counter  # used in bifurcation log
bif_counter = 0

def solve_bifurcation(iter_bif,*fixed_contact_region_params):
    global q_save, u_save, X_save, gNdot_save, gammaF_save, AV_save
    global leaves_counter
    global iter
    global bif_counter
    bif_counter +=1

    global increment_leaves
    increment_leaves = True # I think this is unneccessary

    # f.write(f'Running solve_bifurcations at iter_bif {iter_bif} and leaf {leaves_counter}\n')

    # fixed_contact_regions = True
    unique_contacts = fixed_contact_region_params[0]
    n_unique_contacts = np.shape(unique_contacts)[0]

    # f.write(f'The number of unique contacts is {n_unique_contacts}\n')

    nonconvergence_counter = 0

    for k in range(n_unique_contacts):
        iter = iter_bif

        print(f"k = {k}")
        g.write("     |"*bif_counter)
        g.write(f'__ {k+1} of {n_unique_contacts}  ')

        try:
            fixed_contact  = unique_contacts[k,:]
            X,AV,q,u,gNdot,gammaF = update(X_save[leaves_counter,:,iter_bif-1],AV_save[leaves_counter,:,iter_bif-1],
                                       q_save[leaves_counter,:,iter_bif-1],u_save[leaves_counter,:,iter_bif-1],
                                       gNdot_save[leaves_counter,:,iter_bif-1],gammaF_save[leaves_counter,:,iter_bif-1],
                                       fixed_contact)

            prev_X = X
            prev_AV = AV
            prev_q = q
            prev_u = u
            prev_gNdot = gNdot
            prev_gammaF = gammaF

            q_save[leaves_counter,:,iter_bif] = prev_q
            u_save[leaves_counter,:,iter_bif] = prev_u
            X_save[leaves_counter,:,iter_bif] = prev_X
            gNdot_save[leaves_counter,:,iter_bif] = prev_gNdot
            gammaF_save[leaves_counter,:,iter_bif] = prev_gammaF
            AV_save[leaves_counter,:,iter_bif] = AV

            # f.write(f'{k}-th unique contact convergence successfull\n')

            solve(iter_bif+1)

            if leaves_counter > max_leaves:
                break

        except TypeError as e:
            # make a provision for if we always passed and never converged.
            # f.write(f'{k}-th unique contact convergence unsuccessfull\n')
            g.write('unsuccessful\n')
            nonconvergence_counter = nonconvergence_counter+1
            # f.write(f'nonconvergence_counter = {nonconvergence_counter}\n')
            # num_bif_contacts[leaves_counter,3] = num_bif_contacts[leaves_counter,3]-1
            if nonconvergence_counter == n_unique_contacts:
                # exception raised when None of the fixed contact regions converged
                # raise Exception
                global MAXITERn
                nonconvergence_counter = 0
                if MAXITERn < 10:  # INCOMPLETE, TO BE FIXED
                    # try to increase number of iterations
                    MAXITERn = 200
                    solve_bifurcation(iter_bif,unique_contacts)
                else:
                    try:
                        update_rho_inf()
                        solve_bifurcation(iter_bif,unique_contacts)
                    except:
                        # we cannot update rho_inf anymore
                        # we need to abandon this leaf
                        g.write(f'bifurcation convergence failed\n')
                        pass
                        raise Exception
                # solve_bifurcation(iter_bif,unique_contacts) # maybe wrong, remove
            else:
                pass

    bif_counter = bif_counter-1
    # increment_leaves = False

    return

# initial normal force
lambdaN0 = np.zeros(nN)
lambdaN0[nN-1] = m[n-1]*gr/2
lambdaN0[nN-2] = m[n-1]*gr/2
for i in range(n-1,1,-1):
    lambdaN0[2*(i-1)-1] = m[i-1]*gr/2+lambdaN0[2*(i-1)+1]
    lambdaN0[2*(i-1)-2] = m[i-1]*gr/2+lambdaN0[2*(i-1)+1]

X0 = np.zeros(nX)
X0[3*ndof+3*ng+2*ngamma+2*nN:3*ndof+3*ng+2*ngamma+3*nN] = lambdaN0

# initial auxiliary variable
nAV = ndof+nN+nF
AV0 = np.zeros(nAV)
AV0[ndof:ndof+nN] = lambdaN0

# initial position
x0 = np.zeros(n)
y0 = np.zeros(n)
# the blocks are initially stacked
y0[0] = h[0]/2
for i in range(1,n):
    y0[i] = y0[i-1]+h[i-1]/2+h[i]/2
theta0 = np.zeros(n)
# assembling position coordinates in q0
q0 = np.zeros(3*n)
for i in range(1,n):
    q0[3*i:3*i+3] = [x0[i],y0[i],theta0[i]]

# initial velocity
u0 = np.zeros(3*n)  # starting from rest

# initial normal gap speeds
gNdot0 = np.zeros(nN)   # starting from rest

# inital slip speeds
gammaF0 = np.zeros(nF)  # starting from rest

prev_X = X0
prev_AV = AV0
prev_q = q0[3:3*n]
prev_u = u0[3:3*n]
prev_gNdot = gNdot0
prev_gammaF = gammaF0

q_save = np.zeros((1,ndof,ntime))
u_save = np.zeros((1,ndof,ntime))
X_save = np.zeros((1,nX,ntime))
gNdot_save = np.zeros((1,nN,ntime))
gammaF_save = np.zeros((1,nF,ntime))
AV_save = np.zeros((1,ndof+nN+nF,ntime))
corners_save = np.zeros((1,nN,ntime))

q_save[0,:,0] = prev_q
u_save[0,:,0] = prev_u
X_save[0,:,0] = prev_X
gNdot_save[0,:,0] = prev_gNdot
gammaF_save[0,:,0] = prev_gammaF
AV_save[0,:,0] = prev_AV

A_save = np.zeros((nN,ntime))
B_save = np.zeros((nN,ntime))
C_save = np.zeros((nN,ntime))
D_save = np.zeros((nF,ntime))
E_save = np.zeros((nF,ntime))

# parameters for bifurcations
fixed_contact_regions = False   # COMMENT THIS AND SEE IF NECESSARY

leaves_counter = 0
# running the code!
try:
    f.write(f"nblocks = {n}, oscillation amplitude = {k}*{w[1]}, angular frequency = {ang_frq},\n")
    f.write(f"number of oscillations = {n_oscillations}, number of iterations per oscillation = {iters_per_oscillation},\n")
    f.write(f"Period of oscillation: {oscillation_period} sec/cycle.\n")
    f.write(f"Total duration of simulation: {tf} sec.\n\n")
    solve(1)
    # removing last added leaf_counter
    leaves_counter = leaves_counter-1
    # f.write(f'leaves_counter decremented to {leaves_counter}\n')
    # removing the last added block to q_save
    q_save = q_save[0:np.shape(q_save)[0]-1,:,:]
    # f.write(f'q_save decremented to {np.shape(q_save)}\n')
except:
    f.write(f"Failure at iteration {iter} while calculating leaf {leaves_counter} at bifurcation level {bif_counter}.\n")
finally:
    f.write(f"Number of converged leaves: {leaves_counter}\n")
    end_time = time.time()
    execution_time = end_time-start_time
    print("Execution time:", execution_time, "seconds")
    g.write(f"Execution time: {execution_time} seconds.\n")
    f.write(f"Execution time: {execution_time} seconds.\n")
    f.write("\n")

    f.close()
    g.close()

    block0 = np.stack((xbb,h[0]/2*np.ones((ntime_init)),np.zeros((ntime_init))))
    block0_tiled = np.tile(block0,(np.shape(q_save)[0],1,1))
    q_save_total = np.concatenate((block0_tiled,q_save),axis=1)


    file_name = str(f'{output_path}/q.mat')
    scipy.io.savemat(file_name,dict(q=q_save_total))
    file_name_corners = str(f'{output_path}/corners.mat')
    scipy.io.savemat(file_name_corners,dict(corners=corners_save))

    print("Saved.")

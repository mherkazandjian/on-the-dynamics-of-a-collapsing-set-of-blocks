# branch-by-branch-solution

import numpy as np
import math
import time
import os
import argparse
import scipy.io

start_time = time.time()

# optaining certain parametric arguments from an input file
# def parse_args():
#     parser = argparse.ArgumentParser(description='Process some integers and floats.')
#     parser.add_argument('n', type=int, help='Number of blocks (integer)')
#     parser.add_argument('k', type=float, help='Oscillations amplitude = k*block_width(float)')
#     parser.add_argument('ang_frq', type=float, help='Angular velocity of oscillations (float)')
#     parser.add_argument('mu_val', type=float, help='coefficient of friction (float)')
#     parser.add_argument('n_oscillations', type=float, default = 5, help='Number of oscillations to simulate (float)')
#     parser.add_argument('iters_per_oscillation', type=float, default = 35, help='Number of iterations per oscillations (float)')
#     parser.add_argument('--output_path', '-o', type=str, help='Output path (optional)')
    
#     args = parser.parse_args()
    
#     return args.n, args.k, args.ang_frq, args.mu_val, args.n_oscillations, args.iters_per_oscillation, args.output_path

# n, k, ang_frq, mu_val, n_oscillations, iters_per_oscillation, output_path = parse_args()

# # # ############################
n = 6
k = 1
ang_frq = 5.4977
mu_val = 0.3
n_oscillations = 8
iters_per_oscillation = 200
output_path = os.path.join(os.getcwd(), "outputs/multiple_solutions")
os.makedirs(output_path, exist_ok=True)
# # # ############################

# Define failure to occur when any two consecutive blocks loose contact.
# If you would like to stop solving for the motion of the stack beyond the timestep
# when failure is detected, set the 'reduce_ntime_if_fail = 1'. Otherwise set
# 'reduce_ntime_if_fail = 0'.
# The solution is stopped by reducing ntime to the iteration when failure is detected.
reduce_ntime_if_fail = 1

# Specify the maximum duration in hours for one run 
max_hours = 50

# Specify the maximum number of leaves beyond which the code will stop running (actuall max leaves is max_leaves+1)
max_leaves = 2

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

class NoBifurcationConvergence(Exception):
    """This exception is raised when all leaves did not converge."""
    def __init__(self, message="This exception is raised when all leaves did not converge."):
        self.message = message
        super().__init__(self.message)

# f is an output file that logs failed runs
# it is saved in the directory containing the output file
directory_containing_output = os.path.dirname(output_path)
f = open(f"{directory_containing_output}/run_failures_log.txt",'a')

# g details the birth and death of multiple solutions
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

# n = 5
# k = 1
# ang_frq = 09.4248
# mu_val = 0.3
# n_oscillations = 150
# iters_per_oscillation = 200

g.write(f"######\n Running simulation with n = {n} blocks, angfre = {ang_frq}, mu = {mu_val} for {n_oscillations} oscillations with {iters_per_oscillation} iterations per oscillation.\n")
g.write(f"    Period of oscillation: {oscillation_period} time/cycle.\n")
g.write(f"    Total duration of simulation: {tf}.\n\n")

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
MAXITERn_initial = MAXITERn
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

def remove_last_line(file_path):
    # Read all lines from the file
    with open(file_path, 'r') as file:
        lines = file.readlines()

    # Rewrite the file without the last line
    with open(file_path, 'w') as file:
        file.writelines(lines[:-1])

def update_rho_inf():
    global rho_inf, alpha_m, alpha_f, gama, beta, iter
    rho_inf = rho_inf+0.05  #0.01
    print(rho_inf)
    if np.abs(rho_inf - rho_infinity_initial) < 0.001:
        g.write("\n     rho_inf has been updated through a complete cycle.\n")
        print(f"Iteration {iter}: possibility of infinite loop.\n")
        raise RhoInfInfiniteLoop
    if rho_inf > 1.001:
        rho_inf = 0
    # eq. 72
    alpha_m = (2*rho_inf-1)/(rho_inf+1)
    alpha_f = rho_inf/(rho_inf+1)
    gama = 0.5+alpha_f-alpha_m
    beta = 0.25*(0.5+gama)**2

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
    ex = np.zeros((n,2))
    ey = np.zeros((n,2))
    
    exdot = np.zeros((n,2))
    eydot = np.zeros((n,2))
    
    exddot = np.zeros((n,2))
    eyddot = np.zeros((n,2))
    
    # initializing the position, velocity, and acceleration vectors to the center of mass of each block
    r = np.zeros((n,2))
    v = np.zeros((n,2))
    a = np.zeros((n,2))

    # initializing the position, velocity, and acceleration vectors to each of the 4 corners
    ra = np.zeros((n,2))
    rb = np.zeros((n,2))
    rc = np.zeros((n,2))
    rd = np.zeros((n,2))
    
    va = np.zeros((n,2))
    vb = np.zeros((n,2))
    vc = np.zeros((n,2))
    vd = np.zeros((n,2))
    
    aa = np.zeros((n,2))
    ab = np.zeros((n,2))
    ac = np.zeros((n,2))
    ad = np.zeros((n,2))
    
    for i in range(n):  # range of blocks
        ex[i,:] = np.array([np.cos(theta[i]), np.sin(theta[i])])
        ey[i,:] = np.array([-np.sin(theta[i]), np.cos(theta[i])])

        exdot[i,:] = thetadot[i]*ey[i,:]
        eydot[i,:] = -thetadot[i]*ex[i,:]

        exddot[i,:] = thetaddot[i]*ey[i,:]-thetadot[i]**2*ex[i,:]
        eyddot[i,:] = -thetaddot[i]*ex[i,:]-thetadot[i]**2*ey[i,:]

        r[i,:] = np.array([x[i],y[i]])
        v[i,:] = np.array([xdot[i],ydot[i]])
        a[i,:] = np.array([xddot[i],yddot[i]])

        ra[i,:] = r[i,:]+w[i]/2*ex[i,:]+h[i]/2*ey[i,:]
        rb[i,:] = r[i,:]-w[i]/2*ex[i,:]+h[i]/2*ey[i,:]
        rc[i,:] = r[i,:]-w[i]/2*ex[i,:]-h[i]/2*ey[i,:]
        rd[i,:] = r[i,:]+w[i]/2*ex[i,:]-h[i]/2*ey[i,:]

        va[i,:] = v[i,:]+w[i]/2*exdot[i,:]+h[i]/2*eydot[i,:]
        vb[i,:] = v[i,:]-w[i]/2*exdot[i,:]+h[i]/2*eydot[i,:]
        vc[i,:] = v[i,:]-w[i]/2*exdot[i,:]-h[i]/2*eydot[i,:]
        vd[i,:] = v[i,:]+w[i]/2*exdot[i,:]-h[i]/2*eydot[i,:]

        aa[i,:] = a[i,:]+w[i]/2*exddot[i,:]+h[i]/2*eyddot[i,:]
        ab[i,:] = a[i,:]-w[i]/2*exddot[i,:]+h[i]/2*eyddot[i,:]
        ac[i,:] = a[i,:]-w[i]/2*exddot[i,:]-h[i]/2*eyddot[i,:]
        ad[i,:] = a[i,:]+w[i]/2*exddot[i,:]-h[i]/2*eyddot[i,:]

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

    for i in range(1,n):
        gNa[i] = np.dot(rc[i,:]-ra[i-1,:],ey[i,:])
        gNb[i] = np.dot(rc[i,:]-rb[i-1,:],ey[i,:])
        gNc[i] = np.dot(rc[i,:]-rb[i-1,:],ey[i-1,:])
        gNd[i] = np.dot(rd[i,:]-ra[i-1,:],ey[i-1,:])

        dgNa_dq[i,3*(i-1):3*(i+1)] = np.array([np.sin(theta[i]), -np.cos(theta[i]),-h[i-1]*np.sin(theta[i] - theta[i-1])/2 - w[i-1]*np.cos(theta[i] - theta[i-1])/2,-np.sin(theta[i]), np.cos(theta[i]),h[i-1]*np.sin(theta[i] - theta[i-1])/2 + w[i-1]*np.cos(theta[i] - theta[i-1])/2 - x[i]*np.cos(theta[i]) + x[i-1]*np.cos(theta[i]) - y[i]*np.sin(theta[i]) + y[i-1]*np.sin(theta[i])])
        dgNb_dq[i,3*(i-1):3*(i+1)] = np.array([np.sin(theta[i]), -np.cos(theta[i]),-h[i-1]*np.sin(theta[i] - theta[i-1])/2 + w[i-1]*np.cos(theta[i] - theta[i-1])/2,-np.sin(theta[i]), np.cos(theta[i]),h[i-1]*np.sin(theta[i] - theta[i-1])/2 - w[i-1]*np.cos(theta[i] - theta[i-1])/2 - x[i]*np.cos(theta[i]) + x[i-1]*np.cos(theta[i]) - y[i]*np.sin(theta[i]) + y[i-1]*np.sin(theta[i])])
        dgNc_dq[i,3*(i-1):3*(i+1)] = np.array([np.sin(theta[i-1]), -np.cos(theta[i-1]),-h[i]*np.sin(theta[i] - theta[i-1])/2 + w[i]*np.cos(theta[i] - theta[i-1])/2 - x[i]*np.cos(theta[i-1]) + x[i-1]*np.cos(theta[i-1]) - y[i]*np.sin(theta[i-1]) + y[i-1]*np.sin(theta[i-1]),-np.sin(theta[i-1]), np.cos(theta[i-1]),h[i]*np.sin(theta[i] - theta[i-1])/2 - w[i]*np.cos(theta[i] - theta[i-1])/2])
        dgNd_dq[i,3*(i-1):3*(i+1)] = np.array([np.sin(theta[i-1]), -np.cos(theta[i-1]),-h[i]*np.sin(theta[i] - theta[i-1])/2 - w[i]*np.cos(theta[i] - theta[i-1])/2 - x[i]*np.cos(theta[i-1]) + x[i-1]*np.cos(theta[i-1]) - y[i]*np.sin(theta[i-1]) + y[i-1]*np.sin(theta[i-1]),-np.sin(theta[i-1]), np.cos(theta[i-1]),h[i]*np.sin(theta[i] - theta[i-1])/2 + w[i]*np.cos(theta[i] - theta[i-1])/2])

        gNa_dot[i] = np.dot(vc[i,:]-va[i-1,:],ey[i,:])+np.dot(rc[i,:]-ra[i-1,:],eydot[i,:])
        gNb_dot[i] = np.dot(vc[i,:]-vb[i-1,:],ey[i,:])+np.dot(rc[i,:]-rb[i-1,:],eydot[i,:])
        gNc_dot[i] = np.dot(vc[i,:]-vb[i-1,:],ey[i-1,:])+np.dot(rc[i,:]-rb[i-1,:],eydot[i-1,:])
        gNd_dot[i] = np.dot(vd[i,:]-va[i-1,:],ey[i-1,:])+np.dot(rd[i,:]-ra[i-1,:],eydot[i-1,:])

        gNa_ddot[i] = np.dot(ac[i,:]-aa[i-1,:],ey[i,:])+2*np.dot(vc[i,:]-va[i-1,:],eydot[i,:])+np.dot(rc[i,:]-ra[i-1,:],eyddot[i,:])
        gNb_ddot[i] = np.dot(ac[i,:]-ab[i-1,:],ey[i,:])+2*np.dot(vc[i,:]-vb[i-1,:],eydot[i,:])+np.dot(rc[i,:]-rb[i-1,:],eyddot[i,:])
        gNc_ddot[i] = np.dot(ac[i,:]-ab[i-1,:],ey[i-1,:])+2*np.dot(vc[i,:]-vb[i-1,:],eydot[i-1,:])+np.dot(rc[i,:]-rb[i-1,:],eyddot[i-1,:])
        gNd_ddot[i] = np.dot(ad[i,:]-aa[i-1,:],ey[i-1,:])+2*np.dot(vd[i,:]-va[i-1,:],eydot[i-1,:])+np.dot(rd[i,:]-ra[i-1,:],eyddot[i-1,:])

        gammaF_allcases[i,0] = np.dot(va[i-1,:]-vc[i,:],ex[i,:])    # a
        gammaF_allcases[i,1] = np.dot(vb[i-1,:]-vc[i,:],ex[i,:])    # b
        gammaF_allcases[i,2] = np.dot(va[i-1,:]-vc[i,:],ex[i-1,:])  # c
        gammaF_allcases[i,3] = np.dot(va[i-1,:]-vd[i,:],ex[i-1,:])  # d

        dgammaF_dq_allcases[i,0,3*(i-1):3*(i+1)] = np.array([np.cos(theta[i]), np.sin(theta[i]),-h[i-1]*np.cos(theta[i] - theta[i-1])/2 + w[i-1]*np.sin(theta[i] - theta[i-1])/2,-np.cos(theta[i]), -np.sin(theta[i]), -h[i]/2])
        dgammaF_dq_allcases[i,1,3*(i-1):3*(i+1)] = np.array([np.cos(theta[i]), np.sin(theta[i]),-h[i-1]*np.cos(theta[i] - theta[i-1])/2 - w[i-1]*np.sin(theta[i] - theta[i-1])/2,-np.cos(theta[i]), -np.sin(theta[i]), -h[i]/2])
        dgammaF_dq_allcases[i,2,3*(i-1):3*(i+1)] = np.array([np.cos(theta[i-1]), np.sin(theta[i-1]), -h[i-1]/2, -np.cos(theta[i-1]),-np.sin(theta[i-1]),-h[i]*np.cos(theta[i] - theta[i-1])/2 - w[i]*np.sin(theta[i] - theta[i-1])/2])
        dgammaF_dq_allcases[i,3,3*(i-1):3*(i+1)] = np.array([np.cos(theta[i-1]), np.sin(theta[i-1]), -h[i-1]/2, -np.cos(theta[i-1]),-np.sin(theta[i-1]),-h[i]*np.cos(theta[i] - theta[i-1])/2 + w[i]*np.sin(theta[i] - theta[i-1])/2])

        gammaFdot_allcases[i,0] = np.dot(va[i-1,:]-vc[i,:],exdot[i,:])+np.dot(aa[i-1,:]-ac[i,:],ex[i,:])        # a
        gammaFdot_allcases[i,1] = np.dot(vb[i-1,:]-vc[i,:],exdot[i,:])+np.dot(ab[i-1,:]-ac[i,:],ex[i,:])        # b
        gammaFdot_allcases[i,2] = np.dot(va[i-1,:]-vc[i,:],exdot[i-1,:])+np.dot(aa[i-1,:]-ac[i,:],ex[i-1,:])    # c
        gammaFdot_allcases[i,3] = np.dot(va[i-1,:]-vd[i,:],exdot[i-1,:])+np.dot(aa[i-1,:]-ad[i,:],ex[i-1,:])    # d

        # selecting the appropriate gap distance constraints for the left and right of each block
        # the selection is saved in the corners array
        if np.dot(rb[i-1,:]-rd[i,:],ex[i,:])>0 or np.dot(ra[i-1,:]-rc[i,:],ex[i,:])<0:
            # complete horizontal detachement
            corners[2*(i-1)] = 4
            corners[2*(i-1)+1] = 4
        else:
            if np.dot(rb[i-1,:]-rc[i,:],ex[i,:])>0:
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
            if np.dot(ra[i-1,:]-rd[i,:],ex[i,:])<0:
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

    return gN, gNdot, gNddot, WN, corners, gammaF_allcases, dgammaF_dq_allcases, gammaFdot_allcases


def get_R(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf,*index_sets):
    """Calculates the residual"""
    global corners_save, iter, ntime

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
        # print(f"A={A}")
        # print(f"B={B}")
        # print(f"C={C}")
        # print(f"D={D}")
        # print(f"E={E}")
        corners_save[leaf,:,iter] = corners
        return R, AV, q, u, gNdot, gammaF, A, B, C, D, E
    else:
        # in this case, get_R is called as part of calculating the Jacobian for fixed contact regions
        return R, AV, q, u, gNdot, gammaF

def get_R_J(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf,*fixed_contact):
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
        R, AV, q, u, gNdot, gammaF =  get_R(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf,A, B, C, D, E)
    else:
        R, AV, q, u, gNdot, gammaF, A, B, C, D, E = get_R(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf)
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
        R_plus_epsilon,_,_,_,_,_ = get_R(X+epsilon*I[:,i],prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf, A, B, C, D, E)
        J[:,i] = (R_plus_epsilon-R)/epsilon

    if fixed_contact_regions:
        return R, AV, q, u, gNdot, gammaF, J
    else:
        # return the contact regions 'contacts_nu' to be saved in case they are needed (in the case of unconverged iterations)
        return R, AV, q, u, gNdot, gammaF, J, contacts_nu

def update(prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf,*fixed_contact):
    """Takes components at time t and return values at time t+dt"""
    global ntime, iter
    
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
            R, AV, q, u, gNdot, gammaF, J = get_R_J(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf,fixed_contact)
        else:
            R, AV, q, u, gNdot, gammaF, J, contacts_nu = get_R_J(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf)
            contacts = np.zeros((MAXITERn+1,3*nN+2*nF),dtype=int)
            contacts[nu,:] = contacts_nu
        norm_R = np.linalg.norm(R,np.inf)
        # print(f"nu = {nu}")
        # print(f"norm(R) = {norm_R}")

        while np.abs(np.linalg.norm(R,np.inf))>(10**(-10)) and nu<MAXITERn:
            # Newton Update
            X = X-np.linalg.solve(J,R)
            # Calculate new EOM and residual
            nu = nu+1
            if fixed_contact_regions:
                R, AV, q, u, gNdot, gammaF, J = get_R_J(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf,fixed_contact)
            else:
                R, AV, q, u, gNdot, gammaF, J, contacts_nu = get_R_J(X,prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf)
                contacts[nu,:] = contacts_nu
            norm_R = np.linalg.norm(R,np.inf)
            # print(f"nu = {nu}")
            # print(f"norm(R) = {norm_R}")
        if nu == MAXITERn:
            print(f"Iteration {iter} and leaf {leaf}:")
            print(f"No Convergence for nu = {nu} at rho_inf = {rho_inf}\n")
            raise MaxNewtonIterAttainedError
        
        if reduce_ntime_if_fail == 1:   # if we ask to stop code after failure is detected
            if 4 in corners_save:       # if failure is detected
                f.write(f"    Failure was detected at iteration {iter}, so ntime changed from {ntime} to {iter}.\n")
                ntime = iter
                raise FailureDetected

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
        print(f"Error {e} at iteration {iter} and leaf {leaf}.")
        # increment rho_inf        
        update_rho_inf()
        # calling function recursively
        update(prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf,fixed_contact)
    except Exception as e:
        # any other exception
        g.write(f"\n    The exception {e} was raised during the calculation of some leaf at iteration {iter}.\n")
        print(f"Error {e} at iteration {iter} and leaf {leaf}.\n")
        raise e
    
    return X,AV,q,u,gNdot,gammaF

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

bif_tracker = np.array([0])

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

    np.save(f'{output_path}/q_save.npy', q_save)
    np.save(f'{output_path}/u_save.npy', u_save)
    np.save(f'{output_path}/X_save.npy', X_save)
    np.save(f'{output_path}/gNdot_save.npy', gNdot_save)
    np.save(f'{output_path}/gammaF_save.npy', gammaF_save)
    np.save(f'{output_path}/AV_save.npy', AV_save)

    return

def increment_saved_arrays(leaf):
    global q_save, u_save, X_save, gNdot_save, gammaF_save, AV_save, corners_save
    global bif_tracker

    bif_tracker = np.vstack((bif_tracker,np.array([iter])))

    save_arrays()

    # increment saved arrays
    q_save_addition = np.tile(q_save[leaf,:,:],(1,1,1))
    q_save = np.vstack((q_save,q_save_addition))
    u_save_addition = np.tile(u_save[leaf,:,:],(1,1,1))
    u_save = np.vstack((u_save,u_save_addition))
    X_save_addition = np.tile(X_save[leaf,:,:],(1,1,1))
    X_save = np.vstack((X_save,X_save_addition))
    gNdot_save_addition = np.tile(gNdot_save[leaf,:,:],(1,1,1))
    gNdot_save = np.vstack((gNdot_save,gNdot_save_addition))
    gammaF_save_addition = np.tile(gammaF_save[leaf,:,:],(1,1,1))
    gammaF_save = np.vstack((gammaF_save,gammaF_save_addition))
    AV_save_addition = np.tile(AV_save[leaf,:,:],(1,1,1))
    AV_save = np.vstack((AV_save,AV_save_addition))
    corners_save_addition = np.tile(corners_save[leaf,:,:],(1,1,1))
    corners_save = np.vstack((corners_save,corners_save_addition))


def solve_new(leaf,iter_start):
    global q_save, u_save, X_save, gNdot_save, gammaF_save, AV_save, corners_save
    global rho_infinity_initial, rho_inf, MAXITERn, MAXITERn_initial
    global iter, total_leaves

    g.write(f"  solve_new(leaf = {leaf}, iter_start = {iter_start}) is currently running.\n")

    iter = iter_start

    while iter<ntime:
        if not iter%100:
            print(f"iteration {iter}")
        # at this point, np.shape(q_save)[0] = total_leaves

        current_time = time.time()
        if current_time-start_time>(3600*max_hours):
            f.write(f'\n  Program quit because max execution time {max_hours} hours was exceeded.\n')
            raise MaxHoursAttained

        current_total_leaves = total_leaves

        while leaf < current_total_leaves:
            if not iter%100:
                print(f"leaf {leaf}")

            prev_X = X_save[leaf,:,iter-1]
            prev_AV = AV_save[leaf,:,iter-1]
            prev_q = q_save[leaf,:,iter-1]
            prev_u = u_save[leaf,:,iter-1]
            prev_gNdot = gNdot_save[leaf,:,iter-1]
            prev_gammaF = gammaF_save[leaf,:,iter-1]

            try: 

                X,AV,q,u,gNdot,gammaF = update(prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf)

                q_save[leaf,:,iter] = q
                u_save[leaf,:,iter] = u
                X_save[leaf,:,iter] = X
                gNdot_save[leaf,:,iter] = gNdot
                gammaF_save[leaf,:,iter] = gammaF
                AV_save[leaf,:,iter] = AV

                # update initial value
                rho_infinity_initial = rho_inf 
                # reset initial value
                MAXITERn = MAXITERn_initial

                # leaf will be zeroed out again
                # the purpose of this line is to go outside the while leaf < total_leaves loop
                leaf = leaf+1

            except ValueError as e:
                try: 
                    solve_bifurcation(leaf,iter)
                    leaf += 1
                except NoBifurcationConvergence:
                    try:
                        update_rho_inf()
                    except RhoInfInfiniteLoop:
                        # we cannot update rho_inf anymore we need to abandon this leaf  
                        # deleting leaf
                        total_leaves-=1
                        # decrement saved arrays
                        q_save = np.delete(q_save,leaf,0)
                        u_save = np.delete(u_save,leaf,0)
                        X_save = np.delete(X_save,leaf,0)
                        gNdot_save = np.delete(gNdot_save,leaf,0)
                        gammaF_save = np.delete(gammaF_save,leaf,0)
                        AV_save = np.delete(AV_save,leaf,0)
                        current_total_leaves = total_leaves-1
                        g.write(f"  Leaf {leaf} in iteration {iter} is now deleted. The total number of leaves becomes {total_leaves}.\n")
                        solve_new(0,iter) # try starting at leaf, not at zero
                        return

            except Exception as e:
                f.write(f"  The exception {e} is now raised at leaf {leaf} while calculating iteration {iter}.\n")
                raise e
            
        iter = iter+1
        leaf = 0

        if iter%10 == 0:
            save_arrays()


    return


def solve_bifurcation(leaf,iter):
    global q_save, u_save, X_save, gNdot_save, gammaF_save, AV_save, corners_save
    global MAXITERn
    global total_leaves

    prev_X = X_save[leaf,:,iter-1]
    prev_AV = AV_save[leaf,:,iter-1]
    prev_q = q_save[leaf,:,iter-1]
    prev_u = u_save[leaf,:,iter-1]
    prev_gNdot = gNdot_save[leaf,:,iter-1]
    prev_gammaF = gammaF_save[leaf,:,iter-1]

    unique_contacts,_ = update(prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf)

    n_unique_contacts = np.shape(unique_contacts)[0]
    nonconvergence_counter = 0 # number of nonconverged branches out of unique_contacts
    num_converged_leaves = 0
    g.write(f"    A total number of {n_unique_contacts} unique contacts was detected while calculating leaf {leaf} at iteration {iter}.\n")
    for k in range(n_unique_contacts):
        try:
            fixed_contact  = unique_contacts[k,:]
            X,AV,q,u,gNdot,gammaF = update(prev_X,prev_AV,prev_q,prev_u,prev_gNdot,prev_gammaF,leaf,fixed_contact)
            num_converged_leaves +=1

            if num_converged_leaves > 1:
                increment_saved_arrays(leaf)
                leaf = total_leaves # we are now on a new leaf that is the last leaf
                total_leaves+=1
                g.write(f"  A new leaf {leaf} was created at iteration {iter} so the total number of leaves is now increased to {total_leaves}.\n")

            q_save[leaf,:,iter] = q
            u_save[leaf,:,iter] = u
            X_save[leaf,:,iter] = X
            gNdot_save[leaf,:,iter] = gNdot
            gammaF_save[leaf,:,iter] = gammaF
            AV_save[leaf,:,iter] = AV

            if total_leaves > max_leaves:
                break

        except TypeError as e:
            print(f"Error {e} at iteration {iter} and leaf {leaf}.\n") # this error is raised because the leaf did not converge and update returned nothing      
            nonconvergence_counter = nonconvergence_counter+1
            if nonconvergence_counter == n_unique_contacts:
                # exception raised when None of the fixed contact regions converged
                # raise Exception
                nonconvergence_counter = 0
                if MAXITERn < 10:
                    # try to increase number of iterations
                    MAXITERn = 200
                    solve_bifurcation(leaf,iter)
                else:
                    raise NoBifurcationConvergence

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
    f.write(f"######\nnblocks = {n}, oscillation amplitude = {k}*{w[1]}, angular frequency = {ang_frq},\n")
    f.write(f"number of oscillations = {n_oscillations}, number of iterations per oscillation = {iters_per_oscillation},\n")
    f.write(f"Period of oscillation: {oscillation_period} sec/cycle.\n")
    f.write(f"Total duration of simulation: {tf} sec.\n\n")
    iter_start = 1
    leaf_start = 0
    total_leaves = 1
    solve_new(leaf_start,iter_start)
    # removing last added leaf_counter
    leaves_counter = leaves_counter-1
    # f.write(f'leaves_counter decremented to {leaves_counter}\n')
    # removing the last added block to q_save
    # q_save = q_save[0:np.shape(q_save)[0]-1,:,:]
    # f.write(f'q_save decremented to {np.shape(q_save)}\n')
except: 
    f.write(f"Failure at iteration {iter} while calculating leaf {leaves_counter}.\n")
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

    save_arrays()

    print("Saved.")
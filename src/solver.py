
from abc import ABC, abstractmethod
import numpy as np
from .farm import Farm
from .flow_field import FlowField
from .grid import TurbineGrid
from .turbine import axial_induction
from .wake_velocity.jensen import JensenVelocityDeficit

jensen_deficit_model = JensenVelocityDeficit()

def sequential_solver(farm: Farm, flow_field: FlowField) -> None:

    grid = TurbineGrid(farm.coords, flow_field.reference_turbine_diameter, flow_field.reference_wind_height, 5)
    flow_field.initialize_velocity_field(grid)

    # <<interface>>
    jensen_args = jensen_deficit_model.prepare_function(
        grid,
        farm.turbines[0],
        flow_field
    )

    # Calculate the wake deflection field
    # deflection = np.array([0.0])

    total_deficit = np.zeros(np.shape(grid.x))

    # turbines = [
    #     # Wind direction 1
    #     Turbine1, # 0
    #     Turbine2, # 1
    #     Turbine3, # 2
    #     Turbine4, # 3
    # ]

    # turbines = [
    #     # Wind direction 2
    #     Turbine2, # 1
    #     Turbine1, # 0
    #     Turbine4,
    #     Turbine3,
    # ]

    # for wind direction 1:

    # This is u_wake
    velocity_deficit = np.zeros_like(flow_field.u_initial)
    
    # Calculate the velocity deficit sequentially from upstream to downstream turbines
    for i in range(grid.n_turbines - 1):

        jensen_args['u'] = flow_field.u_initial - velocity_deficit
        c = jensen_deficit_model.function(i, **jensen_args)

        u = flow_field.u_initial - velocity_deficit
        u[0, i+1:, :, :] = 0
        turbine_ai = axial_induction(
            velocities=u[0, :, :, :],
            yaw_angle=grid.n_turbines*[0.0],
            fCt=grid.n_turbines*[farm.turbines[0].fCt],
            ix_filter=[i]
        )
        turbine_ai = turbine_ai * np.ones((grid.n_turbines, grid.grid_resolution, grid.grid_resolution))

        # flow_field.u[i] = flow_field.u[i-1] * (1 - 2 * turbine_ai * deficit)
        # print(turbine_ai)
        # print(c)
        # print(np.shape(flow_field.u_initial[:, i, :, :] ))
        turb_u_wake = 2 * turbine_ai * c * flow_field.u_initial[0, :, :, :] 
        # flow_field.u[i, :, :, :] = flow_field.u_initial[i, :, :, :] - turb_u_wake

        velocity_deficit[0, :, :, :] = np.sqrt((velocity_deficit[0, :, :, :] ** 2) + (turb_u_wake ** 2))

    flow_field.u = flow_field.u_initial - velocity_deficit
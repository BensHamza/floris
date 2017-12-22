"""
Copyright 2017 NREL

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
"""

from .BaseObject import BaseObject
import numpy as np
from scipy.interpolate import interp1d
from scipy.interpolate import griddata


class Turbine(BaseObject):

    def __init__(self, instance_dictionary):

        super().__init__()

        # constants
        self.grid_point_count = 16
        self.velocities = [0] * self.grid_point_count
        self.grid = [0] * self.grid_point_count

        self.description = instance_dictionary["description"]

        properties = instance_dictionary["properties"]
        self.rotor_diameter = properties["rotor_diameter"]
        self.hub_height = properties["hub_height"]
        self.blade_count = properties["blade_count"]
        self.pP = properties["pP"]
        self.pT = properties["pT"]
        self.generator_efficiency = properties["generator_efficiency"]
        self.eta = properties["eta"]
        self.power_thrust_table = properties["power_thrust_table"]
        self.blade_pitch = properties["blade_pitch"]
        self.yaw_angle = properties["yaw_angle"]
        self.tilt_angle = properties["tilt_angle"]
        self.TSR = properties["TSR"]

        # these attributes need special attention
        self.rotor_radius = self.rotor_diameter / 2.0
        self.yaw_angle = np.radians(self.yaw_angle)
        self.tilt_angle = np.radians(self.tilt_angle)

        # initialize derived attributes
        self.fCp, self.fCt = self._CpCtWs()
        self.grid = self._create_swept_area_grid()
        self.velocities = [-1] * 16  # initialize to an invalid value until calculated

        # calculated attributes are
        # self.Ct         # Thrust Coefficient
        # self.Cp         # Power Coefficient
        # self.power      # Power (W) <-- True?
        # self.aI         # Axial Induction
        # self.TI         # Turbulence intensity at rotor
        # self.windSpeed  # Windspeed at rotor

        # self.usePitch = usePitch
        # if usePitch:
        #     self.Cp, self.Ct, self.betaLims = CpCtpitchWs()
        # else:
        #     self.Cp, self.Ct = CpCtWs()

    # Private methods

    def _create_swept_area_grid(self):
        # TODO: add validity check:
        # rotor points has a minimum in order to always include points inside
        # the disk ... 2?
        #
        # the grid consists of the y,z coordinates of the discrete points which
        # lie within the rotor area: [(y1,z1), (y2,z2), ... , (yN, zN)]

        # update:
        # using all the grid point because that how roald did it.
        # are the points outside of the rotor disk used later?

        # determine the dimensions of the square grid
        num_points = int(np.round(np.sqrt(self.grid_point_count)))
        # syntax: np.linspace(min, max, n points)
        horizontal = np.linspace(-self.rotor_radius, self.rotor_radius, num_points)
        vertical = np.linspace(-self.rotor_radius, self.rotor_radius, num_points)

        # build the grid with all of the points
        grid = [(h, vertical[i]) for i in range(num_points) for h in horizontal]

        # keep only the points in the swept area
        # grid = [point for point in grid if np.hypot(point[0], point[1]) < self.rotor_radius]

        return grid

    def _calculate_cp(self):
        return self.fCp(self.get_average_velocity())

    def _calculate_ct(self):
        return self.fCt(self.get_average_velocity())

    def _calculate_power(self):
        cptmp = self.Cp \
                * np.cos(self.yaw_angle)**self.pP \
                * np.cos(self.tilt_angle)**self.pT

        #TODO: air density (1.225) is hard coded below. should this be variable in the flow field?
        return 0.5 * 1.225 * (np.pi * self.rotor_radius**2) * cptmp * self.generator_efficiency * self.get_average_velocity()**3

    def _calculate_ai(self):
        return 0.5 / np.cos(self.yaw_angle) \
               * (1 - np.sqrt(1 - self.Ct * np.cos(self.yaw_angle) ) )

    def _calculate_turbulence_intensity(self, flowfield, wake, turbine_coord, wake_coord, turbine_wake):

        D = self.rotor_diameter
        TI_initial = flowfield.turbulence_intensity

        # turbulence intensity parameters stored in floris.json
        #TI_i = wake.added_turbulence_intensity["TI_initial"]
        #TI_constant = wake.added_turbulence_intensity["TI_constant"]
        #TI_ai = wake.added_turbulence_intensity["TI_ai"]
        #TI_downstream = wake.added_turbulence_intensity["TI_downstream"]
        TI_i = 0.1
        TI_constant = 0.73
        TI_ai = 0.8
        TI_downstream = -0.275

        # turbulence intensity calculation based on Crespo et. al.
        TI_calculation = TI_constant*(turbine_wake.aI**TI_ai)*(TI_initial**TI_i)*((turbine_coord.x - wake_coord.x)/D)**(TI_downstream)

        return np.sqrt(TI_calculation**2 + self.TI**2)

    def _CpCtWs(self):
        cp = self.power_thrust_table["power"]
        ct = self.power_thrust_table["thrust"]
        windspeed = self.power_thrust_table["wind_speed"]

        fCpInterp = interp1d(windspeed, cp)
        fCtInterp = interp1d(windspeed, ct)

        def fCp(Ws):
            return max(cp) if Ws < min(windspeed) else fCpInterp(Ws)

        def fCt(Ws):
            return 0.99 if Ws < min(windspeed) else fCtInterp(Ws)

        return fCp, fCt

    def _calculate_swept_area_velocities(self, flowfield, local_wind_speed, coord, x, y, z):
        """
            TODO: explain these velocities
            initialize the turbine disk velocities used in the 3D model based on shear using the power log law.
        """
        #return [local_wind_speed * ((self.hub_height + g[1]) / self.hub_height)**shear for g in self.grid]

        dx = (np.max(x) - np.min(x)) / flowfield.grid_x_resolution
        mask = (x < coord.x + dx) & (x > (coord.x - dx)) \
             & (y < (coord.y + self.rotor_radius)) & (y > (coord.y - self.rotor_radius)) \
             & (z > (self.hub_height - self.rotor_radius)) & (z < (self.hub_height + self.rotor_radius))

        # only keep points relevant to the rotor
        u_at_turbine = local_wind_speed[mask]
        x_grid = x[mask]
        y_grid = y[mask]
        z_grid = z[mask]

        # interpolate from the flow field to get the flow field at the grid points
        data = np.zeros(len(self.grid))
        for i,pt in enumerate(self.grid):
            data[i] = griddata((x_grid,y_grid,z_grid), u_at_turbine, (coord.x,coord.y+pt[0],self.hub_height+pt[1]),method='nearest')

        return data

    # Public methods

    def update_quantities(self, u_wake, coord, rotated_map, flowfield, rotated_x, rotated_y, rotated_z):

        # extract relevant quantities
        wind_speed          = flowfield.wind_speed
        local_wind_speed    = flowfield.initial_flowfield - u_wake

        # update turbine quantities
        self.initial_velocities = self._calculate_swept_area_velocities(flowfield, flowfield.initial_flowfield, coord, rotated_x, rotated_y, rotated_z)
        self.velocities         = self._calculate_swept_area_velocities(flowfield, local_wind_speed, coord, rotated_x, rotated_y, rotated_z)
        self.Cp                 = self._calculate_cp()
        self.Ct                 = self._calculate_ct()
        self.power              = self._calculate_power()
        self.aI                 = self._calculate_ai()
        self.windSpeed          = self.get_average_velocity()

    def set_yaw_angle(self, angle):
        """
        Sets the turbine yaw angle
        inputs:
            angle: float - new yaw angle in degrees
        outputs:
            none
        """
        self.yaw_angle = np.radians(angle)

    def get_grid(self):
        return self.grid

    def get_average_velocity(self):
        return np.mean(self.velocities)

"""Stimulus Factory Plot module."""

import numpy as np

from bluenaas.domains.simulation import StimulationPlotConfig


class StimulusFactoryPlot:
    """Generates stimuli preview plot data."""

    def __init__(self, params: StimulationPlotConfig, threshold_current: int):
        from bluecellulab.stimulus.factory import (
            StimulusFactory,  # pylint: disable=import-outside-toplevel
        )

        self.dt = 0.1
        self.factory = StimulusFactory(dt=self.dt)

        self.protocol_name = params.stimulus_protocol
        self.threshold_current = threshold_current
        self.amplitudes = params.amplitudes

        if not isinstance(self.amplitudes, list):
            raise ValueError("Amplitudes must be a list")

    @property
    def stim_fn(self):
        """Exposes the stimulus function to call based on stimulus chosen."""
        protocol_mapping = {
            "iv": self.factory.iv,
            "fire_pattern": self.factory.fire_pattern,
            "ap_waveform": self.factory.ap_waveform,
            "idrest": self.factory.idrest,
        }
        return protocol_mapping[self.protocol_name]

    def _get_stim_name(self, amplitude):
        return f"{self.protocol_name.upper()}_{amplitude}"

    def _get_time_by_index(self, times):
        def get_time_for(index):
            return int(times[index])

        return get_time_for

    def _get_plot_data(self, response):
        # get the x and y axis to plot the breaking points
        # even though we have 4 points (initial, up, down, final), to make the plot looks square _∏_
        # we need to add 2 more points just before up and right after down breaking points

        unique_elements = np.unique(response.current)
        get_time_for = self._get_time_by_index(response.time)

        if unique_elements.size == 1:
            # Case 1: Since all current values are same, send only the first and the last to create a straight line
            return {
                "x": [response.time[0], response.time[-1]],
                "y": [response.current[0], response.current[-1]],
            }

        if unique_elements.size != 2:
            raise Exception("current has not _∏_ shape")

        down_value = unique_elements[0]
        up_value = unique_elements[1]
        down_indices = np.where(response.current == down_value)[0]
        up_indices = np.where(response.current == up_value)[0]
        first_up, last_up = up_indices[0], up_indices[-1]
        first_down, last_down = down_indices[0], down_indices[-1]

        is_up_clamp = first_up > first_down

        if is_up_clamp:
            # Case 2: Top clamp shape
            #     ___________
            #     |         |
            #     |         |
            #     |         |
            # ----          ----

            return {
                "x": [
                    get_time_for(first_down),
                    get_time_for(first_up - 1),
                    get_time_for(first_up),
                    get_time_for(last_up),
                    get_time_for(last_up + 1),
                    get_time_for(last_down),
                ],
                "y": [
                    down_value,
                    down_value,
                    up_value,
                    up_value,
                    down_value,
                    down_value,
                ],
            }
        else:
            # Case 3: Reverse clamp shape
            # ----           ----
            #     |         |
            #     |         |
            #     |         |
            #     ___________
            return {
                "x": [
                    get_time_for(first_up),
                    get_time_for(first_down - 1),
                    get_time_for(first_down),
                    get_time_for(last_down),
                    get_time_for(last_down + 1),
                    get_time_for(last_up),
                ],
                "y": [up_value, up_value, down_value, down_value, up_value, up_value],
            }

    def apply_stim(self):
        """Generate plot data based on  stimuli parameters."""
        final_data = []
        for amplitude in self.amplitudes:
            label = self._get_stim_name(amplitude)
            response = self.stim_fn(
                self.threshold_current,
                threshold_percentage=(amplitude / self.threshold_current)
                * 100,  # Threshold current cannot be zero
            )
            plot_data = self._get_plot_data(response)
            plot_data.update({"name": label, "amplitude": amplitude})
            final_data.append(plot_data)

        return final_data

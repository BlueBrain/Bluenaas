from bluenaas.domains.simulation import (
    WORKER_TASK_STATES,
)

MESSAGE_WAIT_TIME_SECONDS: float = 5.0
POLLING_INTERVAL_SECONDS: float = 0.01
SIMULATION_TIMEOUT_SECONDS: float = 15 * 60

task_state_descriptions: dict[WORKER_TASK_STATES, str] = {
    "INIT": "Simulation is captured by the system",
    "PROGRESS": "Simulation is currently in progress.",
    "PENDING": "Simulation is waiting for execution.",
    "STARTED": "Simulation has started executing.",
    "SUCCESS": "The simulation completed successfully.",
    "FAILURE": "The simulation has failed.",
    "REVOKED": "The simulation has been canceled.",
    "PARTIAL_SUCCESS": "The simulation has been completed but not fully successful.",
}

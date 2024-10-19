import psutil


def get_cpus_in_use():
    """
    Retrieves the current CPU usage statistics.

    This function calculates the number of CPUs currently in use based on the
    percentage of CPU usage and returns relevant statistics.

    Returns:
        dict: A dictionary containing CPU usage statistics:
            - cpus_in_use (int): The number of CPUs currently in use, rounded to the nearest whole number.
            - total_cpus (int): The total number of logical CPUs available.
            - cpu_usage_percent (float): The percentage of CPU usage over a one-second interval.
    """

    cpu_usage_percent = psutil.cpu_percent(interval=1)
    total_cpus = psutil.cpu_count()
    cpus_in_use = (cpu_usage_percent / 100) * total_cpus

    return {
        "cpus_in_use": round(cpus_in_use),
        "total_cpus": total_cpus,
        "cpu_usage_percent": cpu_usage_percent,
    }

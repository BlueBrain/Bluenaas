from celery.result import AsyncResult


def get_last_progress_time(task: AsyncResult, lst: list[int]):
    hashed_record = None
    should_update = False

    if task:
        task_info = getattr(task, "info", None)
        if task_info and isinstance(task_info, dict):
            result = task_info.get("result", None)
            if result is not None and isinstance(result, dict):
                hashed_record = result.get("hash", None)

    if hashed_record not in lst:
        lst.append(hashed_record)
        should_update = True

    return should_update

class SharedMemoryError(Exception):
    pass


class BackendUnavailable(SharedMemoryError):
    pass


class LockTimeout(SharedMemoryError):
    pass

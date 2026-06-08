class MemoryPoolError(Exception):
    pass


class BackendUnavailable(MemoryPoolError):
    pass


class SerializationError(MemoryPoolError):
    pass

"""Trabajo de CPU (Argon2) fuera del bucle de eventos, sin pasar de un hilo por núcleo.

Con más hilos que núcleos, los hashes de Argon2 compiten por la memoria y tardan varias
veces más todos a la vez (medido con perf/accounts.js en T023): mejor que esperen turno.
"""

import os
from collections.abc import Callable

import anyio

# os.cpu_count() ve los núcleos de la máquina, no la cuota de CPU del contenedor: en una
# tarea con menos vCPU que el host, el tope queda alto. Se revisa con la infraestructura.
_limiter = anyio.CapacityLimiter(os.cpu_count() or 1)


async def run_cpu_bound[**P, T](function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    return await anyio.to_thread.run_sync(lambda: function(*args, **kwargs), limiter=_limiter)

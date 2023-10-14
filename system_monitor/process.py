import psutil
for proc in psutil.process_iter():
    try:
        mem = proc.memory_full_info()
    except psutil.ZombieProcess:
        mem = "Zombie"
    except psutil.AccessDenied:
        mem = "Access denied"

    try:
        conn = proc.connections()
        exe = proc.exe()
    except psutil.AccessDenied:
        conn = "Access denied"
        exe = "Access denied"

    print(
        proc.pid,
        proc.status(),
        proc.username(),
        mem,
        proc.name(),
        exe,
        proc.cmdline(),
        proc.create_time(),
        proc.is_running(),
        conn,
    )
import subprocess
import threading

from typing import List
from glitch.repair.interactive.tracer.parser import parse_tracer_output
from glitch.repair.interactive.tracer.model import get_syscall_with_type, Syscall
from glitch.repair.interactive.tracer.transform import get_affected_paths, get_file_system_state

class STrace(threading.Thread):
    def __init__(self, pid: str):
        threading.Thread.__init__(self)
        self.syscalls: List[Syscall]  = []
        self.pid = pid

    def run(self) -> None:
        proc = subprocess.Popen(
            ["sudo", "strace", "-v", "-s", "65536", "-e", 
             "trace=file", "-f", "-p", self.pid], 
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
        )

        for line in proc.stdout:
            if (
                line.startswith("strace: Process") 
                or "+++ exited with" in line
                or "--- SIG" in line
            ):
                continue
            syscall = get_syscall_with_type(parse_tracer_output(line))
            if "/bin/synth-glitch" in syscall.args:
                # TODO don't break and just update
                break
            self.syscalls.append(syscall)

        return self.syscalls
    
pid = "58988"
workdir = subprocess.check_output(["pwdx", pid]).decode("utf-8").split(": ")[1].strip()
affected_paths = get_affected_paths(workdir, STrace(pid).run())
file_system = get_file_system_state(affected_paths)

for path, state in file_system.state.items():
    print(path, state)
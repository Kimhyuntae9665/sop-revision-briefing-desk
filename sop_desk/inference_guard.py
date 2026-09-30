# Copied safety subset from project 01 commit 721949d17891bbb009b31b19a20469bd0946991c (MIT).
"""Bounded single-flight localhost Ollama client. No tools or server mutation."""
import json,time,threading,urllib.request,urllib.error,uuid,fcntl,os,stat
from pathlib import Path
MODEL="qwen3:4b"
BASE="http://127.0.0.1:11434"
_lock=threading.Lock()
_disabled_reason=None
def _configured_inference_lock(environ=None, home=None):
    """Both project clients use the same user-owned lease, never clone ancestry."""
    environ = os.environ if environ is None else environ
    configured = environ.get("AX_LAB_INFERENCE_LOCK")
    if configured is not None:
        if not isinstance(configured, str) or not configured or "\x00" in configured:
            raise RuntimeError("inference_lock_configuration_invalid")
        path = Path(configured)
        if not path.is_absolute():
            raise RuntimeError("inference_lock_configuration_invalid")
        return path
    user_home = Path.home() if home is None else Path(home)
    if not user_home.is_absolute():
        raise RuntimeError("inference_lock_configuration_invalid")
    return user_home / ".cache" / "ax-lab" / "runtime" / "inference.lock"


INFERENCE_LOCK = _configured_inference_lock()
MAX_LOCK_PARENT_CREATION = 3


def _open_inference_lease():
    """Create at most three private directories and open a safe shared lock."""
    path = Path(INFERENCE_LOCK)
    if not path.is_absolute():
        raise RuntimeError("inference_lock_configuration_invalid")
    fd = None
    directory_fd = None
    try:
        missing = []
        parent = path.parent
        cursor = parent
        while not cursor.exists():
            missing.append(cursor)
            if len(missing) > MAX_LOCK_PARENT_CREATION:
                raise OSError("too_many_missing_lock_parents")
            cursor = cursor.parent
        for directory in reversed(missing):
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError:
                if not directory.is_dir():
                    raise
        directory_fd = os.open(str(parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        metadata = os.fstat(directory_fd)
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077):
            raise OSError("unsafe_lock_directory")
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     0o600, dir_fd=directory_fd)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise OSError("unsafe_lock_file")
        os.fchmod(fd, 0o600)
        lease = os.fdopen(fd, "a")
        fd = None
        return lease
    except (OSError, ValueError):
        raise RuntimeError("inference_lock_unavailable") from None
    finally:
        if fd is not None:
            os.close(fd)
        if directory_fd is not None:
            os.close(directory_fd)

# An HTTP timeout does not prove server-side inference finished. Persist a
# shared fail-closed barrier so another clone/project/process cannot retry.
_timeout_guard_leases=[]
def _timeout_marker():
    return Path(str(INFERENCE_LOCK)+".blocked")

def _check_timeout_barrier():
    if os.path.lexists(_timeout_marker()):
        raise RuntimeError("inference_blocked_after_timeout: verify owned request completion and explicitly recover the shared runtime")

def _latch_timeout(lease):
    global _disabled_reason
    _disabled_reason="inference_disabled_after_timeout: verify owned request completion and explicitly recover the shared runtime"
    directory_fd=None
    fd=None
    try:
        directory_fd=os.open(str(Path(INFERENCE_LOCK).parent),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        metadata=os.fstat(directory_fd)
        if metadata.st_uid!=os.geteuid() or stat.S_IMODE(metadata.st_mode)&0o077:
            raise OSError("unsafe_timeout_directory")
        try:
            fd=os.open(_timeout_marker().name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,0o600,dir_fd=directory_fd)
        except FileExistsError:
            return
        os.write(fd,b"HTTP timeout: server completion unverified; manual shared-runtime recovery required.\n")
        os.fsync(fd)
    except OSError:
        # Keep the OS lease held in this process if persistence is unavailable.
        # Never pretend this fallback survives process termination.
        _timeout_guard_leases.append(lease)
        _disabled_reason += "; barrier_write_failed_keep_process_alive"
    finally:
        if fd is not None:os.close(fd)
        if directory_fd is not None:os.close(directory_fd)

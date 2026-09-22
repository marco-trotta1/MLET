"""Verify the recorded audit code and its pandas compatibility patch."""
from pathlib import Path
import hashlib


def verify_audit_code(current: Path, recorded_hash: str) -> None:
    current_bytes = current.read_bytes()
    if hashlib.sha256(current_bytes).hexdigest() == recorded_hash:
        return
    snapshot = current.with_name("ml_transfer_audit.recorded.py").read_bytes()
    if hashlib.sha256(snapshot).hexdigest() != recorded_hash:
        raise ValueError("The recorded audit snapshot does not match its receipt")
    patched = snapshot
    for variable, group in [("fit", "a"), ("val", "b")]:
        old = f"{variable} = train.group.isin({group}).to_numpy()".encode()
        new = f"{variable} = train.group.isin({group}).to_numpy(copy=True)".encode()
        if patched.count(old) != 1:
            raise ValueError("The recorded audit mask is missing or duplicated")
        patched = patched.replace(old, new)
    if current_bytes != patched:
        raise ValueError("The audit code differs beyond the verified pandas compatibility patch")

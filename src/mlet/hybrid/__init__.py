"""Non-serving hybrid physics/ML modelling scaffold.

Nothing in this package may be imported by the outlook, source, experiment, or
CLI modules. It exists so that hybrid modelling can be developed and reviewed
without any path from it to a published artifact. ``scripts/verify.sh`` and
the hybrid isolation tests enforce the boundary.

The scaffold is pure NumPy. PyTorch appears only in ``torch_adapter``, behind
the optional ``mlet[hybrid]`` extra.
"""

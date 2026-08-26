"""Standalone entrypoint for the Grim v26 rules pilot."""
from policies.v26_reexport.main import agent as _policy


def competition_entrypoint(obs):
    return _policy(obs)

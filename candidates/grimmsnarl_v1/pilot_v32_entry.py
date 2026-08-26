"""Standalone entrypoint for the Grim v32 rules pilot."""
from policies.v32.main import agent as _policy


def competition_entrypoint(obs):
    return _policy(obs)

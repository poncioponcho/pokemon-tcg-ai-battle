"""Standalone entrypoint for the Grim v22 rules pilot."""
from policies.v22.main import agent as _policy


def competition_entrypoint(obs):
    return _policy(obs)

"""Standalone entrypoint for the Grim v28 rules pilot."""
from policies.v28.main import agent as _policy


def competition_entrypoint(obs):
    return _policy(obs)

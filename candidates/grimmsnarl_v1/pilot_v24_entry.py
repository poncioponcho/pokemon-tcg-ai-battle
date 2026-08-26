"""Standalone entrypoint for the Grim v24 rules pilot."""
from policies.rule_v24.main import agent as _policy


def competition_entrypoint(obs):
    return _policy(obs)

# SRE Lab Notes

> **Version note:** This file records the earlier `main` implementation baseline. The completed Platform Engineering V2 evidence supersedes its open-status wording; start with [V2 overview](V2_OVERVIEW.md) and the linked V2 implementation. V2 has not been merged into `main`.

## SLI

Successful HTTP requests divided by total HTTP requests.

## SLO

Lab target: 99.9% successful requests over the selected evaluation window.

## Error budget

0.1% unsuccessful requests over the same window.

These are learning-lab objectives, not historical production guarantees.

## Required exercises
- failed image rollout and rollback
- pod restart investigation
- readiness/liveness behavior
- database-unavailable runbook review
- metrics and alert inspection

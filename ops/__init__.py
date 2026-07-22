"""Scheduled operational checks for the FD estate.

Runs as a Railway cron service off this same repo (see ops/daily.py), so the
checks watch our services from *outside* the machines they run on - a watchdog
on a box can never report that box being down.
"""

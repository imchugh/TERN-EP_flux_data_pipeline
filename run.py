#!/usr/bin/env python3
"""Entry point for the flux data pipeline task runner."""

import argparse
import sys

from tasks.tasks import run_task


def main():

    parser = argparse.ArgumentParser(description='Run a pipeline task.')
    parser.add_argument('task', help='Registered task name')
    parser.add_argument(
        '--site', default=None,
        help='Site name (site-scoped tasks only; omit to run all CSV-enabled sites)',
        )
    args = parser.parse_args()

    try:
        run_task(task=args.task, site=args.site)
    except NotImplementedError as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

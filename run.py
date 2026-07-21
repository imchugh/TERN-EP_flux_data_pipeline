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
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Forward a dry-run flag to the task (only supported by some tasks)',
        )
    args = parser.parse_args()

    try:
        run_task(task=args.task, site=args.site, dry_run=args.dry_run)
    except NotImplementedError as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

# (C) Datadog, Inc. 2019
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
import linecache
import os
from datetime import datetime

from binary import BinaryUnits, convert_units

try:
    import tracemalloc
except ImportError:
    tracemalloc = None


def get_timestamp_filename(prefix):
    return '{}_{}'.format(prefix, datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%S_%f'))


def get_unit(unit):
    return getattr(BinaryUnits, unit.upper().replace('I', ''), BinaryUnits.B)


def format_units(unit, amount, unit_repr):
    # Dynamic based on the number of bytes
    if unit is None:
        unit = get_unit(unit_repr)

    if unit < BinaryUnits.KB:
        return '%d' % amount, unit_repr
    elif unit < BinaryUnits.MB:
        return '%.2f' % amount, unit_repr
    else:
        return '%.3f' % amount, unit_repr


def get_unit_formatter(unit):
    if unit == 'highest':
        unit = None
    else:
        unit = get_unit(unit)

    return lambda n: format_units(unit, *convert_units(n, to=unit))


def write_pretty_top(path, snapshot, unit_formatter, key_type, limit):
    # Modified version of https://docs.python.org/3/library/tracemalloc.html#pretty-top
    top_stats = snapshot.statistics(key_type, cumulative=False)

    with open(path, 'w', encoding='utf-8') as f:
        f.write('Top {} lines\n'.format(limit))

        for index, stat in enumerate(top_stats[:limit], 1):
            frame = stat.traceback[0]

            # If possible, replace `/path/to/datadog_checks/check/file.py` with `check/file.py`
            filename = frame.filename
            path_parts = filename.split(os.sep)
            if 'datadog_checks' in path_parts:
                check_package_parts = path_parts[path_parts.index('datadog_checks') + 1:]
                if check_package_parts:
                    filename = os.sep.join(check_package_parts)

            amount, unit = unit_formatter(stat.size)
            f.write('#{}: {}:{}: {} {}\n'.format(index, filename, frame.lineno, amount, unit))

            line = linecache.getline(frame.filename, frame.lineno).strip()
            if line:
                f.write('    {}\n'.format(line))

        other = top_stats[limit:]
        if other:
            size = sum(stat.size for stat in other)
            amount, unit = unit_formatter(size)
            f.write('{} other: {} {}\n'.format(len(other), amount, unit))

        total = sum(stat.size for stat in top_stats)
        amount, unit = unit_formatter(total)
        f.write('Total allocated size: {} {}\n'.format(amount, unit))


def profile_memory(f, config, args=(), kwargs=None):
    if kwargs is None:
        kwargs = {}

    depth = config.get('profile_memory_depth', 25)
    tracemalloc.start(depth)

    try:
        f(*args, **kwargs)
        snapshot = tracemalloc.take_snapshot()
    finally:
        tracemalloc.stop()

    verbose = bool(config.get('profile_memory_verbose', 0))
    if not verbose:
        snapshot = snapshot.filter_traces(
            (
                tracemalloc.Filter(False, '<frozen importlib._bootstrap>'),
                tracemalloc.Filter(False, '<unknown>'),
                tracemalloc.Filter(False, __file__),
            )
        )

    location = config.get('profile_memory', '')
    sort_by = config.get('profile_memory_sorting', 'lineno')
    lines = config.get('profile_memory_lines', 40)
    unit = config.get('profile_memory_unit', 'highest')

    # First, write the prettified snapshot
    snapshot_dir = os.path.join(location, 'snapshots')
    if not os.path.isdir(snapshot_dir):
        os.makedirs(snapshot_dir)

    new_snapshot = get_timestamp_filename('snapshot')
    write_pretty_top(os.path.join(snapshot_dir, new_snapshot), snapshot, get_unit_formatter(unit), sort_by, lines)

    # Then, compute the diff if there was a previous run
    previous_snapshot_dump = os.path.join(location, 'last-snapshot')
    if os.path.isfile(previous_snapshot_dump):
        diff_dir = os.path.join(location, 'diffs')
        if not os.path.isdir(diff_dir):
            os.makedirs(diff_dir)

        previous_snapshot = tracemalloc.Snapshot.load(previous_snapshot_dump)
        top_stats = snapshot.compare_to(previous_snapshot, key_type=sort_by, cumulative=False)

        # and write it
        new_diff = get_timestamp_filename('diff')
        with open(os.path.join(diff_dir, new_diff), 'w') as fd:
            for stat in top_stats[:lines]:
                fd.write('{}\n'.format(stat))

    # Finally, dump the current snapshot for doing a diff on the next run
    snapshot.dump(previous_snapshot_dump)

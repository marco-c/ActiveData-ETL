# encoding: utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Author: Tyler Blair (tblair@cs.dal.ca)
#

"""
Parses an lcov-generated coverage file and converts it to the JSON format used by other coverage outputs.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

import sys
import json
from copy import copy

from activedata_etl.imports.cxx_demangler import demangle
from pyLibrary import convert
from pyLibrary.maths import Math

from pyLibrary.debugs.logs import Log

from pyLibrary.env.files import File

from pyLibrary.dot import Null, Dict, set_default

# EXAMPLE OUTPUT RECORD
#     {
#         "test": {
#             "name": test_name,
#             "url": obj.testUrl
#         },
#         "source": {
#             "file": file_info,
#             "method": {
#                 "name": method_name,
#                 "covered": [{"line": c} for c in method_covered],
#                 "uncovered": method_uncovered,
#                 "total_covered": len(method_covered),
#                 "total_uncovered": len(method_uncovered),
#                 "percentage_covered": method_percentage_covered,
#             }
#         },
#         "etl": {
#             "id": count(),
#             "source": parent_etl,
#             "type": "join",
#             "machine": machine_metadata,
#             "timestamp": Date.now()
#         }
#     }
from pyLibrary.queries import jx


def parse_lcov_coverage(source_key, test_suite, stream):
    """
    Parses lcov coverage from a stream
    :param stream:
    :return:
    """
    # XXX BRDA, BRF, BFH not implemented because not used in the output

    while(True):
        record = Dict(test={"suite": test_suite})
        methods = Dict()
        all_covered = set()
        all_uncovered = set()

        for line in stream:
            line = unicode(line.strip())
            if not line:
                continue

            if line == 'end_of_record':
                break

            cmd, data = line.split(":", 1)

            if cmd == 'TN':
                if data.strip():
                    record.test.name = data
            elif cmd == 'SF':
                record.source.file.name = data
            elif cmd == 'FNF':
                functions_found = int(data)
            elif cmd == 'FNH':
                functions_hit = int(data)
            elif cmd == 'LF':
                lines_found = int(data)
            elif cmd == 'LH':
                lines_hit = int(data)
            elif cmd == 'DA':
                line_number, execution_count = data.split(',')

                if execution_count == '0':
                    all_uncovered.add(int(line_number))
                else:
                    all_covered.add(int(line_number))
            elif cmd == 'FN':
                first_line, function_name = data.split(',')
                name, params, sig = demangle(function_name)
                full_name = name + (params if params else "(" + sig + ")")
                methods[full_name].name = full_name
                methods[full_name].first_line = int(first_line)
            elif cmd == 'FNDA':
                execution_count, function_name = data.split(',')
                execution_count = int(execution_count)
                if execution_count:
                    name, params, sig = demangle(function_name)
                    full_name = name + (params if params else "(" + sig + ")")
                    methods[full_name].name = full_name
                    methods[full_name].execution_count = execution_count
            else:
                Log.warning('Unsupported cmd {{cmd}} with data {{data}}', cmd=cmd, data=data)

        remaining_covered = copy(all_covered)
        remaining_uncovered = copy(all_uncovered)

        max_line = Math.MAX([Math.MAX(all_covered), Math.MAX(all_uncovered)]) + 1
        sorted_methods = jx.sort(methods.values(), "first_line") + [{"first_line": max_line}]
        for i, method_info in enumerate(sorted_methods[:-1]):
            method_info.last_line = sorted_methods[i + 1].first_line
            all_method_lines = set(range(method_info.first_line, method_info.last_line))
            remaining_covered -= all_method_lines
            remaining_uncovered -= all_method_lines
            method_info.covered = [{"line": l} for l in sorted(all_covered & all_method_lines)]
            method_info.uncovered = sorted(all_uncovered & all_method_lines)
            method_info.total_covered = len(method_info.covered)
            method_info.total_uncovered = len(method_info.uncovered)
            if method_info.total_covered:
                method_info.percentage_covered = method_info.total_covered / (method_info.total_covered + method_info.total_uncovered)
            else:
                method_info.percentage_covered = 0.0
            yield set_default({"source": {"method": method_info}}, record)

        if remaining_covered:
            Log.error("not expected")

        record.source.method.covered = [{"line": l} for l in sorted(remaining_covered)]
        record.source.method.uncovered = sorted(remaining_uncovered)
        record.source.method.total_covered = len(remaining_covered)
        record.source.method.total_uncovered = len(remaining_uncovered)
        record.source.method.percentage_covered = 0

        yield record  # HAS NO METHOD


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: %s <lcov coverage file>' % sys.argv[0])
        sys.exit(1)

    file_path = sys.argv[1]

    parsed = parse_lcov_coverage(Null, "test", File(file_path))
    output = File("output.json").delete()
    for p in parsed:
        output.append(convert.value2json(p))
    # Log.note("{{output}}", output=list(parsed))

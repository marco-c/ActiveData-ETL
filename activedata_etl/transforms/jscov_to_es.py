# encoding: utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Author: Trung Do (chin.bimbo@gmail.com)
#
from __future__ import division
from __future__ import unicode_literals

import taskcluster

from mohg.repos.changesets import Changeset
from mohg.repos.revisions import Revision
from pyLibrary import convert
from pyLibrary.debugs.logs import Log, machine_metadata
from pyLibrary.dot import wrap, Dict, unwraplist, set_default
from pyLibrary.env import http
from pyLibrary.jsons import stream
from pyLibrary.strings import expand_template
from pyLibrary.times.dates import Date
from pyLibrary.times.timer import Timer
from activedata_etl import etl2key
from activedata_etl.transforms import EtlHeadGenerator

STATUS_URL = "https://queue.taskcluster.net/v1/task/{{task_id}}"
ARTIFACTS_URL = "https://queue.taskcluster.net/v1/task/{{task_id}}/artifacts"
ARTIFACT_URL = "https://queue.taskcluster.net/v1/task/{{task_id}}/artifacts/{{path}}"
RETRY = {"times": 3, "sleep": 5}


def process(source_key, source, destination, resources, please_stop=None):
    """
    This transform will turn a pulse message containing info about a jscov artifact on taskcluster
    into a list of records of method coverages. Each record represents a method in a source file, given a test.

    :param source_key: The key of the file containing the pulse messages in the source pulse message bucket
    :param source: The source pulse messages, in a batch of (usually) 100
    :param destination: The destination for the transformed data
    :param resources: not used
    :param please_stop: The stop signal to stop the current thread
    :return: The list of keys of files in the destination bucket
    """
    keys = []
    etl_header_gen = EtlHeadGenerator(source_key)
    ccov_artifact_count = 0

    for msg_line_index, msg_line in enumerate(list(source.read_lines())):
        if please_stop:
            Log.error("Shutdown detected. Stopping job ETL.")

        try:
            task_cluster_record = convert.json2value(msg_line)
        except Exception, e:
            if "JSON string is only whitespace" in e:
                continue
            else:
                Log.error("unexpected JSON decoding problem", cause=e)

        parent_etl = task_cluster_record.etl
        artifacts = task_cluster_record.task.artifacts

        # chop some not-needed, and verbose, properties from tc record
        task_cluster_record.etl = None
        task_cluster_record.action.timings = None
        task_cluster_record.action.etl = None
        task_cluster_record.task.artifacts = None
        task_cluster_record.task.runs = None

        for artifact in artifacts:
            # we're only interested in jscov files, at lease at the moment
            if "jscov" not in artifact.name:
                continue

            # if ccov_artifact_count == 0:
            #     # TEMP, WHILE WE MONITOR
            #     Log.warning("Yea! Code Coverage for key {{key}} is being processed!\n{{ccov_file}} ", ccov_file=artifact.url, key=source_key)
            ccov_artifact_count += 1

            # fetch the artifact
            response_stream = http.get(artifact.url).raw

            _, file_etl = etl_header_gen.next(source_etl=parent_etl, url=artifact.url)

            records = []
            with Timer("Processing {{ccov_file}}", param={"ccov_file": artifact.url}):
                for source_file_index, obj in enumerate(stream.parse(response_stream, [], ["."])):
                    if please_stop:
                        Log.error("Shutdown detected. Stopping job ETL.")

                    if source_file_index == 0:
                        # this is not a jscov object but an object containing the version metadata
                        # TODO: this metadata should not be here
                        # TODO: this version info is not used right now. Make use of it later.
                        jscov_format_version = obj.get("version")
                        continue

                    try:
                        process_source_file(
                            file_etl,
                            obj,
                            task_cluster_record,
                            records
                        )
                    except Exception, e:
                        Log.warning(
                            "Error processing test {{test_url}} and source file {{source}}",
                            test_url=obj.get("testUrl"),
                            source=obj.get("sourceFile"),
                            cause=e
                        )

            with Timer("writing {{num}} records to s3", {"num": len(records)}):
                destination.extend(records, overwrite=True)
            keys.append(etl2key(file_etl))

    return keys


def process_source_file(parent_etl, obj, task_cluster_record, records):
    obj = wrap(obj)

    # get the test name. Just use the test file name at the moment
    # TODO: change this when needed
    try:
        test_name = unwraplist(obj.testUrl).split("/")[-1]
    except Exception, e:
        raise Log.error("can not get testUrl from coverage object", cause=e)

    # turn obj.covered (a list) into a set for use later
    file_covered = set(obj.covered)

    # file-level info
    file_info = wrap({
        "name": obj.sourceFile,
        "covered": [{"line": c} for c in obj.covered],
        "uncovered": obj.uncovered,
        "total_covered": len(obj.covered),
        "total_uncovered": len(obj.uncovered),
        "percentage_covered": len(obj.covered) / (len(obj.covered) + len(obj.uncovered))
    })

    # orphan lines (i.e. lines without a method), initialized to all lines
    orphan_covered = set(obj.covered)
    orphan_uncovered = set(obj.uncovered)

    # iterate through the methods of this source file
    # a variable to count the number of lines so far for this source file
    for count, (method_name, method_lines) in enumerate(obj.methods.iteritems()):
        all_method_lines = set(method_lines)
        method_covered = all_method_lines & file_covered
        method_uncovered = all_method_lines - method_covered
        method_percentage_covered = len(method_covered) / len(all_method_lines)

        orphan_covered = orphan_covered - method_covered
        orphan_uncovered = orphan_uncovered - method_uncovered

        new_record = set_default(
            {
                "test": {
                    "name": test_name,
                    "url": obj.testUrl
                },
                "source": {
                    "file": file_info,
                    "method": {
                        "name": method_name,
                        "covered": [{"line": c} for c in method_covered],
                        "uncovered": method_uncovered,
                        "total_covered": len(method_covered),
                        "total_uncovered": len(method_uncovered),
                        "percentage_covered": method_percentage_covered,
                    }
                },
                "etl": {
                    "id": count + 1,
                    "source": parent_etl,
                    "type": "join",
                    "machine": machine_metadata,
                    "timestamp": Date.now()
                }
            },
            task_cluster_record
        )
        key = etl2key(new_record.etl)
        records.append({"id": key, "value": new_record})

    # a record for all the lines that are not in any method
    # every file gets one because we can use it as canonical representative
    new_record = set_default(
        {
            "test": {
                "name": test_name,
                "url": obj.testUrl
            },
            "source": {
                "is_file": True,  # THE ORPHAN LINES WILL REPRESENT THE FILE AS A WHOLE
                "file": file_info,
                "method": {
                    "covered": [{"line": c} for c in orphan_covered],
                    "uncovered": orphan_uncovered,
                    "total_covered": len(orphan_covered),
                    "total_uncovered": len(orphan_uncovered),
                    "percentage_covered": len(orphan_covered) / max(1, (len(orphan_covered) + len(orphan_uncovered))),
                }
            },
            "etl": {
                "id": 0,
                "source": parent_etl,
                "type": "join",
                "machine": machine_metadata,
                "timestamp": Date.now()
            },
        },
        task_cluster_record
    )
    key = etl2key(new_record.etl)
    records.append({"id": key, "value": new_record})


def get_revision_info(task_definition, resources):
    """
    Get the changeset, revision and push info for a given task in TaskCluster

    :param task_definition: The task definition
    :param resources: Pass this from the process method
    :return: The repo object containing information about the changeset, revision and push
    """

    # head_repo will look like "https://hg.mozilla.org/try/"
    head_repo = task_definition.payload.env.GECKO_HEAD_REPOSITORY
    branch = head_repo.split("/")[-2]

    revision = task_definition.payload.env.GECKO_HEAD_REV
    rev = Revision(branch={"name": branch}, changeset=Changeset(id=revision))
    repo = resources.hg.get_revision(rev)
    return repo


def get_run_info(task_definition):
    """
    Get the run object that contains properties that describe the run of this job

    :param task_definition: The task definition
    :return: The run object
    """
    run = Dict()
    run.suite = task_definition.extra.suite
    run.chunk = task_definition.extra.chunks.current
    return run


def get_build_info(task_definition):
    """
    Get a build object that describes the build

    :param task_definition: The task definition
    :return: The build object
    """
    build = Dict()
    build.platform = task_definition.extra.treeherder.build.platform

    # head_repo will look like "https://hg.mozilla.org/try/"
    head_repo = task_definition.payload.env.GECKO_HEAD_REPOSITORY
    branch = head_repo.split("/")[-2]
    build.branch = branch

    build.revision = task_definition.payload.env.GECKO_HEAD_REV
    build.revision12 = build.revision[0:12]

    # MOZILLA_BUILD_URL looks like this:
    # "https://queue.taskcluster.net/v1/task/e6TfNRfiR3W7ZbGS6SRGWg/artifacts/public/build/target.tar.bz2"
    build.url = task_definition.payload.env.MOZILLA_BUILD_URL

    # get the taskId of the build, then from that get the task definition of the build
    # note: this is a fragile way to get the taskId of the build
    build.taskId = build.url.split("/")[5]
    queue = taskcluster.Queue()
    build_task_definition = wrap(queue.task(taskId=build.taskId))
    build.name = build_task_definition.extra.build_name
    build.product = build_task_definition.extra.build_product
    build.type = build_task_definition.extra.build_type  #TODO: expand "dbg" to "debug"
    build.created_timestamp = Date(build_task_definition.created).unix

    return build


def add_tc_prefix(dest_etl):
    # FIX ONCE TC LOGGER IS USING "tc" PREFIX FOR KEYS
    if not dest_etl.source.source.source:
        dest_etl.source.source.type = "join"
        dest_etl.source.source.source = {"id": "tc"}

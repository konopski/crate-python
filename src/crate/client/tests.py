# -*- coding: utf-8; -*-
#
# Licensed to CRATE Technology GmbH ("Crate") under one or more contributor
# license agreements.  See the NOTICE file distributed with this work for
# additional information regarding copyright ownership.  Crate licenses
# this file to you under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.  You may
# obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
# License for the specific language governing permissions and limitations
# under the License.
#
# However, if you have executed another commercial license agreement
# with Crate these terms will supersede the license and you may use the
# software solely pursuant to the terms of the relevant commercial agreement.

from __future__ import absolute_import

import json
import unittest
import doctest
import re
from pprint import pprint
from datetime import datetime, date

import requests
from zope.testing.renormalizing import RENormalizing
import zc.customdoctests

from crate.testing.layer import CrateLayer
from crate.testing.tests import crate_path, docs_path
from crate.client import connect

from . import http
from .test_cursor import CursorTest
from .test_http import HttpClientTest, ThreadSafeHttpClientTest, KeepAliveClientTest
from .sqlalchemy.tests import test_suite as sqlalchemy_test_suite
from .sqlalchemy.types import ObjectArray
from .compat import cprint


class ClientMocked(object):
    def __init__(self):
        self.response = {}

    def sql(self, stmt=None, parameters=None):
        return self.response

    def set_next_response(self, response):
        self.response = response


def setUpMocked(test):
    test.globs['connection_client_mocked'] = ClientMocked()


crate_port = 44209
crate_transport_port = 44309
crate_layer = CrateLayer('crate',
                         crate_home=crate_path(),
                         crate_exec=crate_path('bin', 'crate'),
                         port=crate_port,
                         transport_port=crate_transport_port)

crate_host = "127.0.0.1:{port}".format(port=crate_port)
crate_uri = "http://%s" % crate_host


def setUpWithCrateLayer(test):
    test.globs['HttpClient'] = http.Client
    test.globs['crate_host'] = crate_host
    test.globs['pprint'] = pprint
    test.globs['print'] = cprint

    conn = connect(crate_host)
    cursor = conn.cursor()

    def refresh(table):
        cursor.execute("refresh table %s" % table)
    test.globs["refresh"] = refresh

    with open(docs_path('testing/testdata/mappings/locations.sql')) as s:
        stmt = s.read()
        cursor.execute(stmt)
        stmt = ("select count(*) from information_schema.tables "
                "where table_name = 'locations'")
        cursor.execute(stmt)
        assert cursor.fetchall()[0][0] == 1

    data_path = docs_path('testing/testdata/data/test_a.json')
    # load testing data into crate
    cursor.execute("copy locations from ?", (data_path,))
    # refresh location table so imported data is visible immediately
    refresh("locations")

    # create blob table
    cursor.execute("create blob table myfiles clustered into 1 shards with (number_of_replicas=0)")


def setUpCrateLayerAndSqlAlchemy(test):
    setUpWithCrateLayer(test)
    import sqlalchemy as sa
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker

    data = {
        "settings": {
            "mapper": {
                "dynamic": True
            }
        },
        "mappings": {
            "default": {
                "_meta": {
                    "primary_keys": "id",
                    "columns": {
                        "more_details": {
                            "collection_type": "array"
                        }
                    }
                },
                "properties": {
                    "id": {
                        "type": "string",
                        "index": "not_analyzed"
                    }
                }
            }
        }
    }
    requests.put('{0}/characters'.format(crate_uri), data=json.dumps(data))

    engine = sa.create_engine('crate://{0}'.format(crate_host))
    Base = declarative_base()

    class Location(Base):
        __tablename__ = 'locations'
        name = sa.Column(sa.String, primary_key=True)
        kind = sa.Column(sa.String)
        date = sa.Column(sa.Date, default=date.today)
        datetime = sa.Column(sa.DateTime, default=datetime.utcnow)
        nullable_datetime = sa.Column(sa.DateTime)
        nullable_date = sa.Column(sa.Date)
        flag = sa.Column(sa.Boolean)
        details = sa.Column(ObjectArray)

    Session = sessionmaker(engine)
    session = Session()
    test.globs['sa'] = sa
    test.globs['engine'] = engine
    test.globs['Location'] = Location
    test.globs['Base'] = Base
    test.globs['session'] = session
    test.globs['Session'] = Session


def tearDownWithCrateLayer(test):
    # clear testing data
    conn = connect(crate_host)
    cursor = conn.cursor()
    cursor.execute("drop table locations")
    cursor.execute("drop blob table myfiles")
    try:
        cursor.execute("drop table characters")
    except:
        pass


def test_suite():
    suite = unittest.TestSuite()
    flags = (doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS)
    checker = RENormalizing([
        # python 3 drops the u" prefix on unicode strings
        (re.compile(r"u('[^']*')"), r"\1"),

        # python 3 includes module name in exceptions
        (re.compile(r"crate.client.exceptions.ProgrammingError:"),
         "ProgrammingError:"),
        (re.compile(r"crate.client.exceptions.ConnectionError:"),
         "ConnectionError:"),
        (re.compile(r"crate.client.exceptions.DigestNotFoundException:"),
         "DigestNotFoundException:"),
        (re.compile(r"crate.client.exceptions.BlobsDisabledException:"),
         "BlobsDisabledException:"),
        (re.compile(r"<type "),
         "<class "),
    ])

    s = doctest.DocFileSuite(
        'cursor.txt',
        'connection.txt',
        checker=checker,
        setUp=setUpMocked,
        optionflags=flags
    )
    suite.addTest(s)
    suite.addTest(unittest.makeSuite(CursorTest))
    suite.addTest(unittest.makeSuite(HttpClientTest))
    suite.addTest(unittest.makeSuite(KeepAliveClientTest))
    suite.addTest(unittest.makeSuite(ThreadSafeHttpClientTest))
    suite.addTest(sqlalchemy_test_suite())
    suite.addTest(doctest.DocTestSuite('crate.client.connection'))
    suite.addTest(doctest.DocTestSuite('crate.client.http'))

    s = doctest.DocFileSuite(
        'sqlalchemy/itests.txt',
        checker=checker,
        setUp=setUpCrateLayerAndSqlAlchemy,
        tearDown=tearDownWithCrateLayer,
        optionflags=flags
    )
    s.layer = crate_layer
    suite.addTest(s)

    s = doctest.DocFileSuite(
        'http.txt',
        '../../../docs/client.txt',
        '../../../docs/advanced_usage.txt',
        '../../../docs/blobs.txt',
        checker=checker,
        setUp=setUpWithCrateLayer,
        tearDown=tearDownWithCrateLayer,
        optionflags=flags
    )
    s.layer = crate_layer
    suite.addTest(s)

    s = doctest.DocFileSuite(
        '../../../docs/sqlalchemy.txt',
        checker=checker,
        setUp=setUpCrateLayerAndSqlAlchemy,
        tearDown=tearDownWithCrateLayer,
        optionflags=flags
    )
    s.layer = crate_layer
    suite.addTest(s)

    return suite
